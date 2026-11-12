$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        uv venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    uv pip install --python .venv\Scripts\python.exe -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
} finally { Pop-Location }
