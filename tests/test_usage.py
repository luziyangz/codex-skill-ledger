from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import skill_ledger as L

class UsageTests(unittest.TestCase):
    def row(self,name,installed=True,status='已启用',purpose='整理资料'):
        return {'name':name,'installed':installed,'status':status,'purpose':purpose}
    def test_local_example_contains_task_and_input(self):
        info=L.usage_info(self.row('copy-editing'))
        self.assertTrue(info['usage'].startswith('/copy-editing '));self.assertIn('【粘贴文案】',info['usage']);self.assertEqual(info['usage_note'],'')
    def test_plugin_uses_full_qualified_name_and_connection_hint(self):
        info=L.usage_info(self.row('chatcut:voice'))
        self.assertTrue(info['usage'].startswith('/voice '));self.assertIn('chatcut:voice',info['usage_desktop_hint']);self.assertIn('【配音文案和声音要求】',info['usage']);self.assertIn('账号连接',info['usage_connection'])
    def test_disabled_and_removed_have_different_prerequisites(self):
        self.assertIn('开启',L.usage_info(self.row('skill-installer',status='已停用'))['usage_note'])
        self.assertIn('先安装',L.usage_info(self.row('old',installed=False,status='已归档'))['usage_note'])
    def test_new_skill_gets_a_usable_example_without_manual_mapping(self):
        info=L.usage_info(self.row('new-demo',purpose='制作每周销售报告。'))
        self.assertIn('new-demo',info['usage']);self.assertIn('每周销售报告',info['usage']);self.assertIn('【',info['usage'])

if __name__=='__main__':unittest.main(verbosity=2)
