from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from skill_invocation import read_policy,invocation_info
import skill_ledger as L

class InvocationTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent);self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def skill(self,name='demo',metadata=None):
        path=self.base/name/'SKILL.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('---\nname: '+name+'\ndescription: Demo task trigger\n---\nInstructions',encoding='utf-8')
        if metadata is not None:
            p=path.parent/'agents'/'openai.yaml';p.parent.mkdir();p.write_text(metadata,encoding='utf-8')
        return path
    def test_missing_policy_uses_documented_true_default(self):
        self.assertIs(read_policy(self.skill())['allow_implicit'],True)
        self.assertIs(read_policy(self.skill('two','interface:\n  default_prompt: "Input {topic} with * characters"'))['allow_implicit'],True)
    def test_explicit_false_and_true(self):
        for name,value in [('yes','true'),('no','false')]:
            result=read_policy(self.skill(name,'policy:\n  allow_implicit_invocation: '+value+' # comment'))
            self.assertIs(result['allow_implicit'],value=='true')
    def test_flow_policy(self):self.assertIs(read_policy(self.skill(metadata='policy: {allow_implicit_invocation: false}'))['allow_implicit'],False)
    def test_invalid_and_ambiguous_policy_do_not_become_auto(self):
        for index,metadata in enumerate(['policy:\n  allow_implicit_invocation: "false"','policy: *shared','policy:\n  allow_implicit_invocation: true\n  allow_implicit_invocation: false','policy:\n  nested:\n    allow_implicit_invocation: false','"policy": {allow_implicit_invocation: false}']):
            self.assertIsNone(read_policy(self.skill(str(index),metadata))['allow_implicit'])
    def test_copies_with_different_rules_are_reported_as_mixed(self):
        first=self.skill('one','policy:\n  allow_implicit_invocation: false');second=self.skill('two')
        info=invocation_info({'installed':True,'paths':[str(first),str(second)],'purpose':'写作'},L.frontmatter)
        self.assertEqual(info['mode'],'mixed');self.assertEqual(len(info['copies']),2);self.assertIn('Demo task',info['description'])
    def test_backup_policy_is_not_presented_as_current(self):
        path=self.skill(metadata='policy:\n  allow_implicit_invocation: false')
        info=invocation_info({'installed':False,'paths':['missing'],'archive_paths':str(path)})
        self.assertEqual(info['mode'],'manual');self.assertEqual(info['scope'],'backup');self.assertIn('重新安装后需复核',info['summary'])
    def test_removed_skill_without_backup_is_unknown(self):
        info=invocation_info({'installed':False,'paths':['missing']})
        self.assertEqual(info['mode'],'unknown');self.assertEqual(info['scope'],'none')
    def test_slash_example_and_auto_task_are_different(self):
        info=L.usage_info({'name':'to-spec','purpose':'规格说明','installed':False,'status':'已归档'})
        self.assertTrue(info['usage'].startswith('/to-spec '));self.assertFalse(info['usage_auto'].startswith('/'))
        self.assertIn('菜单选择',info['usage_desktop_hint']);self.assertIn('/skills',info['usage_cli_hint']);self.assertIn('先安装',info['usage_note'])
    def test_plugin_manual_step_identifies_provider(self):
        info=L.usage_info({'name':'chatcut:voice','purpose':'配音','installed':True,'status':'已启用'})
        self.assertTrue(info['usage'].startswith('/voice '));self.assertIn('chatcut:voice',info['usage_desktop_hint'])
    def test_backup_for_another_skill_is_not_used_as_policy_evidence(self):
        path=self.skill('parent','policy:\n  allow_implicit_invocation: false')
        info=invocation_info({'name':'child','installed':False,'paths':[],'recovery_paths':[str(path.parent)]},L.frontmatter)
        self.assertEqual(info['mode'],'unknown');self.assertEqual(info['copies'],[])

if __name__=='__main__':unittest.main(verbosity=2)
