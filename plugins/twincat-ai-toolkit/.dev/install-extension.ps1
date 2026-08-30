<#
.SYNOPSIS
    Installs / Updates the local twincat-iecst.vsix extension directly in Cursor/VS Code.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$McpDir = Join-Path (Split-Path -Parent $ScriptDir) "mcp-servers\mcp-twincat"

$PythonCmd = "import sys; sys.path.insert(0, r'$McpDir'); import extension_ops; res = extension_ops.install_extension(force=True); print(res)"

if (Get-Command python -ErrorAction SilentlyContinue) {
    python -c $PythonCmd
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -c $PythonCmd
} else {
    Write-Error "Python executable not found. Please ensure Python is in your PATH."
}
