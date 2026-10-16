import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

W=Path(__file__).resolve().parent.parent
TOOL=W
spec=importlib.util.spec_from_file_location('skill_ledger',TOOL/'skill_ledger.py')
ledger=importlib.util.module_from_spec(spec);spec.loader.exec_module(ledger)
sys.path.insert(0,str(TOOL));sys.modules['skill_ledger']=ledger
TEST_ROOT=W/'tests'/'ledger-test-fixtures';TEST_ROOT.mkdir(exist_ok=True)

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.base=Path(self.tmp.name).resolve()
        assert self.base.is_relative_to(TEST_ROOT.resolve())
        self.root=self.base/'skills';self.root.mkdir()
        self.cache=self.base/'plugins';self.cache.mkdir()
        self.config=self.base/'config.toml';self.config.write_text('',encoding='utf-8')
        data=self.base/'.data';data.mkdir()
        for name,value in [('reference.json',{}),('历史导入.json',[])]:
            (data/name).write_text(json.dumps(value),encoding='utf-8')
        self.settings={'codex_config':str(self.config),'skill_roots':[{'path':str(self.root),'label':'test'}],'plugin_cache':str(self.cache),'known_plugins':[]}
        self.save_settings();(self.base/'查看记录.template.html').write_text('<script id="data">__DATA__</script>',encoding='utf-8')
        self.skill('one')
    def tearDown(self):
        assert self.base.is_relative_to(TEST_ROOT.resolve())
        self.tmp.cleanup()
    def save_settings(self):
        (self.base/'设置.json').write_text(json.dumps(self.settings),encoding='utf-8')
    def skill(self,name,root=None):
        p=(root or self.root)/name/'SKILL.md';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('---\nname: '+name+'\ndescription: demo\n---\nHello\n',encoding='utf-8')
        return p
    def run_update(self):
        with contextlib.redirect_stdout(io.StringIO()):return ledger.update(self.base)
    def state(self):return json.loads((self.base/'.data'/'ledger.json').read_text(encoding='utf-8'))
    def test_baseline_and_no_change_do_not_fabricate_history(self):
        self.assertEqual(self.run_update()['new_events'],0)
        self.assertEqual(self.run_update()['new_events'],0)
        self.assertEqual(self.state()['events'],[])
    def test_add_remove_history_is_retained(self):
        self.run_update();p=self.skill('two');self.run_update();p.unlink();p.parent.rmdir();self.run_update()
        self.assertEqual([e['action'] for e in self.state()['events']],['新增','移除'])
        self.assertEqual(self.run_update()['new_events'],0)
    def test_disable_enable_by_file_and_directory(self):
        self.run_update();p=self.root/'one'/'SKILL.md'
        self.config.write_text("[[skills.config]]\npath = '"+str(p)+"'\nenabled = false\n",encoding='utf-8');self.run_update()
        self.assertEqual(self.state()['snapshot']['one']['state'],'配置停用')
        self.config.write_text('',encoding='utf-8');self.run_update()
        self.assertEqual([e['action'] for e in self.state()['events']],['停用','启用'])
        self.config.write_text("[[skills.config]]\npath = '"+str(p.parent)+"'\nenabled = false\n",encoding='utf-8');self.run_update()
        self.assertEqual(self.state()['snapshot']['one']['state'],'配置停用')
    def test_bad_config_keeps_existing_snapshot_and_history(self):
        self.run_update();before=(self.base/'.data'/'ledger.json').read_bytes()
        self.config.write_text('broken = [',encoding='utf-8')
        with self.assertRaises(Exception):self.run_update()
        self.assertEqual((self.base/'.data'/'ledger.json').read_bytes(),before)
    def test_inaccessible_required_root_does_not_log_removal(self):
        self.run_update();before=self.state()
        self.settings['skill_roots'][0]['path']=str(self.base/'missing');self.save_settings()
        with self.assertRaises(RuntimeError):self.run_update()
        self.assertEqual(self.state(),before)
    def test_unknown_plugin_is_cache_and_old_versions_are_not_duplicates(self):
        for version in ('1.9.0','1.10.0'):
            root=self.cache/'market'/'demo'/version
            (root/'.codex-plugin').mkdir(parents=True)
            (root/'.codex-plugin'/'plugin.json').write_text(json.dumps({'skills':'./skills/'}),encoding='utf-8')
            self.skill('test',root/'skills')
        self.run_update();r=self.state()['snapshot']['demo:test']
        self.assertEqual(r['state'],'缓存待核对');self.assertEqual(r['version'],'1.10.0');self.assertEqual(r['copies'],1)
    def test_bad_skill_aborts_scan_without_losing_other_entries(self):
        self.run_update();before=self.state();self.skill('bad').write_text('not frontmatter',encoding='utf-8')
        with self.assertRaises(RuntimeError):self.run_update()
        self.assertEqual(self.state(),before)
    def test_csv_formula_like_cells_are_neutralized(self):
        self.assertEqual(ledger.safe_cell('=HYPERLINK("example")'),"'=HYPERLINK(\"example\")")

if __name__=='__main__':unittest.main(verbosity=2)
