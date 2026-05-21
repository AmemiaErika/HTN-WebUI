@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Current folder: %cd%
echo.

if not exist "app.py" (
  echo ERROR: app.py not found. Please put this bat in the project root folder.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found. Please create it first:
  echo py -m venv .venv
  pause
  exit /b 1
)

echo Python version:
".venv\Scripts\python.exe" --version

echo.
echo Checking Streamlit...
".venv\Scripts\python.exe" -m streamlit --version >nul 2>&1
if errorlevel 1 (
  echo Streamlit not found in .venv. Installing requirements...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
  )
)

echo.
echo Starting Streamlit...
".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo Streamlit stopped or failed.
pause
