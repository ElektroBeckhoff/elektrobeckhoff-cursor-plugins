@echo off
REM Install or update the TwinCAT 3 Structured Text extension in Cursor/VS Code
set SCRIPT_DIR=%~dp0
set MCP_DIR=%SCRIPT_DIR%..\mcp-servers\mcp-twincat
python -c "import sys; sys.path.insert(0, r'%MCP_DIR%'); import extension_ops; res = extension_ops.install_extension(force=True); print(res.get('message', res))"
if %ERRORLEVEL% neq 0 (
    echo.
    echo An error occurred during extension installation.
    pause
)
