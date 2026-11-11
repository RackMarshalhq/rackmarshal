"""Apply database migrations all-or-nothing, and rehearse them on a copy first.

Used by `rackmarshal upgrade-plan` to judge a release's database changes, and later by the
upgrade itself. Nothing here touches the real database except `apply_all`, which the plan never calls.

`apply_all` runs every migration plus its ledger row inside ONE SQLite transaction, so a failure
leaves the database exactly as it was. (The ordinary `migrate --apply` runs each file separately.)

`rehearse` copies the database to a private folder, applies the migrations to the copy and checks:
* every table that existed before still exists, with every row and every old column unchanged
  (a migration may add tables and columns, and may rebuild a table, but must not lose data);
* the layout fingerprint of the result, so the real run can be compared with the rehearsal.
"""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

SORT_ID = re.compile(r"^(\d{3})([a-z]?)", re.I)


class RehearsalError(Exception):
    """A refusal written for the person at the keyboard."""


def migration_order_key(migration_id):
    """Order used by the migration runner: number first, then the letter suffix."""
    match = SORT_ID.match(migration_id)
    if not match:
        raise RehearsalError("Migration '%s' does not start with a three-digit number." % migration_id)
    return (match.group(1), match.group(2).lower(), migration_id)


def statements(sql):
    """Split a migration file into complete SQL statements (triggers stay in one piece)."""
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            if pending.strip():
                yield pending
            pending = ""
    leftover = [line for line in pending.splitlines() if line.strip() and not line.strip().startswith("--")]
    if leftover:
        raise RehearsalError("A migration ends in the middle of a statement.")


def _ledger_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(schema_migrations)")}


def apply_all(conn, migrations, note="applied by upgrade", expect=None):
    """Apply (id, sql, sha256) triples in order, all in one transaction. `conn` needs isolation_level=None.

    `expect` is an optional (schema_sha256, ledger) pair; if the result differs, nothing is kept.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = _ledger_columns(conn)
        for migration_id, sql, checksum in migrations:
            for statement in statements(sql):
                conn.execute(statement)
            if "note" in columns:
                conn.execute("INSERT INTO schema_migrations (id, checksum, note) VALUES (?, ?, ?)",
                             (migration_id, checksum, note))
            else:
                conn.execute("INSERT INTO schema_migrations (id, checksum) VALUES (?, ?)", (migration_id, checksum))
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RehearsalError("The migrations leave %d broken foreign-key link(s)." % len(violations))
        if expect is not None:
            wanted_schema, wanted_ledger = expect
            if schema_fingerprint(conn) != wanted_schema or ledger_of(conn) != [tuple(x) for x in wanted_ledger]:
                raise RehearsalError("The migrated database differs from the rehearsal.")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def schema_fingerprint(conn):
    """Same definition as lifecycle.database_snapshot()['schema_sha256']."""
    schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    return hashlib.sha256(repr(schema).encode()).hexdigest()


def ledger_of(conn):
    return [(row[0], row[1]) for row in conn.execute("SELECT id,checksum FROM schema_migrations ORDER BY id")]


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def table_contents(conn):
    """{table: {"columns": [...], "rows": sha256 over the sorted rows}} for every ordinary table."""
    result = {}
    names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for name in names:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(%s)" % _quote(name))]
        result[name] = {"columns": columns}
    return result


def _rows_digest(conn, table, columns):
    select = "SELECT %s FROM %s" % (", ".join(_quote(c) for c in columns), _quote(table))
    digest = hashlib.sha256()
    count = 0
    for row in sorted(repr(r).encode() for r in conn.execute(select)):
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
        count += 1
    return count, digest.hexdigest()


def compare_contents(before_conn, after_conn):
    """Return a list of plain-language problems; empty means no data was lost or changed."""
    problems = []
    before, after = table_contents(before_conn), table_contents(after_conn)
    for table, info in sorted(before.items()):
        if table not in after:
            problems.append("table %s would disappear" % table)
            continue
        lost = [c for c in info["columns"] if c not in after[table]["columns"]]
        if lost:
            problems.append("table %s would lose column(s) %s" % (table, ", ".join(lost)))
            continue
        if table == "schema_migrations":
            # The history may only grow: every old (id, checksum) must still be there.
            old = {tuple(r) for r in before_conn.execute("SELECT id, checksum FROM schema_migrations")}
            new = {tuple(r) for r in after_conn.execute("SELECT id, checksum FROM schema_migrations")}
            if not old <= new:
                problems.append("the migration history would be altered")
            continue
        columns = info["columns"]
        if _rows_digest(before_conn, table, columns) != _rows_digest(after_conn, table, columns):
            problems.append("rows in table %s would change" % table)
    return problems


def rehearse(database, migrations, workdir=None, keep_copy=None):
    """Apply `migrations` to a private copy of `database` and report. Never writes to `database`.

    Returns {"schema_sha256", "ledger", "problems": [...], "added_tables": [...]}.
    `keep_copy` (a new file path) also saves the migrated copy there, for compatibility proofs.
    """
    source = Path(database).resolve()
    if not source.is_file():
        raise RehearsalError("The RackMarshal database was not found.")
    folder = Path(tempfile.mkdtemp(prefix="rehearsal-", dir=workdir))
    try:
        os.chmod(folder, 0o700)
        copy = folder / "copy.db"
        with closing(sqlite3.connect("file:%s?mode=ro" % source, uri=True, timeout=30)) as origin, \
                closing(sqlite3.connect(copy)) as target:
            origin.backup(target)
        os.chmod(copy, 0o600)
        with closing(sqlite3.connect(copy, isolation_level=None)) as before_conn, \
                closing(sqlite3.connect(copy.with_name("after.db"), isolation_level=None)) as after_conn:
            before_conn.backup(after_conn)
            after_conn.execute("PRAGMA foreign_keys=ON")
            try:
                apply_all(after_conn, migrations, note="rehearsal")
            except RehearsalError:
                raise
            except sqlite3.Error as exc:
                raise RehearsalError("The migrations do not apply to your database: %s." % exc) from exc
            if keep_copy is not None:
                with closing(sqlite3.connect(keep_copy)) as kept:
                    after_conn.backup(kept)
                os.chmod(keep_copy, 0o600)
            problems = compare_contents(before_conn, after_conn)
            added = sorted(set(table_contents(after_conn)) - set(table_contents(before_conn)))
            return {"schema_sha256": schema_fingerprint(after_conn), "ledger": ledger_of(after_conn),
                    "problems": problems, "added_tables": added}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
