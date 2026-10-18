import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import launch


class LaunchTests(unittest.TestCase):
    def test_running_service_is_reused(self):
        connection = {'url': 'http://127.0.0.1:12345', 'token': 'fixture-token'}
        with patch.object(launch, 'live_connection', return_value=connection), patch.object(launch, 'start_monitor') as start, patch.object(launch.webbrowser, 'open', return_value=True) as browser:
            self.assertTrue(launch.open_ledger(Path('.')))
            start.assert_not_called()
            browser.assert_called_once_with('http://127.0.0.1:12345/#access=fixture-token')

    def test_stopped_service_starts_once_and_waits_for_health(self):
        connection = {'url': 'http://127.0.0.1:12345', 'token': 'fixture-token'}
        with patch.object(launch, 'live_connection', side_effect=[None, None, connection]), patch.object(launch, 'start_monitor') as start, patch.object(launch.time, 'sleep'), patch.object(launch.webbrowser, 'open', return_value=True) as browser:
            self.assertFalse(launch.open_ledger(Path('.')))
            start.assert_called_once()
            browser.assert_called_once()

    def test_stale_connection_never_opens_dead_url(self):
        with patch.object(launch, 'live_connection', return_value=None), patch.object(launch, 'start_monitor'), patch.object(launch.webbrowser, 'open') as browser:
            with self.assertRaisesRegex(RuntimeError, '后台尚未就绪'):
                launch.open_ledger(Path('.'), timeout=0)
            browser.assert_not_called()

    def test_external_connection_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / '.data').mkdir()
            (base / '.data' / 'connection.json').write_text(json.dumps({'url': 'https://example.com', 'token': 'fixture'}), encoding='utf-8')
            with patch.object(launch, 'build_opener') as opener:
                self.assertIsNone(launch.live_connection(base))
                opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
