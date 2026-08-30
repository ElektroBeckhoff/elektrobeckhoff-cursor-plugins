@echo off
REM Synchronize local twincat-ai-toolkit plugin development files directly into Cursor's local plugin cache.
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%sync_to_cache.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo An error occurred during synchronization.
    pause
)
