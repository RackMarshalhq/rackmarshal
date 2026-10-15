"""Restricted core-only systemd lifecycle adapter; never enables units or replays jobs."""
import json
import os
from pathlib import Path
import subprocess
from .lifecycle import require, private_dir, read, write_json, fsync_dir

BASE = ('rackmarshal-status.service', 'rackmarshal-notify.service', 'rackmarshal-notify.timer',
        'rackmarshal-domain@.service', 'rackmarshal-domain@.timer')
DOMAINS = ('pve', 'zfs', 'backup', 'ha', 'hardware', 'mount')
INSTANCES = tuple('rackmarshal-domain@' + domain + suffix for domain in DOMAINS for suffix in ('.service', '.timer'))
ALLOWED = set(BASE + INSTANCES)


class SystemdRuntime:
    def __init__(self, marker, unit_directory, accept, readiness, owner=0, runner=None):
        self.marker, self.unit_directory = Path(marker).absolute(), Path(unit_directory).absolute()
        self.accept_callback, self.readiness = accept, readiness
        self.owner = owner
        self.runner = runner or self._run
        self.commands = []
        private_dir(self.marker.parent, owner)
        private_dir(self.unit_directory, owner)

    def _run(self, argv):
        result = subprocess.run(argv, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'},
                                cwd='/', text=True, capture_output=True, timeout=45)
        self.commands[-1].update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        require(result.returncode == 0, 'systemd command failed: ' + ' '.join(argv))
        return result.stdout

    def command(self, *args):
        argv = ['/usr/bin/systemctl', *args]
        entry = {'argv': argv}
        self.commands.append(entry)
        try:
            result = self.runner(argv)
            entry['stdout'] = result
            return result
        except BaseException as exc:
            entry['error'] = repr(exc)
            raise

    def fields(self, name):
        result = self.command('show', name, '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState',
                              '-p', 'Type', '-p', 'MainPID', '-p', 'NeedDaemonReload')
        return dict(line.split('=',1) for line in result.splitlines() if '=' in line)

    def snapshot(self):
        output = self.command('list-units','--all','--plain','--no-legend','--no-pager')
        names = {line.split()[0] for line in output.splitlines() if line.split() and line.split()[0].startswith('rackmarshal')}
        require(names <= ALLOWED, 'unsupported runtime unit')
        names |= set(BASE[:3])
        units = {name:self.fields(name) for name in sorted(names)}
        for value in units.values():
            require(value['ActiveState'] in ('active','inactive'), 'transitional or failed unit')
            require(value.get('NeedDaemonReload') == 'no', 'unit requires reload before lifecycle')
            require(value['UnitFileState'] in ('enabled','disabled','static'), 'unsupported enablement')
            # Wait for in-flight processing separately; never terminate it as an upgrade shortcut.
            require(not(value.get('Type') == 'oneshot' and value['ActiveState'] != 'inactive'), 'in-flight oneshot; retry after it finishes')
        files = self.command('list-unit-files','--all','--plain','--no-legend','--no-pager')
        enabled = {c[0]:c[1] for line in files.splitlines() if (c:=line.split()) and c[0].startswith('rackmarshal')}
        require(set(enabled) <= ALLOWED, 'unsupported installed unit')
        return {'units':units,'enablement':enabled}

    def guard(self, transaction, snapshot):
        value = {'transaction':str(Path(transaction).absolute())}
        if os.path.lexists(self.marker):
            require(json.loads(read(self.marker,self.owner)) == value, 'another maintenance owner')
        else:
            write_json(self.marker,value)
        text = ('[Unit]\nConditionPathExists=!' + str(self.marker) + '\n').encode()
        require('\n' not in str(self.marker), 'unsafe marker path')
        for name in BASE:
            directory = self.unit_directory / (name + '.d')
            if not directory.exists():
                directory.mkdir(mode=0o755);fsync_dir(directory.parent)
            private_dir(directory,self.owner)
            path = directory / '99-lifecycle-maintenance.conf'
            if os.path.lexists(path):require(read(path,self.owner) == text,'maintenance override conflict')
            else:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
                with os.fdopen(fd,'wb') as stream:
                    stream.write(text);stream.flush();os.fsync(stream.fileno())
                fsync_dir(directory)
        for name in sorted(ALLOWED):
            d=self.unit_directory/(name+'.d')
            if d.exists():
                private_dir(d,self.owner)
                require({p.name for p in d.iterdir()} <= {'20-cycle-health.conf','99-lifecycle-maintenance.conf'}, 'unsupported unit override')
        self.command('daemon-reload')
        for name in BASE:
            loaded=self.command('cat',name)
            require(text.decode().strip() in loaded,'maintenance condition not loaded')
        for name in sorted(set(BASE[:3])|set(INSTANCES)):
            effective=self.command('show',name,'-p','Conditions','-p','DropInPaths')
            # systemd prints tuple(type,trigger,negate,parameter,state). No trigger OR
            # conditions or reset/extra conditions are accepted in this scope.
            lines=dict(line.split('=',1) for line in effective.splitlines() if '=' in line)
            expected='ConditionPathExists = false true '+str(self.marker)
            require(expected in lines.get('Conditions',''), 'effective maintenance condition absent')
            require(lines['Conditions'].count('ConditionPathExists')==1, 'ambiguous effective condition')
            paths=lines.get('DropInPaths','').split()
            require(all(Path(p).parent.parent==self.unit_directory and Path(p).name in ('20-cycle-health.conf','99-lifecycle-maintenance.conf') for p in paths), 'unrecognized effective drop-in')

    def quiesce(self, snapshot):
        names = sorted(snapshot['units'])
        for name in names:
            if name.endswith('.timer'):self.command('stop',name)
        # Recheck oneshot targets after timer stop to close the timer activation race.
        targets=set(names)|{name.removesuffix('.timer')+'.service' for name in names if name.endswith('.timer')}
        for name in sorted(targets):
            if not name.endswith('.service'):continue
            state=self.fields(name)
            require(state['ActiveState'] in ('active','inactive'),'job running/transitional')
            require(not(state.get('Type')=='oneshot' and state['ActiveState']!='inactive'),'oneshot became active; maintenance remains guarded')
            self.command('stop',name)
        for name in sorted(targets):
            value=self.fields(name)
            require(value['ActiveState']=='inactive' and value.get('MainPID','0')=='0','unit not quiescent')

    def accept(self, transaction, journal):
        self.accept_callback(transaction,journal)

    def resume(self, transaction, snapshot, authorize):
        require(json.loads(read(self.marker,self.owner)) == {'transaction':str(Path(transaction).absolute())},'maintenance ownership differs')
        # Persist the acceptance/activation commit decision before permitting any
        # boot-time or ordinary workload restart. Completion remains separate.
        authorize()
        # Marker removal is explicitly confined to the lifecycle-owned file.
        self.marker.unlink();fsync_dir(self.marker.parent)
        units=snapshot['units']
        for name,value in units.items():
            if name.endswith('.service') and value['ActiveState']=='active' and value.get('Type')!='oneshot':
                self.command('start',name);self.readiness(name)
        for name,value in units.items():
            if name.endswith('.timer') and value['ActiveState']=='active':self.command('start',name)
        actual=self.snapshot()
        require(actual['enablement']==snapshot['enablement'],'enablement changed')
        for name,value in units.items():
            require(actual['units'].get(name,{}).get('ActiveState')==value['ActiveState'],'active state not restored')

    def hold(self, transaction, snapshot):
        self.guard(transaction,snapshot)
        self.quiesce(snapshot)
