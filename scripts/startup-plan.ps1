# Pure planning and ownership checks. Loading this file never creates an entry.
function Get-SkiluneStartupPlan {
    param([string]$ToolDirectory,[string]$Runtime,[string]$StartupDirectory)
    foreach($path in @($ToolDirectory,$Runtime,$StartupDirectory)) {
        if(-not [IO.Path]::IsPathRooted($path)){throw 'An absolute local path is required.'}
        if($path.StartsWith('\\')){throw 'Network paths are not supported for startup.'}
    }
    $base=[IO.Path]::GetFullPath($ToolDirectory)
    $python=[IO.Path]::GetFullPath($Runtime)
    $directory=[IO.Path]::GetFullPath($StartupDirectory)
    $script=Join-Path $base 'skill_ledger.py'
    if(-not(Test-Path -LiteralPath $python -PathType Leaf)){throw 'Python runtime is missing.'}
    if([IO.Path]::GetFileName($python) -notin @('python.exe','pythonw.exe','python3.exe')){throw 'A Python runtime is required.'}
    if(-not(Test-Path -LiteralPath $script -PathType Leaf)){throw 'skill_ledger.py is missing.'}
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$id=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($base.ToLowerInvariant())))).Replace('-','').Substring(0,10)} finally {$hash.Dispose()}
    # Retain the existing per-installation name and Windows Startup location.
    $shortcut=Join-Path $directory ('Codex Skill Ledger '+$id+'.lnk')
    [pscustomobject]@{
        Path=$shortcut
        TargetPath=$python
        Arguments='"{0}" --base "{1}" --watch --quiet' -f $script,$base
        WorkingDirectory=$base
        Description='Skilune - local skill change recording'
    }
}

function Test-SkiluneStartupOwnership {
    param($Shortcut,[string]$ToolDirectory)
    $base=[IO.Path]::GetFullPath($ToolDirectory)
    if($Shortcut.WorkingDirectory -ne $base){return $false}
    $script=Join-Path $base 'skill_ledger.py'
    $pythonName=[IO.Path]::GetFileName($Shortcut.TargetPath)
    $directArguments=@(('"{0}" --base "{1}" --watch --quiet' -f $script,$base),('"{0}" --watch --quiet' -f $script))
    if($pythonName -in @('python.exe','pythonw.exe','python3.exe') -and $Shortcut.Arguments -in $directArguments){return $true}
    $powershell=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if($Shortcut.TargetPath -ne $powershell){return $false}
    # Legacy signatures are only recognized for removal, never for creation.
    $policy='-ExecutionPolicy Bypass'
    $oldManage=Join-Path $base 'scripts\manage.ps1'
    $oldLauncher=Join-Path $base '启动后台记录.ps1'
    $legacyArguments=@(
        ('-NoProfile {0} -WindowStyle Hidden -File "{1}" -Action Start' -f $policy,$oldManage),
        ('-NoProfile -NonInteractive -WindowStyle Hidden {0} -File "{1}"' -f $policy,$oldLauncher)
    )
    return $Shortcut.Arguments -in $legacyArguments
}
