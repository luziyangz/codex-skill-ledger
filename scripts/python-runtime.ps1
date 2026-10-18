function Get-SkilunePython {
    param([string[]]$Candidates)
    if(-not $PSBoundParameters.ContainsKey('Candidates')){
        $Candidates=@(foreach($name in @('pythonw.exe','python.exe','python3.exe')){
            Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | ForEach-Object {$_.Source}
        })
        $Candidates+=Join-Path $HOME '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
    }
    foreach($candidate in ($Candidates | Select-Object -Unique)){
        if(-not $candidate -or $candidate -like '*\WindowsApps\*' -or $candidate.StartsWith('\\')){continue}
        if(-not [IO.Path]::IsPathRooted($candidate) -or -not(Test-Path -LiteralPath $candidate -PathType Leaf)){continue}
        $name=[IO.Path]::GetFileName($candidate)
        if($name -notin @('python.exe','pythonw.exe','python3.exe')){continue}
        $console=$candidate
        if($name -eq 'pythonw.exe'){$console=Join-Path (Split-Path -Parent $candidate) 'python.exe'}
        if(-not(Test-Path -LiteralPath $console -PathType Leaf)){continue}
        try {
            $version=& $console -I -c 'import sys; print(int(sys.version_info >= (3, 11)))' 2>$null
            if($LASTEXITCODE -ne 0 -or $version -ne '1'){continue}
        }catch{continue}
        $windowless=Join-Path (Split-Path -Parent $console) 'pythonw.exe'
        if(Test-Path -LiteralPath $windowless -PathType Leaf){return $windowless}
        return $console
    }
    throw 'Python 3.11+ was not found. Install Python and add it to PATH.'
}
