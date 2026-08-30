import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from 'vscode-languageclient/node';
import { registerAiCommands } from './aiCommands';

let client: LanguageClient | undefined;

/**
 * Locate directories containing the `twincat_core` Python package across bundled extension,
 * workspace, monorepo, and Cursor plugin cache locations.
 */
function resolvePythonPathEnv(context: vscode.ExtensionContext, userExtraPaths: string[]): string {
  const candidateDirs: string[] = [];

  // 1. Bundled inside extension (e.g. extension/server containing twincat_core)
  candidateDirs.push(path.join(context.extensionPath, 'server'));
  candidateDirs.push(context.extensionPath);

  // 2. Relative to extension in plugin repository
  candidateDirs.push(path.resolve(context.extensionPath, '..', 'mcp-servers', 'mcp-twincat'));
  candidateDirs.push(
    path.resolve(context.extensionPath, '..', '..', 'plugins', 'twincat-ai-toolkit', 'mcp-servers', 'mcp-twincat')
  );

  // 3. Workspace folders
  if (vscode.workspace.workspaceFolders) {
    for (const wf of vscode.workspace.workspaceFolders) {
      candidateDirs.push(path.join(wf.uri.fsPath, 'plugins', 'twincat-ai-toolkit', 'mcp-servers', 'mcp-twincat'));
      candidateDirs.push(path.join(wf.uri.fsPath, 'mcp-servers', 'mcp-twincat'));
      candidateDirs.push(wf.uri.fsPath);
    }
  }

  // 4. Cursor plugin cache directories
  const homeDir = os.homedir();
  const cursorPluginCacheBase = path.join(
    homeDir,
    '.cursor',
    'plugins',
    'cache',
    'elektrobeckhoff-cursor-plugins',
    'twincat-ai-toolkit'
  );
  if (fs.existsSync(cursorPluginCacheBase)) {
    try {
      const entries = fs.readdirSync(cursorPluginCacheBase, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          candidateDirs.push(path.join(cursorPluginCacheBase, entry.name, 'mcp-servers', 'mcp-twincat'));
        }
      }
    } catch {
      // ignore
    }
  }

  const cursorMarketplacesBase = path.join(homeDir, '.cursor', 'plugins', 'marketplaces');
  if (fs.existsSync(cursorMarketplacesBase)) {
    try {
      const findMcpDirs = (dir: string, depth = 0) => {
        if (depth > 5) return;
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const sub = path.join(dir, entry.name);
            if (entry.name === 'twincat-ai-toolkit') {
              candidateDirs.push(path.join(sub, 'mcp-servers', 'mcp-twincat'));
            } else if (!entry.name.startsWith('.') && entry.name !== 'node_modules') {
              findMcpDirs(sub, depth + 1);
            }
          }
        }
      };
      findMcpDirs(cursorMarketplacesBase);
    } catch {
      // ignore
    }
  }

  // 5. User configured extraPaths
  for (const p of userExtraPaths) {
    if (p && !candidateDirs.includes(p)) {
      candidateDirs.push(p);
    }
  }

  // Filter paths that actually contain twincat_core
  const validPaths: string[] = [];
  for (const dir of candidateDirs) {
    if (fs.existsSync(dir)) {
      const hasCore =
        fs.existsSync(path.join(dir, 'twincat_core')) ||
        fs.existsSync(path.join(dir, '__init__.py'));
      if (hasCore && !validPaths.includes(dir)) {
        validPaths.push(dir);
      }
    }
  }

  // If no directory specifically containing twincat_core was detected, include existing candidates
  if (validPaths.length === 0) {
    for (const dir of candidateDirs) {
      if (fs.existsSync(dir) && !validPaths.includes(dir)) {
        validPaths.push(dir);
      }
    }
  }

  // Preserve existing process.env.PYTHONPATH if set
  if (process.env.PYTHONPATH) {
    validPaths.push(process.env.PYTHONPATH);
  }

  return validPaths.join(path.delimiter);
}

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('twincat');
  const pythonPath = config.get<string>('server.pythonPath', 'python');
  const extraPaths = config.get<string[]>('server.extraPaths', []);
  const pythonPathEnv = resolvePythonPathEnv(context, extraPaths);

  // Configure Python LSP Server process (stdio)
  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: ['-m', 'twincat_core.lsp'],
    options: {
      env: {
        ...process.env,
        PYTHONPATH: pythonPathEnv,
      },
    },
  };

  // Configure LSP Client Options
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: 'file', language: 'iecst' },
      { scheme: 'file', pattern: '**/*.{TcPOU,TcDUT,TcGVL,TcIO,TcTTO,st,iecst}' },
    ],
    synchronize: {
      fileEvents: [
        vscode.workspace.createFileSystemWatcher('**/*.{TcPOU,TcDUT,TcGVL,TcIO,TcTTO,plcproj}'),
      ],
    },
    traceOutputChannel: vscode.window.createOutputChannel('TwinCAT Language Server Trace'),
  };

  // Create LanguageClient
  client = new LanguageClient(
    'twincat-lsp',
    'TwinCAT 3 Language Server',
    serverOptions,
    clientOptions
  );

  // Start client
  client.start();

  // Command: Restart Language Server
  const restartServerCmd = vscode.commands.registerCommand(
    'twincat.restartServer',
    async () => {
      if (client) {
        await client.stop();
        client.start().then(() => {
          vscode.window.showInformationMessage('TwinCAT Language Server restarted.');
        });
      }
    }
  );

  // Register AI Commands for Cursor Chat/Composer
  registerAiCommands(context);

  context.subscriptions.push(
    client,
    restartServerCmd
  );
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
