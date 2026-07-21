@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set "PYTHON_DIR=%ROOT%.tools\runtimes\python"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "NODE_DIR=%ROOT%.tools\runtimes\node"

if not exist "%PYTHON_EXE%" goto bootstrap
if not exist "%NODE_DIR%\node.exe" goto bootstrap
if not exist "%PYTHON_DIR%\Lib\site-packages\uvicorn" goto bootstrap
if not exist "%ROOT%src\frontend\node_modules\.bin\vite.cmd" goto bootstrap

:launch
set "PATH=%NODE_DIR%;%PATH%"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%PYTHON_EXE%" "%ROOT%scripts\launch.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo CartridgeFlow exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:bootstrap
echo First run: installing the project-local Python and Node.js runtimes...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap.ps1"
if errorlevel 1 goto setup_failed
goto launch

:setup_failed
echo Runtime setup failed. Review the error above and try again.
pause
exit /b 1
