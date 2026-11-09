@echo off
rem Runs PortMasterForwarder from the source tree (Python 3.9+ required).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import PIL" 2>nul || %PY% -m pip install --quiet -r requirements.txt
set PYTHONPATH=%~dp0src
%PY% -m portmasterforwarder
if errorlevel 1 pause
