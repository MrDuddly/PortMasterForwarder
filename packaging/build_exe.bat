@echo off
rem Builds dist\PortMasterForwarder.exe (run on Windows). See docs\BUILDING.md
setlocal
cd /d "%~dp0.."
where py >nul 2>nul && (set PY=py -3) || (set PY=python)

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail

%PY% -m unittest discover -s tests
if errorlevel 1 goto :fail

%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\portmasterforwarder.spec
if errorlevel 1 goto :fail

dist\PortMasterForwarder.exe --self-test
if errorlevel 1 goto :fail

echo.
echo Built dist\PortMasterForwarder.exe
certutil -hashfile dist\PortMasterForwarder.exe SHA256
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
