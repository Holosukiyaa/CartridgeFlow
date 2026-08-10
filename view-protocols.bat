@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required but was not found in PATH.
  exit /b 1
)

python "%~dp0scripts\launch_protocol_viewer.py" %*
