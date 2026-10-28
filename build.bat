@echo off
REM Build a distributable app with PyInstaller (see locarc.spec).
REM Builds under %TEMP% and then copies to .\dist (robocopy) so repeated builds
REM don't get blocked by OneDrive file locks inside the project folder.
cd /d %~dp0
if not exist .venv (
  echo [setup] creating venv...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements-dev.txt

set BUILD=%TEMP%\locarc-build
if exist "%BUILD%" rmdir /s /q "%BUILD%"

python -m PyInstaller --noconfirm --clean ^
  --workpath "%BUILD%\work" --distpath "%BUILD%\dist" ^
  locarc.spec
if errorlevel 1 goto :error

robocopy "%BUILD%\dist\LocArc" ".\dist\LocArc" /E /PURGE /MT:8 /NFL /NDL /NJH /NJS
if errorlevel 8 goto :error
rmdir /s /q "%BUILD%"

echo.
echo Done: dist\LocArc\LocArc.exe
echo Tip: verify it with  powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
goto :eof

:error
echo BUILD FAILED
if not defined CI pause
exit /b 1
