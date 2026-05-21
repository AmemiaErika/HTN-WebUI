@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo AI Design WebUI - Install Requirements
echo ========================================
echo.

if not exist "app.py" (
    echo [ERROR] Please put this bat file in the project root folder, next to app.py
    echo Current folder: %cd%
    echo.
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found.
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Python...
py --version >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py"
) else (
    python --version >nul 2>&1
    if %errorlevel%==0 (
        set "PY_CMD=python"
    ) else (
        echo [ERROR] Python was not found. Please install Python first.
        echo.
        pause
        exit /b 1
    )
)
%PY_CMD% --version

echo.
echo [2/4] Creating virtual environment if needed...
if not exist ".venv\Scripts\python.exe" (
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo.
echo [3/4] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] Failed to upgrade pip. Continue installing requirements...
)

echo.
echo [4/4] Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install requirements.
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Installation completed successfully.
echo You can now run start_webui_fixed.bat or:
echo .venv\Scripts\python.exe -m streamlit run app.py
echo ========================================
echo.
pause
