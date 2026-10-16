@echo off
setlocal
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "APP_DIR=%PROJECT_DIR%\app"
set "PORT=3000"
set "SHARED_KEYS_DIR=%PROJECT_DIR%\..\01b Local Keys and Source Archive\keys"
if exist "%SHARED_KEYS_DIR%" set "CREATIVE_NEGOTIATIONS_KEYS_DIR=%SHARED_KEYS_DIR%"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install it from https://nodejs.org/ and try again.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and select "Add Python to PATH".
  pause
  exit /b 1
)
set "PYTHON_BIN=python"

if not exist "%APP_DIR%\openai_key.txt" if not exist "%CREATIVE_NEGOTIATIONS_KEYS_DIR%\openai_key.txt" if "%OPENAI_API_KEY%"=="" (
  echo An OpenAI key is needed for live offer scoring.
  echo Create app\openai_key.txt and add the key,
  echo or place it in the sibling 01b Local Keys and Source Archive\keys folder.
  pause
  exit /b 1
)

if not exist "%APP_DIR%\anthropic_key.txt" if not exist "%CREATIVE_NEGOTIATIONS_KEYS_DIR%\anthropic_key.txt" if "%ANTHROPIC_API_KEY%"=="" (
  echo Note: no Anthropic key was found. The scorer and solo preview will work,
  echo but the optional live LLM counterpart will not be available.
)

pushd "%APP_DIR%"
if not exist "node_modules\express" (
  echo Installing the app dependency...
  call npm install
  if errorlevel 1 (
    popd
    echo Installation failed. Check the internet connection and try again.
    pause
    exit /b 1
  )
)

start "Creative Negotiations" /D "%APP_DIR%" cmd /k "set PORT=%PORT%&& set PYTHON_BIN=%PYTHON_BIN%&& set CREATIVE_NEGOTIATIONS_KEYS_DIR=%CREATIVE_NEGOTIATIONS_KEYS_DIR%&& npm start"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%PORT%/experiment"
popd
endlocal
