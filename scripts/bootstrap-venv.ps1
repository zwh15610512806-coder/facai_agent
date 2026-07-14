$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Lock = Join-Path $Root "requirements.lock"

if (-not (Test-Path $Lock)) {
    throw "requirements.lock is missing; dependency resolution must be reviewed before bootstrap"
}
if (-not (Test-Path $Python)) {
    $BasePython = (Get-Command python -ErrorAction Stop).Source
    $Version = & $BasePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($Version -ne "3.12") { throw "Python 3.12 is required; found $Version at $BasePython" }
    & $BasePython -m venv $Venv
}

& $Python -m pip install --upgrade "pip==26.1.2"
& $Python -m pip install --require-hashes -r $Lock
if ($LASTEXITCODE -ne 0) { throw "Locked dependency installation failed" }

$Digest = (Get-FileHash -Algorithm SHA256 $Lock).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $Venv ".facai-requirements.sha256") -Value $Digest -Encoding ascii
& $Python (Join-Path $Root "scripts\verify_runtime.py")
