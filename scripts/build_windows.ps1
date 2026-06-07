$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$PythonBin = if ($env:PYTHON) { $env:PYTHON } else { "py" }
$VenvDir = if ($env:VENV) { $env:VENV } else { ".venv-build" }
$AppName = "LanDrop"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Artifact = "dist\$AppName.exe"

& $PythonBin -m venv $VenvDir
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-build.txt

& $VenvPython -m py_compile landrop.py landrop_core.py landrop_cli.py landrop_web.py test_landrop.py
& $VenvPython -m unittest

& $VenvPython -m PyInstaller --clean --noconfirm --name $AppName --onefile --windowed landrop_web.py

Write-Host "Built $Artifact"
