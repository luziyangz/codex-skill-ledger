param([string]$ToolDirectory=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$toolDirectory=[IO.Path]::GetFullPath($ToolDirectory)
$launcher=Join-Path $toolDirectory 'launch.py'
if(-not(Test-Path -LiteralPath $launcher)){throw 'launch.py is missing.'}
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
$runtime=Get-SkilunePython
$desktop=[Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory,[Environment+SpecialFolderOption]::DoNotVerify)
$programs=[Environment]::GetFolderPath([Environment+SpecialFolder]::Programs,[Environment+SpecialFolderOption]::DoNotVerify)
$shell=New-Object -ComObject WScript.Shell
$entries=@(@{Directory=$desktop;Name='Skilune 技序.lnk';Legacy='技能台账.lnk'},@{Directory=$programs;Name='Skilune 技序.lnk';Legacy='技能台账 Skill Ledger.lnk'})
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
    $legacyPath=[IO.Path]::GetFullPath((Join-Path $directory $entry.Legacy))
    if([IO.Path]::GetDirectoryName($legacyPath) -ne $directory){throw 'Invalid legacy shortcut path.'}
    if(Test-Path -LiteralPath $legacyPath){
        $legacy=$shell.CreateShortcut($legacyPath)
        if($legacy.Arguments.Contains($launcher)){
            if(Test-Path -LiteralPath $shortcutPath){Remove-Item -LiteralPath $legacyPath}
            else{Move-Item -LiteralPath $legacyPath -Destination $shortcutPath}
        }
    }
    [void][IO.Directory]::CreateDirectory($directory)
    $shortcut=$shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath=$runtime
    $shortcut.Arguments='"{0}"' -f $launcher
    $shortcut.WorkingDirectory=$toolDirectory
    $shortcut.WindowStyle=7
    $brandIcon=Join-Path $toolDirectory 'brand\app.ico'
    $shortcut.IconLocation=if(Test-Path -LiteralPath $brandIcon){$brandIcon+',0'}else{(Join-Path $env:WINDIR 'System32\shell32.dll')+',70'}
    $shortcut.Description='Skilune · 技序'
    $shortcut.Save()
    $verify=$shell.CreateShortcut($shortcutPath)
    if($verify.TargetPath -ne $runtime -or $verify.Arguments -ne $shortcut.Arguments){throw 'Shortcut verification failed.'}
    $created+=$shortcutPath
}
$created|ForEach-Object {Write-Output $_}
