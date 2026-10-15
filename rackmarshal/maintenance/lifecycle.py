"""Same-schema application transactions. Runtime adapter owns maintenance gating.

This module never restores a live database or edits configuration. Backups and
journals are retained. Unknown current bytes require explicit investigation.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile


class Refused(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_dir(path, owner):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        info = item.lstat()
        require(stat.S_ISDIR(info.st_mode), 'directory link or special ancestor')
        require(info.st_uid in (0, owner), 'foreign directory owner')
        if info.st_mode & 0o022:
            require(item != path and info.st_uid == 0 and info.st_mode & stat.S_ISVTX,
                    'writable directory ancestor')
    return path


def read(path, owner):
    private_dir(Path(path).parent, owner)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and info.st_nlink == 1
                and not info.st_mode & 0o022 and info.st_size <= 64 * 1024 * 1024,
                'unsafe file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        require(len(data) == info.st_size, 'file changed during read')
        return data
    finally:
        os.close(fd)


def write_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.journal-', dir=path.parent)
    # Temporary files are retained on failure; no recursive cleanup.
    with os.fdopen(fd, 'wb') as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, path)
    fsync_dir(path.parent)


def inventory(root, owner):
    root = private_dir(root, owner)
    result = {}
    for path in sorted([root, *root.rglob('*')]):
        info = path.lstat()
        name = str(path.relative_to(root))
        require(info.st_uid == owner and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022), 'unsafe code ownership/mode')
        value = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
        if stat.S_ISDIR(info.st_mode):
            value['kind'] = 'directory'
        elif stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1, 'hardlinked code')
            value.update(kind='file', sha256=digest(read(path, owner)))
        elif stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            allowed = ((path.parent == root / 'bin' and path.name in
                        ('python', 'python3', f'python{os.sys.version_info.major}.{os.sys.version_info.minor}')
                        and path.resolve() == Path(os.sys.executable).resolve()) or
                       (path == root / 'lib64' and target == 'lib'))
            require(allowed, 'unsupported code link')
            value.update(kind='link', target=target)
        else:
            raise Refused('special code file')
        result[name] = value
    return result


def clone_tree(source, destination, owner):
    expected = inventory(source, owner)
    require(not os.path.lexists(destination), 'destination already exists')
    shutil.copytree(source, destination, symlinks=True)
    for name, value in expected.items():
        path = destination / name
        # Restore metadata only on newly created copies, never the source.
        if os.geteuid() == 0:
            os.chown(path, value['uid'], value['gid'], follow_symlinks=False)
        if value['kind'] == 'file':
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        elif value['kind'] == 'directory':
            fsync_dir(path)
    fsync_dir(destination.parent)
    require(inventory(destination, owner) == expected, 'copy verification failed')
    return expected


def database_snapshot(path):
    """Canonical logical digest includes schema, ledger and every table row."""
    path = Path(path).absolute()
    require(not path.is_symlink() and path.is_file(), 'unsafe database')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        require(connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'database corrupt')
        connection.execute('BEGIN')
        schema = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        h = hashlib.sha256()
        for row in schema:
            h.update(repr(row).encode())
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            rows = connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"').fetchall()
            label=table.encode();h.update(len(label).to_bytes(8,'big'));h.update(label);h.update(len(rows).to_bytes(8,'big'))
            for row in sorted(repr(row).encode() for row in rows):
                h.update(len(row).to_bytes(8, 'big')); h.update(row)
        ledger = connection.execute('SELECT id,checksum FROM schema_migrations ORDER BY id').fetchall()
        return {'logical_sha256': h.hexdigest(), 'schema_sha256': digest(repr(schema).encode()), 'ledger': ledger}
    finally:
        connection.close()


def verified_backup(database, transaction):
    expected = database_snapshot(database)
    backup = transaction / 'state-backup.sqlite'
    restore = transaction / 'restore-proof.sqlite'
    for destination, source in ((backup, database), (restore, backup)):
        require(not destination.exists(), 'backup path exists')
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        src = sqlite3.connect(Path(source).absolute().as_uri() + '?mode=ro', uri=True)
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        require(database_snapshot(destination) == expected, 'backup restoration differs')
        fd = os.open(destination, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    fsync_dir(transaction)
    require(database_snapshot(database) == expected, 'database changed during backup')
    return {'snapshot': expected, 'backup_sha256': digest(backup.read_bytes()),
            'restore_sha256': digest(restore.read_bytes())}


class Lifecycle:
    """Fail-closed transaction engine. Caller supplies validated artifact trees.

    runtime must implement snapshot, guard, quiesce, accept, resume and hold.
    guard/hold are persistent across reboot; resume removes guards only for
    previously active, explicitly compatible workloads. Calls are journaled.
    """
    def __init__(self, active, store, database, protected, runtime, owner=None, fault=None):
        self.owner = os.getuid() if owner is None else owner
        self.active, self.store, self.database = map(lambda p: Path(p).absolute(), (active, store, database))
        self.protected = [Path(p).absolute() for p in protected]
        self.runtime = runtime
        self.fault = fault or (lambda phase: None)
        private_dir(self.active.parent, self.owner)
        private_dir(self.store, self.owner)
        require(not self.store.is_relative_to(self.active) and not self.active.is_relative_to(self.store), 'overlapping paths')
        require(self.active.parent.stat().st_dev == self.store.stat().st_dev, 'cross-filesystem transaction')

    @contextmanager
    def lock(self):
        path = self.store / 'lock'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == self.owner and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600, 'unsafe lock')
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise Refused('lifecycle already running') from exc
            yield
        finally:
            os.close(fd)

    def protected_hashes(self):
        return {str(p): digest(read(p, self.owner)) for p in self.protected}

    def save(self, transaction, journal, phase):
        journal['phase'] = phase
        journal['runtime_commands'] = list(getattr(self.runtime, 'commands', []))
        write_json(transaction / 'transaction.json', journal)
        self.fault(phase)

    def upgrade(self, candidate, identity, expected_old, expected_schema, compatible, evidence=None, expected_candidate=None):
        require(compatible is True, 'semantic compatibility unqualified')
        with self.lock():
            for path in self.store.glob('*/transaction.json'):
                state = json.loads(read(path, self.owner))
                require(state['phase'] in ('COMMITTED', 'ROLLED_BACK', 'REFUSED'), 'unfinished transaction')
            before = inventory(self.active, self.owner)
            require(before == expected_old, 'legacy inventory differs')
            db = database_snapshot(self.database)
            require(db['schema_sha256'] == expected_schema['schema_sha256'] and db['ledger'] == expected_schema['ledger'], 'schema-changing upgrade refused')
            protected = self.protected_hashes()
            candidate = Path(candidate).absolute()
            require(not candidate.is_relative_to(self.active) and not candidate.is_relative_to(self.store), 'candidate overlaps transaction')
            transaction = Path(tempfile.mkdtemp(prefix='transaction-', dir=self.store))
            fsync_dir(self.store)
            journal = {'format': 1, 'active': str(self.active), 'database': str(self.database), 'identity': identity,
                       'before': before, 'protected': protected, 'database_before': db,
                       'runtime': self.runtime.snapshot(), 'after': inventory(candidate, self.owner), 'evidence': evidence or {}}
            if expected_candidate is not None:require(journal['after']==expected_candidate,'candidate changed after semantic proof')
            self.save(transaction, journal, 'STAGING')
            protected_dir=transaction/'protected';protected_dir.mkdir(mode=0o700)
            journal['protected_backups']={}
            for index,path in enumerate(self.protected):
                content=read(path,self.owner);target=protected_dir/str(index)
                fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream:
                    stream.write(content);stream.flush();os.fsync(stream.fileno())
                require(digest(read(target,self.owner))==protected[str(path)],'protected backup changed')
                info=path.lstat();journal['protected_backups'][str(path)]={'file':str(target.relative_to(transaction)),'sha256':protected[str(path)],'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
            fsync_dir(protected_dir);fsync_dir(transaction)
            clone_tree(candidate, transaction / 'candidate', self.owner)
            self.save(transaction, journal, 'STAGED')
            # Exceptions after this boundary leave the persistent guard in place.
            try:
                self.save(transaction, journal, 'GUARD_INTENT')
                self.runtime.guard(transaction, journal['runtime'])
                self.save(transaction, journal, 'GUARDED')
                self.runtime.quiesce(journal['runtime'])
                self.save(transaction, journal, 'QUIESCED')
                journal['backup'] = verified_backup(self.database, transaction)
                require(journal['backup']['snapshot']['schema_sha256'] == expected_schema['schema_sha256'] and journal['backup']['snapshot']['ledger'] == expected_schema['ledger'], 'quiesced schema changed')
                require(self.protected_hashes() == protected, 'protected files changed')
                require(inventory(self.active, self.owner) == before, 'code changed during preflight')
                self.save(transaction, journal, 'OLD_RENAME_INTENT')
                os.rename(self.active, transaction / 'previous'); fsync_dir(self.active.parent); fsync_dir(transaction)
                self.save(transaction, journal, 'OLD_RETAINED')
                os.rename(transaction / 'candidate', self.active); fsync_dir(self.active.parent); fsync_dir(transaction)
                self.save(transaction, journal, 'ACTIVATED')
                require(inventory(self.active, self.owner) == journal['after'], 'activation differs')
                self.runtime.accept(transaction, journal)
                require(database_snapshot(self.database) == journal['backup']['snapshot'], 'live database changed during acceptance')
                require(self.protected_hashes() == protected, 'protected files changed')
                self.save(transaction, journal, 'ACCEPTED')
                self.runtime.resume(transaction, journal['runtime'], lambda: self.save(transaction,journal,'RESUME_AUTHORIZED'))
                self.save(transaction, journal, 'COMMITTED')
            except BaseException as exc:
                journal['error'] = repr(exc)
                # Do not silently restore data or resume workloads after uncertainty.
                try: self.runtime.hold(transaction, journal['runtime'])
                finally: self.save(transaction, journal, 'RECOVERY_REQUIRED')
                raise
            return transaction

    def rollback(self, transaction, compatible):
        require(compatible is True, 'rollback semantic compatibility unqualified')
        with self.lock():
            transaction = Path(transaction).absolute()
            require(transaction.parent == self.store, 'foreign transaction')
            for path in self.store.glob('*/transaction.json'):
                if path.parent != transaction:
                    require(json.loads(read(path,self.owner))['phase'] in ('COMMITTED','ROLLED_BACK','REFUSED'), 'another unfinished transaction')
            journal = json.loads(read(transaction / 'transaction.json', self.owner))
            require(journal['active'] == str(self.active) and journal['database'] == str(self.database), 'transaction target differs')
            require(journal['phase'] in ('STAGING', 'STAGED', 'GUARD_INTENT', 'GUARDED', 'QUIESCED', 'COMMITTED', 'RECOVERY_REQUIRED', 'OLD_RETAINED', 'ACTIVATED', 'ACCEPTED', 'OLD_RENAME_INTENT', 'ROLLBACK_INTENT', 'ROLLBACK_GUARD_INTENT', 'RESUME_AUTHORIZED'), 'unsupported rollback phase')
            previous = transaction / 'previous'
            previous_exists = previous.exists()
            if previous_exists: require(inventory(previous, self.owner) == journal['before'], 'rollback bytes corrupt')
            current = inventory(self.active, self.owner) if self.active.exists() else None
            if previous_exists: require(current in (None, journal['after']), 'current code conflict')
            else: require(current == journal['before'], 'old code unavailable or current code conflict')
            current_db = database_snapshot(self.database)
            require(current_db['schema_sha256'] == journal['database_before']['schema_sha256'] and
                    current_db['ledger'] == [tuple(x) for x in journal['database_before']['ledger']], 'rollback schema differs')
            require(self.protected_hashes() == journal['protected'], 'protected files conflict')
            try:
                self.save(transaction, journal, 'ROLLBACK_GUARD_INTENT')
                self.runtime.guard(transaction, journal['runtime'])
                self.runtime.quiesce(journal['runtime'])
                journal['rollback_database'] = database_snapshot(self.database)
                require(journal['rollback_database']['schema_sha256'] == journal['database_before']['schema_sha256'] and journal['rollback_database']['ledger'] == [tuple(x) for x in journal['database_before']['ledger']], 'quiesced rollback schema changed')
                require(self.protected_hashes() == journal['protected'], 'protected files changed during quiesce')
                require((inventory(self.active,self.owner) if self.active.exists() else None) == current, 'code changed during quiesce')
                self.save(transaction, journal, 'ROLLBACK_INTENT')
                if previous_exists and self.active.exists():
                    require(not (transaction / 'rejected').exists(), 'rejected path exists')
                    os.rename(self.active, transaction / 'rejected'); fsync_dir(self.active.parent); fsync_dir(transaction)
                if previous_exists:
                    os.rename(previous, self.active); fsync_dir(self.active.parent); fsync_dir(transaction)
                require(inventory(self.active, self.owner) == journal['before'], 'restored code differs')
                self.runtime.accept(transaction, dict(journal, rollback=True))
                require(database_snapshot(self.database) == journal['rollback_database'], 'rollback changed newer data')
                require(self.protected_hashes() == journal['protected'], 'rollback changed protected files')
                self.runtime.resume(transaction, journal['runtime'], lambda: self.save(transaction,journal,'RESUME_AUTHORIZED'))
                self.save(transaction, journal, 'ROLLED_BACK')
            except BaseException as exc:
                journal['rollback_error'] = repr(exc)
                try: self.runtime.hold(transaction, journal['runtime'])
                finally: self.save(transaction, journal, 'RECOVERY_REQUIRED')
                raise
            return transaction
