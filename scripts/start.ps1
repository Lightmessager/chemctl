$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$projectPythonw = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$env:CHEMCTL_HOME = Join-Path $projectRoot '.chemctl'
$env:CHEMCTL_URL = 'http://127.0.0.1:8765'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Run scripts\install.ps1 first.'
}
New-Item -ItemType Directory -Path $env:CHEMCTL_HOME -Force | Out-Null
$serviceReady = $false
try {
    $health = Invoke-RestMethod "$env:CHEMCTL_URL/api/v1/health" -TimeoutSec 2
    $serviceReady = $health.ok -and $health.data.api -eq 'ok'
} catch { }
if (-not $serviceReady) {
    $apiProcess = Start-Process -FilePath $projectPython -ArgumentList @('-m', 'chemctl', 'serve') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $env:CHEMCTL_HOME 'api.stdout.log') -RedirectStandardError (Join-Path $env:CHEMCTL_HOME 'api.stderr.log')
    Set-Content -LiteralPath (Join-Path $env:CHEMCTL_HOME 'api.pid') -Value $apiProcess.Id
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod "$env:CHEMCTL_URL/api/v1/health" -TimeoutSec 1
            if ($health.ok) { $serviceReady = $true; break }
        } catch { }
        if ($apiProcess.HasExited) { break }
    }
}
if (-not $serviceReady) { throw 'API did not start. Check .chemctl\api.stderr.log.' }
Start-Process -FilePath $projectPythonw -ArgumentList @('-m', 'chemctl.gui') -WorkingDirectory $projectRoot
