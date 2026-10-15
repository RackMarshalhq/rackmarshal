import json,os,tempfile,unittest
from pathlib import Path
from rackmarshal.maintenance.lifecycle_systemd import SystemdRuntime,BASE
from rackmarshal.maintenance.lifecycle import Refused
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.units=self.root/'units';self.units.mkdir(mode=0o700)
  self.states={'rackmarshal-status.service':'active','rackmarshal-notify.service':'inactive','rackmarshal-notify.timer':'active'};self.calls=[]
  def runner(args):
   self.calls.append(args[1:]);cmd=args[1]
   if cmd=='list-units':return '\n'.join(n+' loaded '+v+' dead' for n,v in self.states.items())
   if cmd=='list-unit-files':return '\n'.join(n+' '+('static' if n.endswith('notify.service') else 'enabled') for n in self.states)
   if cmd=='show':
    n=args[2]
    if 'Conditions' in args:return 'Conditions=ConditionPathExists = false true '+str(self.root/'marker')+' untested\nDropInPaths='+str(self.units/(BASE[0]+'.d')/'99-lifecycle-maintenance.conf')
    return '\n'.join([f'ActiveState={self.states.get(n,"inactive")}', 'SubState=dead','UnitFileState='+('static' if n.endswith('notify.service') else 'enabled'),'Type='+('oneshot' if n.endswith('notify.service') else 'simple'),'MainPID=0','NeedDaemonReload=no'])
   if cmd=='cat':return (self.units/(args[2]+'.d')/'99-lifecycle-maintenance.conf').read_text()
   if cmd in ('start','stop'):self.states[args[2]]='active' if cmd=='start' else 'inactive'
   return ''
  self.rt=SystemdRuntime(self.root/'marker',self.units,lambda *a:None,lambda *a:None,owner=os.getuid(),runner=runner)
 def test_guard_stop_resume_order_and_no_enable(self):
  before=self.rt.snapshot();self.rt.guard(self.root/'tx',before);self.assertTrue((self.root/'marker').exists());self.rt.quiesce(before)
  self.assertTrue(all(v=='inactive' for v in self.states.values()));self.rt.resume(self.root/'tx',before,lambda:None)
  self.assertFalse((self.root/'marker').exists());mutations=[c for c in self.calls if c[0] in ('start','stop','enable','disable')]
  self.assertEqual(mutations[0],['stop','rackmarshal-notify.timer'])
  self.assertEqual(mutations[-2:],[['start','rackmarshal-status.service'],['start','rackmarshal-notify.timer']])
  self.assertNotIn(['start','rackmarshal-notify.service'],mutations)
 def test_other_guard_owner_refused(self):
  before=self.rt.snapshot();self.rt.guard(self.root/'first',before)
  with self.assertRaises(Refused):self.rt.guard(self.root/'second',before)
 def test_override_conflict_refused(self):
  d=self.units/(BASE[0]+'.d');d.mkdir();(d/'99-lifecycle-maintenance.conf').write_text('foreign')
  with self.assertRaises(Refused):self.rt.guard(self.root/'tx',self.rt.snapshot())
 def test_inflight_notification_refused(self):
  self.states['rackmarshal-notify.service']='active'
  with self.assertRaises(Refused):self.rt.snapshot()
 def test_unknown_unit_refused(self):
  self.states['rackmarshal-other.service']='active'
  with self.assertRaises(Refused):self.rt.snapshot()
 def test_failed_durable_authorization_keeps_guard(self):
  before=self.rt.snapshot();self.rt.guard(self.root/'tx',before);self.rt.quiesce(before)
  def fail():raise RuntimeError('journal fsync failure')
  with self.assertRaises(RuntimeError):self.rt.resume(self.root/'tx',before,fail)
  self.assertTrue((self.root/'marker').exists());self.assertTrue(all(v=='inactive' for v in self.states.values()))
if __name__=='__main__':unittest.main()
