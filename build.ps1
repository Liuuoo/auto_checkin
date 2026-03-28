$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "===== Build GitHubCheckinTool ====="
Write-Host ""

Write-Host "[1/3] Install project dependencies..."
py -3 -m pip install -r requirements.txt

Write-Host ""
Write-Host "[2/3] Install PyInstaller..."
py -3 -m pip install pyinstaller

Write-Host ""
Write-Host "[3/3] Build executable..."
py -3 -m PyInstaller --noconfirm --clean --onefile --noconsole --name GitHubCheckinTool gui_app.py

Write-Host ""
if (Test-Path ".\dist\GitHubCheckinTool.exe") {
    Write-Host "Build succeeded"
    Write-Host "Output: dist\GitHubCheckinTool.exe"
} else {
    Write-Host "Build completed but output file was not found."
    exit 1
}
