"""Windows startup tests. Shortcuts are created only inside temporary folders."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == 'nt', 'Windows shortcut integration')
class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='skilune-startup-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / '示例 project'
        self.base.mkdir()
        (self.base / 'skill_ledger.py').write_text('# fixture only', encoding='utf-8')
        self.startup = Path(self.temp.name) / 'fake-startup'
        self.startup.mkdir()
        self.runtime = Path(sys.executable)
        self.prefix = (
            "$ErrorActionPreference='Stop'\n"
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)\n"
            f". {ps_string(ROOT / 'scripts' / 'startup-plan.ps1')}\n"
            f". {ps_string(ROOT / 'scripts' / 'python-runtime.ps1')}\n"
            f"$base={ps_string(self.base)}\n"
            f"$runtime={ps_string(self.runtime)}\n"
            f"$startup={ps_string(self.startup)}\n"
        )

    def ps(self, code):
        script = Path(self.temp.name) / 'check.ps1'
        script.write_text(self.prefix + code, encoding='utf-8-sig')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script)],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        return json.loads(result.stdout.decode('utf-8-sig'))

    def test_plan_is_direct_python_and_creates_nothing(self):
        plan = self.ps('Get-SkiluneStartupPlan $base $runtime $startup | ConvertTo-Json -Compress')
        self.assertEqual(Path(plan['TargetPath']), self.runtime)
        self.assertEqual(plan['Arguments'], f'"{self.base / "skill_ledger.py"}" --base "{self.base}" --watch --quiet')
        self.assertEqual(Path(plan['Path']).parent, self.startup)
        self.assertNotIn('powershell', plan['Arguments'].lower())
        self.assertNotIn('bypass', plan['Arguments'].lower())
        self.assertEqual(list(self.startup.iterdir()), [])

    def test_runtime_validation_and_missing_candidate(self):
        value = self.ps("""
$selected=Get-SkilunePython -Candidates @((Join-Path $base 'missing.exe'),$runtime)
$console=Join-Path (Split-Path -Parent $selected) 'python.exe'
$version=& $console -I -c 'import sys; print(int(sys.version_info >= (3, 11)))'
$failed=$false
try {Get-SkilunePython -Candidates @((Join-Path $base 'missing.exe')) | Out-Null} catch {$failed=$true}
@{valid=($version -eq '1');missingRejected=$failed} | ConvertTo-Json
""")
        self.assertEqual(value, {'valid': True, 'missingRejected': True})

    def test_missing_runtime_or_script_fails_before_creation(self):
        value = self.ps(r"""
$failures=0
try {Get-SkiluneStartupPlan $base (Join-Path $base 'missing-python.exe') $startup | Out-Null} catch {$failures++}
Remove-Item -LiteralPath (Join-Path $base 'skill_ledger.py')
try {Get-SkiluneStartupPlan $base $runtime $startup | Out-Null} catch {$failures++}
$failures | ConvertTo-Json
""")
        self.assertEqual(value, 2)
        self.assertEqual(list(self.startup.iterdir()), [])

    def test_rejects_relative_and_network_paths(self):
        value = self.ps(r"""
$failures=0
try {Get-SkiluneStartupPlan '.' $runtime $startup | Out-Null} catch {$failures++}
try {Get-SkiluneStartupPlan '\\server\share' $runtime $startup | Out-Null} catch {$failures++}
$failures | ConvertTo-Json
""")
        self.assertEqual(value, 2)

    def test_shortcut_roundtrip_only_in_temporary_directory(self):
        owned = self.ps("""
$plan=Get-SkiluneStartupPlan $base $runtime $startup
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($plan.Path)
$link.TargetPath=$plan.TargetPath
$link.Arguments=$plan.Arguments
$link.WorkingDirectory=$plan.WorkingDirectory
$link.Save()
$read=$shell.CreateShortcut($plan.Path)
Test-SkiluneStartupOwnership $read $base | ConvertTo-Json
""")
        self.assertTrue(owned)

    def test_unrelated_or_modified_shortcuts_are_not_owned(self):
        results = self.ps(r"""
$plan=Get-SkiluneStartupPlan $base $runtime $startup
$link=[pscustomobject]@{TargetPath=$runtime;Arguments=$plan.Arguments;WorkingDirectory=$base}
$checks=@((Test-SkiluneStartupOwnership $link $base))
$link.Arguments+=' --extra'
$checks+=Test-SkiluneStartupOwnership $link $base
$link.Arguments=$plan.Arguments
$link.WorkingDirectory=Split-Path -Parent $base
$checks+=Test-SkiluneStartupOwnership $link $base
$link.WorkingDirectory=$base
$link.TargetPath=Join-Path $env:WINDIR 'System32\cmd.exe'
$checks+=Test-SkiluneStartupOwnership $link $base
$checks | ConvertTo-Json
""")
        self.assertEqual(results, [True, False, False, False])

    def test_exact_legacy_signature_recognized_for_cleanup(self):
        results = self.ps(r"""
$policy='-ExecutionPolicy Bypass'
$link=[pscustomobject]@{
 TargetPath=(Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe')
 Arguments=('-NoProfile -NonInteractive -WindowStyle Hidden {0} -File "{1}"' -f $policy,(Join-Path $base '启动后台记录.ps1'))
 WorkingDirectory=$base
}
$checks=@((Test-SkiluneStartupOwnership $link $base))
$link.Arguments+=' -OtherCommand'
$checks+=Test-SkiluneStartupOwnership $link $base
$checks | ConvertTo-Json
""")
        self.assertEqual(results, [True, False])


if __name__ == '__main__':
    unittest.main()
