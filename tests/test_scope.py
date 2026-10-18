import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import skill_ledger as L
import skill_manager as M
import skill_scope as S


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        (self.base/'.data').mkdir();self.global_root=self.base/'user-skills';self.global_root.mkdir()
        self.workspace=self.base/'workspace';self.workspace.mkdir();self.cache=self.base/'cache';self.cache.mkdir()
        self.config=self.base/'config.toml';self.config.write_text('',encoding='utf-8')
        self.settings={'codex_config':str(self.config),'skill_roots':[{'path':str(self.global_root),'label':'用户','scope':'global'}],
                       'plugin_cache':str(self.cache),'known_plugins':[],'project_scan_roots':[{'path':str(self.workspace)}]}
        self.save()
        (self.base/'.data'/'reference.json').write_text('{}',encoding='utf-8');(self.base/'.data'/'历史导入.json').write_text('[]',encoding='utf-8')
        (self.base/'查看记录.template.html').write_text('<script id="data">__DATA__</script>',encoding='utf-8')
    def tearDown(self):self.temp.cleanup()
    def save(self):S.write(self.base/'设置.json',self.settings)
    def skill(self,name,owner=None):
        root=self.global_root if owner is None else self.workspace/owner/'.agents'/'skills'
        path=root/name/'SKILL.md';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('---\nname: '+name+'\ndescription: Demo\n---\nInstructions',encoding='utf-8');return path
    def update(self,force=False):
        if force:S.invalidate(self.base)
        L.update(self.base,False);return L.read_json(self.base/'.data'/'ledger.json')
    def payload(self):
        value=(self.base/'.data'/'live-data.js').read_text(encoding='utf-8')
        return json.loads(value.removeprefix('window.SkillLedgerReceive && window.SkillLedgerReceive(').removesuffix(');\n'))
    def test_same_name_global_and_two_projects_stay_separate_and_only_selected_project_uninstalls(self):
        paths=[self.skill('same'),self.skill('same','project-a'),self.skill('same','project-b')]
        state=self.update();self.assertEqual(len(state['snapshot']),3)
        rows=self.payload()['skills'];self.assertEqual([r['skill_name'] for r in rows],['same']*3)
        self.assertEqual({r['scope_label'] for r in rows},{'全局技能','project-a','project-b'})
        self.assertTrue(all(r['invocation']['mode']=='auto_manual' for r in rows))
        self.assertTrue(all(r['usage'].startswith('/same ') for r in rows))
        selected=next(r for r in rows if r['scope_label']=='project-a')
        manager=M.Manager(self.base);plan=manager.preview([selected['name']]);self.assertEqual(plan['count'],1)
        result=manager.commit(plan['id']);self.assertTrue(result['results'][0]['ok'])
        self.assertTrue(paths[0].exists());self.assertFalse(paths[1].exists());self.assertTrue(paths[2].exists())
    def test_new_project_and_new_skill_are_discovered_without_changing_roots(self):
        self.update();self.skill('first','new-project');state=self.update(True)
        self.assertEqual([e['action'] for e in state['events']],['新增'])
        self.assertEqual(self.payload()['skills'][0]['scope_label'],'new-project')
        self.skill('second','new-project');state=self.update()
        self.assertEqual(len(state['snapshot']),2);self.assertEqual(len(state['events']),2)
        rows=self.payload()['skills'];self.assertEqual({r['scope_label'] for r in rows},{'new-project'})
    def test_parent_and_nested_folders_are_different_scopes_and_not_merged(self):
        self.skill('same','repo');self.skill('same','repo/module');state=self.update()
        self.assertEqual(len(state['snapshot']),2)
        self.assertEqual({r['scope_path'] for r in state['snapshot'].values()},{str(self.workspace/'repo'),str(self.workspace/'repo'/'module')})
    def test_dependency_tree_and_wrong_agent_spelling_are_not_installs(self):
        self.skill('real','project');self.skill('dependency','project/node_modules/pkg')
        wrong=self.workspace/'wrong'/'.agent'/'skill'/'demo'/'SKILL.md';wrong.parent.mkdir(parents=True);wrong.write_text('fixture')
        state=self.update();self.assertEqual(len(state['snapshot']),1)
    def test_legacy_migration_preserves_records_without_fake_install_remove(self):
        path=self.skill('same','old-project')
        legacysettings={**self.settings,'project_scan_roots':[],'skill_roots':[{'path':str(path.parent.parent),'label':'old','scope':'global'}]}
        snapshot=L.scan(legacysettings,{})
        old={'schema':1,'created':L.now(),'last_scan':L.now(),'snapshot':snapshot,'events':[{'name':'same','action':'新增','time':L.now(),'skill':snapshot['same'],'detail':'fixture'}]}
        S.write(self.base/'.data'/'ledger.json',old)
        current=self.update();self.assertEqual(len(current['events']),1);self.assertEqual(current['events'][0]['action'],'新增')
        self.assertIn('@@project-',current['events'][0]['name']);self.assertEqual(current['scope_schema'],1)
        self.assertEqual(len(self.update()['events']),1)
    def test_unavailable_known_workspace_does_not_fabricate_uninstall(self):
        self.skill('same','project');old=self.update()
        moved=self.workspace.with_name('offline');self.workspace.rename(moved)
        S.invalidate(self.base)
        with self.assertRaisesRegex(RuntimeError,'不可访问'):self.update()
        self.assertEqual(L.read_json(self.base/'.data'/'ledger.json'),old)
    def test_adding_watch_folder_updates_scope_even_with_no_skills(self):
        self.update();before=self.payload()['revision'];other=self.base/'other-project';other.mkdir()
        S.add_project(self.base,str(other));self.update();payload=self.payload()
        self.assertNotEqual(before,payload['revision'])
        self.assertTrue(any(r['scope_label']=='other-project' for r in payload['discovery']['scopes']))
    def test_configured_project_survives_whole_skill_folder_removal(self):
        path=self.skill('gone','project');self.update();path.unlink();path.parent.rmdir();path.parent.parent.rmdir()
        state=self.update(True);self.assertEqual(state['events'][-1]['action'],'移除')
        self.assertEqual(self.payload()['skills'][0]['display_status'],'已卸载')
    def test_authenticated_project_api_adds_root_and_returns_fresh_payload(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        self.update();other=self.base/'outside';skill=other/'.agents'/'skills'/'new'/'SKILL.md'
        skill.parent.mkdir(parents=True);skill.write_text('---\nname: new\ndescription: Demo\n---\nDemo',encoding='utf-8')
        server=M.serve(self.base,catalog=False)
        try:
            connection=L.read_json(self.base/'.data'/'connection.json')
            def call(route,body,token=connection['token']):
                req=Request(connection['url']+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Skill-Ledger-Token':token})
                with urlopen(req,timeout=5) as response:return json.load(response)
            with self.assertRaises(HTTPError):call('/api/projects',{'path':str(other)},'wrong')
            self.assertEqual(len(L.read_json(self.base/'设置.json')['project_scan_roots']),1)
            result=call('/api/projects',{'path':str(other)})
            self.assertEqual(result['data']['skills'][0]['skill_name'],'new')
            self.assertEqual(result['data']['skills'][0]['scope_label'],'outside')
            refresh=call('/api/scan/refresh',{})
            self.assertEqual(len(refresh['data']['skills']),1)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
