@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

where python >nul 2>nul || goto missing_python
where node >nul 2>nul || goto missing_node
where npm >nul 2>nul || goto missing_node

python -c "import uvicorn" >nul 2>nul || goto bootstrap
if not exist "%ROOT%src\frontend\node_modules\.bin\vite.cmd" goto bootstrap

:launch
python "%ROOT%scripts\launch.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo CartridgeFlow exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:bootstrap
echo Installing CartridgeFlow dependencies with the system Python and Node.js...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap.ps1"
if errorlevel 1 goto setup_failed
goto launch

:missing_python
echo Python is required but was not found in PATH.
pause
exit /b 1

:missing_node
echo Node.js and npm are required but were not found in PATH.
pause
exit /b 1

:setup_failed
echo Dependency setup failed. Review the error above and try again.
pause
exit /b 1
