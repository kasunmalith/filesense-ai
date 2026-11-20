$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Install Python 3.12 x64 from python.org before building."
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}

$python = Resolve-Path -LiteralPath ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[semantic,image-ai,spreadsheet,duplicates,chat,build]"
& $python -m PyInstaller --noconfirm --clean .\FileSenseAI.spec

$executable = Join-Path (Get-Location) "dist\FileSenseAI\FileSenseAI.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "PyInstaller completed without producing the expected executable: $executable"
}
Write-Host "Build complete: $executable"
Write-Host "Model weights and user data are stored outside this directory in the per-user app-data folder."
