param([string]$ToolDirectory=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$toolDirectory=[IO.Path]::GetFullPath($ToolDirectory)
$launcher=Join-Path $toolDirectory 'launch.py'
if(-not(Test-Path -LiteralPath $launcher)){throw 'launch.py is missing.'}
$runtime=$null
foreach($name in @('pythonw.exe','python.exe','python3.exe')){
    $candidate=Get-Command $name -ErrorAction SilentlyContinue
    if($candidate -and $candidate.Source -notlike '*\WindowsApps\*'){$runtime=$candidate.Source;break}
}
if(-not $runtime){
    $candidate=Join-Path $HOME '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
    if(Test-Path -LiteralPath $candidate){$runtime=$candidate}
}
if(-not $runtime){throw 'Python 3.11+ was not found.'}
$desktop=[Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory,[Environment+SpecialFolderOption]::DoNotVerify)
$programs=[Environment]::GetFolderPath([Environment+SpecialFolder]::Programs,[Environment+SpecialFolderOption]::DoNotVerify)
$shell=New-Object -ComObject WScript.Shell
$entries=@(@{Directory=$desktop;Name='技能台账.lnk'},@{Directory=$programs;Name='技能台账 Skill Ledger.lnk'})
$created=@()
foreach($entry in $entries){
    if(-not $entry.Directory){throw 'Windows shortcut directory is unavailable.'}
    $directory=[IO.Path]::GetFullPath($entry.Directory)
    $shortcutPath=[IO.Path]::GetFullPath((Join-Path $directory $entry.Name))
    if([IO.Path]::GetDirectoryName($shortcutPath) -ne $directory){throw 'Invalid shortcut path.'}
    if(Test-Path -LiteralPath $shortcutPath){
        $existing=$shell.CreateShortcut($shortcutPath)
        if(-not $existing.Arguments.Contains($launcher)){throw 'A shortcut from another installation already uses this name.'}
    }
    [void][IO.Directory]::CreateDirectory($directory)
    $shortcut=$shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath=$runtime
    $shortcut.Arguments='"{0}"' -f $launcher
    $shortcut.WorkingDirectory=$toolDirectory
    $shortcut.WindowStyle=7
    $shortcut.IconLocation=(Join-Path $env:WINDIR 'System32\shell32.dll')+',70'
    $shortcut.Description='技能台账：查看技能、使用方法和安装卸载记录'
    $shortcut.Save()
    $verify=$shell.CreateShortcut($shortcutPath)
    if($verify.TargetPath -ne $runtime -or $verify.Arguments -ne $shortcut.Arguments){throw 'Shortcut verification failed.'}
    $created+=$shortcutPath
}
$created|ForEach-Object {Write-Output $_}
