import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch

W=Path(__file__).resolve().parent.parent;B=W
sys.path.insert(0,str(B))
import skill_ledger as L
import skill_manager as S

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=W/'tests');self.base=Path(self.temp.name)
        (self.base/'.data').mkdir();self.root=self.base/'skills';self.root.mkdir();self.cache=self.base/'cache';self.cache.mkdir()
        self.config=self.base/'config.toml';self.config.write_text('',encoding='utf-8')
        self.settings={'codex_config':str(self.config),'skill_roots':[{'path':str(self.root),'label':'test'}],'plugin_cache':str(self.cache),'known_plugins':['demo'],'plugin_cli':sys.executable}
        self.save();(self.base/'.data'/'reference.json').write_text('{}',encoding='utf-8');(self.base/'.data'/'历史导入.json').write_text('[]',encoding='utf-8')
        (self.base/'查看记录.template.html').write_text('<script id="data">__DATA__</script>',encoding='utf-8')
        self.skill('one');self.skill('two');L.update(self.base,False);self.manager=S.Manager(self.base)
    def tearDown(self):
        assert self.base.resolve().is_relative_to((W/'tests').resolve());self.temp.cleanup()
    def save(self):(self.base/'设置.json').write_text(json.dumps(self.settings),encoding='utf-8')
    def skill(self,name,parent=None):
        path=(parent or self.root)/name/'SKILL.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('---\nname: '+name+'\ndescription: demo\n---\nDemo',encoding='utf-8');return path
    def store(self):return L.read_json(self.base/'.data'/'ledger.json')
    def test_preview_has_no_side_effect_and_single_uninstall_has_real_time_and_backup(self):
        before=self.store();plan=self.manager.preview(['one'])
        self.assertTrue((self.root/'one'/'SKILL.md').exists());self.assertEqual(before,self.store());self.assertEqual(plan['count'],1)
        result=self.manager.commit(plan['id']);self.assertTrue(result['results'][0]['ok']);self.assertFalse((self.root/'one').exists());self.assertTrue((self.root/'two').exists())
        event=self.store()['events'][-1];self.assertEqual(event['action'],'卸载');self.assertEqual(event['time'],event['occurred_at']);self.assertTrue(Path(event['recovery'][0]['backup'],'SKILL.md').exists())
        self.assertEqual(L.registry(self.store(),{})[0]['status'],'已卸载')
    def test_batch_uninstall_and_no_duplicate_detection_events(self):
        plan=self.manager.preview(['one','two','one']);result=self.manager.commit(plan['id'])
        self.assertEqual(len(result['results']),2);self.assertEqual([e['action'] for e in self.store()['events']],['卸载','卸载'])
        self.assertEqual(L.update(self.base,False)['new_events'],0)
    def test_changed_snapshot_rejects_stale_confirmation(self):
        plan=self.manager.preview(['one']);self.skill('new')
        with self.assertRaisesRegex(ValueError,'发生变化'):self.manager.commit(plan['id'])
        self.assertTrue((self.root/'one').exists())
    def test_protected_and_unknown_names_cannot_be_removed(self):
        self.skill('protected',self.root/'.system');plan=self.manager.preview(['protected','../../outside'])
        self.assertEqual(plan['count'],0);self.assertEqual(len(plan['blocked']),2);self.assertTrue((self.root/'.system'/'protected').exists())
    def test_failed_group_is_reported_and_other_groups_can_complete(self):
        plan=self.manager.preview(['one','two']);real_move=shutil.move
        def fail_one(source,dest):
            if Path(source)==self.root/'one':raise PermissionError('locked')
            return real_move(source,dest)
        with patch.object(S.shutil,'move',side_effect=fail_one):result=self.manager.commit(plan['id'])
        self.assertFalse(result['results'][0]['ok']);self.assertTrue(result['results'][1]['ok']);self.assertTrue((self.root/'one').exists())
        self.assertEqual([e['name'] for e in self.store()['events']],['two'])
    def test_multiple_copies_are_all_removed_and_backup_receipt_kept(self):
        second=self.base/'other';second.mkdir();self.skill('one',second);self.settings['skill_roots'].append({'path':str(second),'label':'other'});self.save();L.update(self.base,False)
        plan=self.manager.preview(['one']);self.manager.commit(plan['id'])
        self.assertFalse((second/'one').exists());self.assertFalse((self.root/'one').exists())
        event=self.store()['events'][-1];self.assertEqual(len(event['recovery']),2)
        self.assertEqual(len(list((self.base/'.data'/'uninstall-backups').glob('*/receipt.json'))),1)
    def test_new_plugin_is_discovered_from_installation_catalog(self):
        package=self.cache/'market'/'brandnew'/'1.0';(package/'.codex-plugin').mkdir(parents=True);(package/'.codex-plugin'/'plugin.json').write_text('{"skills":"./skills"}',encoding='utf-8');self.skill('feature',package/'skills')
        L.update(self.base,False);self.assertEqual(self.store()['snapshot']['brandnew:feature']['state'],'缓存待核对')
        (self.base/'.data'/'installed-plugins.json').write_text(json.dumps({'installed':[{'id':'brandnew@market','name':'brandnew'}]}),encoding='utf-8')
        L.update(self.base,False);self.assertEqual(self.store()['snapshot']['brandnew:feature']['state'],'已登记')
        self.assertEqual(self.store()['events'][-1]['action'],'新增')
        self.assertFalse(L.registry(self.store(),{})[0]['lifecycle']['present_at_baseline'])
    def test_partial_catalog_keeps_confirmed_installs_until_complete_result(self):
        full={'installed':[{'pluginId':'fresh@market','name':'fresh','installed':True}]}
        with patch.object(S,'run_cli',return_value=(full,'')):S.refresh_catalog(self.base)
        self.assertIn('fresh',S.configured(self.base)['known_plugins'])
        with patch.object(S,'run_cli',return_value=({'installed':[]},'failed to list remote marketplace')):S.refresh_catalog(self.base)
        self.assertIn('fresh',S.configured(self.base)['known_plugins'])
        self.assertFalse(L.read_json(self.base/'.data'/'installed-plugins.json')['complete'])
        with patch.object(S,'run_cli',return_value=({'installed':[]},'')):S.refresh_catalog(self.base)
        self.assertNotIn('fresh',S.configured(self.base)['known_plugins'])
    def test_failure_in_second_copy_rolls_back_first_copy(self):
        second=self.base/'other';second.mkdir();self.skill('one',second);self.settings['skill_roots'].append({'path':str(second),'label':'other'});self.save();L.update(self.base,False)
        plan=self.manager.preview(['one']);paths=self.manager.plans[plan['id']]['groups'][0]['paths'];blocked=Path(paths[1]);real_move=shutil.move
        def move(source,dest):
            if Path(source)==blocked:raise PermissionError('locked second copy')
            return real_move(source,dest)
        with patch.object(S.shutil,'move',side_effect=move):result=self.manager.commit(plan['id'])
        self.assertFalse(result['results'][0]['ok']);self.assertTrue((self.root/'one'/'SKILL.md').exists());self.assertTrue((second/'one'/'SKILL.md').exists())
        self.assertFalse(any(e['action']=='卸载' for e in self.store()['events']))
    def test_plugin_preview_expands_all_its_skills_and_uses_official_cli(self):
        package=self.cache/'market'/'demo'/'1.0';(package/'.codex-plugin').mkdir(parents=True);(package/'.codex-plugin'/'plugin.json').write_text('{"skills":"./skills"}',encoding='utf-8');self.skill('a',package/'skills');self.skill('b',package/'skills');L.update(self.base,False)
        plan=self.manager.preview(['demo:a']);self.assertEqual(plan['count'],2);self.assertEqual(plan['groups'][0]['names'],['demo:a','demo:b'])
        self.assertEqual(plan['selected_names'],['demo:a']);self.assertEqual(plan['extra_names'],['demo:b'])
        def remove(settings,args,timeout):
            self.assertEqual(args,['remove','demo@market','--json']);shutil.rmtree(package);return {},''
        with patch.object(S,'run_cli',side_effect=remove):result=self.manager.commit(plan['id'])
        self.assertTrue(result['results'][0]['ok']);self.assertEqual([e['name'] for e in self.store()['events'] if e['action']=='卸载'],['demo:a','demo:b'])
    def test_double_commit_does_not_repeat_uninstall(self):
        plan=self.manager.preview(['one']);first=self.manager.commit(plan['id'])
        self.assertEqual(first,self.manager.commit(plan['id']))
        self.assertEqual(len(self.store()['events']),1)
        self.assertTrue(all(row['display_status'] in ('已安装','已卸载') for row in first['data']['skills']))
    def test_disabled_skill_is_installed_and_csv_matches_display(self):
        path=self.root/'one'/'SKILL.md'
        self.config.write_text("[[skills.config]]\npath = '"+str(path)+"'\nenabled = false\n",encoding='utf-8');L.update(self.base,False)
        plan=self.manager.preview(['two']);result=self.manager.commit(plan['id'])
        rows={r['name']:r for r in result['data']['skills']}
        self.assertEqual(rows['one']['display_status'],'已安装');self.assertTrue(rows['one']['installed'])
        self.assertEqual(rows['two']['display_status'],'已卸载');self.assertFalse(rows['two']['installed'])
        import csv
        with (self.base/'当前技能.csv').open(encoding='utf-8-sig',newline='') as stream:
            exported={r['名称']:r['状态'] for r in csv.DictReader(stream)}
        self.assertEqual(exported,{'one':'已安装','two':'已卸载'})
    def test_preview_blocks_package_containing_protected_child(self):
        self.skill('package');self.skill('protected',self.root/'package'/'.system')
        plan=self.manager.preview(['package'])
        self.assertEqual(plan['count'],0);self.assertEqual(plan['blocked'][0]['name'],'package')
        self.assertTrue((self.root/'package'/'SKILL.md').exists())
    def test_bundled_and_canonical_components_are_identified_before_confirmation(self):
        for origin in ('sites@openai-curated-remote','work-pets@openai-curated-remote','template-creator@openai-primary-runtime','computer-use@openai-bundled'):
            cap=S.capability({'name':origin.split('@')[0]+':demo','state':'配置停用','origin':origin,'paths':[]},self.settings)
            self.assertEqual(cap['kind'],'none');self.assertIn('内置',cap['reason'])
    def test_http_authentication_origin_and_real_uninstall_route(self):
        server=S.serve(self.base,catalog=False)
        try:
            connection=L.read_json(self.base/'.data'/'connection.json');url=connection['url'];token=connection['token']
            def call(route,body=None,origin='null',access=token,host=None):
                headers={'Origin':origin,'X-Skill-Ledger-Token':access}
                if host:headers['Host']=host
                if body is not None:headers['Content-Type']='application/json'
                req=Request(url+route,data=json.dumps(body).encode() if body is not None else None,headers=headers)
                with urlopen(req,timeout=3) as response:return json.load(response)
            self.assertIn('skills',call('/api/data'))
            for kwargs in ({'access':'wrong'},{'origin':'https://untrusted.example'},{'host':'untrusted.example'}):
                with self.assertRaises(HTTPError) as error:call('/api/data',**kwargs)
                self.assertEqual(error.exception.code,403)
            with self.assertRaises(HTTPError):call('/.data/connection.js')
            with self.assertRaises(HTTPError):call('/../%E8%AE%BE%E7%BD%AE.json')
            plan=call('/api/uninstall/preview',{'names':['one']});self.assertTrue((self.root/'one').exists())
            result=call('/api/uninstall/commit',{'id':plan['id']});self.assertTrue(result['results'][0]['ok']);self.assertFalse((self.root/'one').exists())
            self.assertEqual(call('/api/data')['events'][-1]['time_label'],'操作时间')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
