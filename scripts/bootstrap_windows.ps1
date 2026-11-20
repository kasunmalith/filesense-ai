$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Install the Python 3.12 x64 launcher from python.org, then rerun this script."
}

py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,spreadsheet,duplicates,chat]"
Write-Host "Setup complete. Start FileSense AI with .\.venv\Scripts\python.exe -m filesense_ai"
