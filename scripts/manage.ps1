param([ValidateSet('Open','Start','InstallStartup','StopRemove')][string]$Action='Open')
$ErrorActionPreference='Stop'
$toolDirectory=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$scriptPath=Join-Path $toolDirectory 'skill_ledger.py'
$hashProvider=[Security.Cryptography.SHA256]::Create()
try {$installId=([BitConverter]::ToString($hashProvider.ComputeHash([Text.Encoding]::UTF8.GetBytes($toolDirectory.ToLowerInvariant())))).Replace('-','').Substring(0,10)} finally {$hashProvider.Dispose()}
$startupDirectory=[Environment]::GetFolderPath('Startup')
$shortcutPath=[IO.Path]::GetFullPath((Join-Path $startupDirectory ('Codex Skill Ledger '+$installId+'.lnk')))
if([IO.Path]::GetDirectoryName($shortcutPath) -ne [IO.Path]::GetFullPath($startupDirectory)){throw 'Invalid startup path.'}

if($Action -eq 'StopRemove'){
    $statusPath=Join-Path $toolDirectory '.data\connection.json'
    if(Test-Path -LiteralPath $statusPath){
        $status=Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8|ConvertFrom-Json
        $monitor=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$status.pid) -ErrorAction SilentlyContinue
        if($monitor -and $monitor.CommandLine -and $monitor.CommandLine.Contains($scriptPath) -and $monitor.CommandLine.Contains('--watch')){Stop-Process -Id ([int]$status.pid)}
    }
    if(Test-Path -LiteralPath $shortcutPath){
        $shell=New-Object -ComObject WScript.Shell
        $shortcut=$shell.CreateShortcut($shortcutPath)
        if(-not $shortcut.Arguments.Contains((Join-Path $PSScriptRoot 'manage.ps1'))){throw 'Shortcut belongs to another installation.'}
        Remove-Item -LiteralPath $shortcutPath
    }
    Write-Host 'Background recording stopped; startup removed. Records are retained.'
    exit
}

if($Action -eq 'InstallStartup'){
    $shell=New-Object -ComObject WScript.Shell
    $shortcut=$shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath=Join-Path $PSHOME 'powershell.exe'
    $shortcut.Arguments='-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Action Start' -f (Join-Path $PSScriptRoot 'manage.ps1')
    $shortcut.WorkingDirectory=$toolDirectory
    $shortcut.WindowStyle=7
    $shortcut.Description='Local Codex skill inventory and change history'
    $shortcut.Save()
    Write-Host 'Startup recording enabled for the current user. Starting now.'
}

$runtime=$null
foreach($name in @('pythonw.exe','python.exe','python3.exe')){
    $candidate=Get-Command $name -ErrorAction SilentlyContinue
    if($candidate -and $candidate.Source -notlike '*\WindowsApps\*'){$runtime=$candidate.Source;break}
}
if(-not $runtime){
    $candidate=Join-Path $HOME '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
    if(Test-Path -LiteralPath $candidate){$runtime=$candidate}
}
if(-not $runtime){throw 'Python 3.11+ was not found. Install Python and add it to PATH.'}
$arguments='"{0}" --watch --quiet' -f $scriptPath
if($Action -eq 'Open'){$arguments='"{0}"' -f (Join-Path $toolDirectory 'launch.py')}
Start-Process -FilePath $runtime -ArgumentList $arguments -WorkingDirectory $toolDirectory -WindowStyle Hidden
