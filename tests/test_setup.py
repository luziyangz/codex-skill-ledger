import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skill_setup as setup
import skill_ledger as ledger


class SetupTests(unittest.TestCase):
    def test_empty_machine_then_new_install_then_missing_required_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home'
            codex = home / '.codex'
            base = root / 'app'
            original = setup.defaults
            with patch.object(setup, 'defaults', side_effect=lambda: original(home, codex)):
                setup.ensure(base)
                self.assertEqual(ledger.update(base, False)['new_events'], 0)
                skill = codex / 'skills' / 'demo' / 'SKILL.md'
                skill.parent.mkdir(parents=True)
                skill.write_text('---\nname: demo\ndescription: fixture\n---\nExample', encoding='utf-8')
                self.assertEqual(ledger.update(base, False)['new_events'], 1)
                self.assertTrue(json.loads((base / '设置.json').read_text(encoding='utf-8'))['skill_roots'][0]['required'])
                skill.unlink()
                skill.parent.rmdir()
                skill.parent.parent.rmdir()
                previous = (base / '.data' / 'ledger.json').read_bytes()
                with self.assertRaises(RuntimeError):
                    ledger.update(base, False)
                self.assertEqual((base / '.data' / 'ledger.json').read_bytes(), previous)

    def test_setup_preserves_existing_settings_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(setup, 'defaults', return_value=setup.defaults(base / 'home', base / 'home' / '.codex')):
                setup.ensure(base)
            reference = base / '.data' / 'reference.json'
            reference.write_text('{"custom":{"category":"My category"}}', encoding='utf-8')
            history = base / '.data' / '历史导入.json'
            history.write_text('[{"fixture":true}]', encoding='utf-8')
            setup.ensure(base)
            self.assertIn('custom', json.loads(reference.read_text(encoding='utf-8')))
            self.assertEqual(json.loads(history.read_text(encoding='utf-8')), [{'fixture': True}])


if __name__ == '__main__':
    unittest.main()
