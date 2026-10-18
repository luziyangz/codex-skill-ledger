[CmdletBinding(SupportsShouldProcess=$true)]
param([ValidateSet('Open','Start','InstallStartup','StopRemove')][string]$Action='Open')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'startup-plan.ps1')
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
$toolDirectory=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$scriptPath=Join-Path $toolDirectory 'skill_ledger.py'
$startupDirectory=[Environment]::GetFolderPath('Startup')
if(-not $startupDirectory){throw 'Windows Startup directory is unavailable.'}

if($Action -eq 'StopRemove'){
    $shell=New-Object -ComObject WScript.Shell
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$id=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($toolDirectory.ToLowerInvariant())))).Replace('-','').Substring(0,10)} finally {$hash.Dispose()}
    foreach($name in @(('Codex Skill Ledger '+$id+'.lnk'),'Codex Skill Ledger.lnk')){
        $path=Join-Path $startupDirectory $name
        if(Test-Path -LiteralPath $path){
            $shortcut=$shell.CreateShortcut($path)
            if(Test-SkiluneStartupOwnership $shortcut $toolDirectory){
                if($PSCmdlet.ShouldProcess($path,'Remove this installation startup entry')){Remove-Item -LiteralPath $path}
            }else{Write-Warning ('Unrelated startup entry retained: '+$path)}
        }
    }
    $statusPath=Join-Path $toolDirectory '.data\connection.json'
    if(Test-Path -LiteralPath $statusPath){
        $status=Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8|ConvertFrom-Json
        $monitor=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$status.pid) -ErrorAction SilentlyContinue
        if($monitor -and $monitor.CommandLine -and $monitor.CommandLine.Contains(('"'+$scriptPath+'"')) -and $monitor.CommandLine.Contains('--watch')){
            if($PSCmdlet.ShouldProcess(('Process '+$status.pid),'Stop this installation recorder')){Stop-Process -Id ([int]$status.pid)}
        }
    }
    if(-not $WhatIfPreference){Write-Host 'Background recording stopped; owned startup entries removed. Records are retained.'}
    return
}

$runtime=Get-SkilunePython
# Validate all paths before creating anything. This call has no side effects.
$plan=Get-SkiluneStartupPlan $toolDirectory $runtime $startupDirectory
if($Action -eq 'InstallStartup'){
    Write-Host ('Program: '+$plan.TargetPath)
    Write-Host ('Arguments: '+$plan.Arguments)
    Write-Host ('Startup entry: '+$plan.Path)
    if($WhatIfPreference){
        [void]$PSCmdlet.ShouldProcess($plan.Path,'Create a direct local Python startup entry')
        return
    }
    $shell=New-Object -ComObject WScript.Shell
    if(Test-Path -LiteralPath $plan.Path){
        $existing=$shell.CreateShortcut($plan.Path)
        if(-not(Test-SkiluneStartupOwnership $existing $toolDirectory)){throw 'Shortcut belongs to another installation.'}
    }
    if(-not $PSCmdlet.ShouldProcess($plan.Path,'Create a direct local Python startup entry')){return}
    $shortcut=$shell.CreateShortcut($plan.Path)
    $shortcut.TargetPath=$plan.TargetPath
    $shortcut.Arguments=$plan.Arguments
    $shortcut.WorkingDirectory=$plan.WorkingDirectory
    $shortcut.Description=$plan.Description
    $icon=Join-Path $toolDirectory 'brand\app.ico'
    if(Test-Path -LiteralPath $icon){$shortcut.IconLocation=$icon+',0'}
    $shortcut.Save()
    $verify=$shell.CreateShortcut($plan.Path)
    if($verify.TargetPath -ne $plan.TargetPath -or $verify.Arguments -ne $plan.Arguments -or $verify.WorkingDirectory -ne $plan.WorkingDirectory){throw 'Startup entry verification failed.'}
    Write-Host 'Startup enabled for the current user. Starting local recording.'
}
$arguments=$plan.Arguments
if($Action -eq 'Open'){$arguments='"{0}"' -f (Join-Path $toolDirectory 'launch.py')}
if($PSCmdlet.ShouldProcess($runtime+' '+$arguments,'Start local Skilune')){
    Start-Process -FilePath $runtime -ArgumentList $arguments -WorkingDirectory $toolDirectory
}
