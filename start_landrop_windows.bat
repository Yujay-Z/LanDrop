@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 landrop_web.py
  goto done
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python landrop_web.py
  goto done
)

echo Python was not found.
echo Install Python 3 from https://www.python.org/downloads/windows/
echo Then double-click this file again.

:done
pause
