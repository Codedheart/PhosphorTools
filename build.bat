@echo off
rem ============================================================================
rem  Builds a share-ready copy of Phosphor Tools that needs NO Python:
rem     PhosphorTools-windows.zip   ->  friends unzip it and run PhosphorTools.exe
rem  Only the person building needs Python (3.10+). Run this on Windows.
rem ============================================================================
cd /d "%~dp0"
setlocal

set "PY="
for %%V in (3.13 3.12 3.11 3.10) do if not defined PY (py -%%V -c "1" >nul 2>&1 && set "PY=py -%%V")
if not defined PY (python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1 && set "PY=python")
if not defined PY (echo Building needs Python 3.10+ from python.org on THIS PC. & pause & exit /b 1)

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1 || rmdir /s /q .venv
)
if not exist .venv\Scripts\python.exe (
  echo Setting up build environment with %PY% ...
  %PY% -m venv .venv || goto :err
)
echo Installing build tools...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q "pyinstaller>=6.3" || goto :err

if not exist phosphor\assets\VT323-Regular.ttf (
  echo Fetching VT323 font...
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing 'https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf' -OutFile 'phosphor\assets\VT323-Regular.ttf'; Invoke-WebRequest -UseBasicParsing 'https://github.com/google/fonts/raw/main/ofl/vt323/OFL.txt' -OutFile 'phosphor\assets\VT323-OFL.txt' } catch { Write-Host '  font skipped (falls back to Lucida Console)' }"
)

rem Stamp the version from the git tag on this commit (untagged builds report 'dev'
rem and never offer to update themselves)
set "TAG="
for /f "delims=" %%T in ('git describe --tags --exact-match 2^>nul') do set "TAG=%%T"
if defined TAG (
  > phosphor\_build_version.py echo VERSION = "%TAG:v=%"
  echo Version %TAG%
) else (
  if exist phosphor\_build_version.py del phosphor\_build_version.py
  echo No tag on this commit: building as 'dev' ^(no auto-update^)
)

echo Building PhosphorTools.exe ...
if exist build rmdir /s /q build
if exist dist\PhosphorTools rmdir /s /q dist\PhosphorTools
.venv\Scripts\python -m PyInstaller --noconfirm --clean --log-level WARN ^
  --onedir --noconsole --name PhosphorTools --icon phosphor\assets\icon.ico ^
  --add-data "phosphor\assets;phosphor\assets" ^
  --exclude-module numpy --exclude-module PIL --exclude-module pytest ^
  phosphor_tools.py || goto :err

copy /y "share\READ ME FIRST.txt" "dist\PhosphorTools\" >nul

echo Zipping...
if exist PhosphorTools-windows.zip del PhosphorTools-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PhosphorTools' -DestinationPath 'PhosphorTools-windows.zip' -CompressionLevel Optimal" || goto :err

echo.
echo  Done!  Send your friends:  %CD%\PhosphorTools-windows.zip
echo  (They unzip it and double-click PhosphorTools\PhosphorTools.exe - no Python needed.)
echo.
explorer /select,"%CD%\PhosphorTools-windows.zip"
pause
exit /b 0

:err
echo.
echo Build failed - see the messages above.
pause
exit /b 1
