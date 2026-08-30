<#
.SYNOPSIS
    Syncs the twincat-ai-toolkit plugin development files to Cursor's local plugin cache.

.DESCRIPTION
    Runs the Python synchronizer to copy rules, skills, agents, commands, MCP server,
    and VSIX extension directly into ~/.cursor/plugins/cache/ and ~/.cursor/plugins/marketplaces/
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "sync_to_cache.py"

if (Get-Command python -ErrorAction SilentlyContinue) {
    python $PythonScript
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 $PythonScript
} else {
    Write-Error "Python executable not found. Please ensure Python is in your PATH."
}
