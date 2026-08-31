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
 * workspace, monorepo, and user extra paths.
 */
function resolvePythonPathEnv(context: vscode.ExtensionContext, userExtraPaths: string[]): string {
  const validPaths: string[] = [];

  // 1. First priority: Bundled inside extension (e.g. extension/server containing twincat_core)
  const bundledServerDir = path.join(context.extensionPath, 'server');
  if (fs.existsSync(path.join(bundledServerDir, 'twincat_core'))) {
    validPaths.push(bundledServerDir);
  }

  // 2. Relative to extension in development / plugin repository
  const devServerDir = path.resolve(context.extensionPath, '..', 'mcp-servers', 'mcp-twincat');
  if (fs.existsSync(path.join(devServerDir, 'twincat_core')) && !validPaths.includes(devServerDir)) {
    validPaths.push(devServerDir);
  }

  const monorepoServerDir = path.resolve(
    context.extensionPath,
    '..',
    '..',
    'plugins',
    'twincat-ai-toolkit',
    'mcp-servers',
    'mcp-twincat'
  );
  if (fs.existsSync(path.join(monorepoServerDir, 'twincat_core')) && !validPaths.includes(monorepoServerDir)) {
    validPaths.push(monorepoServerDir);
  }

  // 3. Workspace folders (direct paths only, non-blocking)
  if (vscode.workspace.workspaceFolders) {
    for (const wf of vscode.workspace.workspaceFolders) {
      const wsCoreDir = path.join(wf.uri.fsPath, 'plugins', 'twincat-ai-toolkit', 'mcp-servers', 'mcp-twincat');
      if (fs.existsSync(path.join(wsCoreDir, 'twincat_core')) && !validPaths.includes(wsCoreDir)) {
        validPaths.push(wsCoreDir);
      }
    }
  }

  // 4. User configured extraPaths
  for (const p of userExtraPaths) {
    if (p && fs.existsSync(p) && !validPaths.includes(p)) {
      validPaths.push(p);
    }
  }

  // 5. Preserve existing process.env.PYTHONPATH if set
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
      { scheme: 'file', language: 'xml' },
      { scheme: 'file', pattern: '**/*.{TcPOU,TcDUT,TcGVL,TcIO,TcTTO,tcpou,tcdut,tcgvl,tcio,tctto,st,iecst,TcPou,TcDut,TcGvl,TcIo,TcTto,TCPOU,TCDUT,TCGVL,TCIO,TCTTO,ST,IECST}' },
      { scheme: 'untitled', language: 'iecst' },
      { scheme: 'untitled', language: 'xml' },
    ],
    synchronize: {
      fileEvents: [
        vscode.workspace.createFileSystemWatcher('**/*.{TcPOU,TcDUT,TcGVL,TcIO,TcTTO,tcpou,tcdut,tcgvl,tcio,tctto,plcproj,TcPou,TcDut,TcGvl,TcIo,TCPOU,TCDUT,TCGVL,TCIO,PLCPROJ}'),
      ],
    },
    traceOutputChannel: vscode.window.createOutputChannel('TwinCAT Language Server Trace'),
  };

  // Create LanguageClient
  client = new LanguageClient(
    'twincat-lsp',
    'TwinCAT Language Server',
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

  // Command: Format Current Section / Member
  const formatSectionCmd = vscode.commands.registerCommand(
    'twincat.formatSection',
    async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || !client) {
        return;
      }

      try {
        const position = editor.selection.active;
        const response = await client.sendRequest<{
          edits: Array<{
            range: {
              start: { line: number; character: number };
              end: { line: number; character: number };
            };
            newText: string;
          }>;
          sectionName: string;
          success: boolean;
        }>('twincat/formatSection', {
          textDocument: { uri: editor.document.uri.toString() },
          position: { line: position.line, character: position.character },
        });

        if (!response || !response.success) {
          vscode.window.showWarningMessage('Could not format current section.');
          return;
        }

        if (!response.edits || response.edits.length === 0) {
          vscode.window.setStatusBarMessage(
            `TwinCAT: ${response.sectionName || 'Section'} is already formatted.`,
            3000
          );
          return;
        }

        const workspaceEdit = new vscode.WorkspaceEdit();
        for (const edit of response.edits) {
          const range = new vscode.Range(
            new vscode.Position(edit.range.start.line, edit.range.start.character),
            new vscode.Position(edit.range.end.line, edit.range.end.character)
          );
          workspaceEdit.replace(editor.document.uri, range, edit.newText);
        }

        const applied = await vscode.workspace.applyEdit(workspaceEdit);
        if (applied) {
          vscode.window.setStatusBarMessage(
            `TwinCAT: Formatted ${response.sectionName}`,
            3000
          );
        }
      } catch (err: any) {
        vscode.window.showErrorMessage(`Format Section error: ${err?.message || err}`);
      }
    }
  );

  // Register AI Commands for Cursor Chat/Composer
  registerAiCommands(context);

  context.subscriptions.push(
    client,
    restartServerCmd,
    formatSectionCmd
  );
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
