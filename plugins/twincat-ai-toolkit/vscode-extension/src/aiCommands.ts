import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import { TWINCAT_ST_SCHEME, TwinCatVirtualDocumentProvider } from './virtualDocumentProvider';

export interface TargetScopeInfo {
  uri: vscode.Uri;
  ref: string;
  displayTitle: string;
  isFolder: boolean;
  isMultiSelect: boolean;
  isPartialSelection: boolean;
  startLine?: number;
  endLine?: number;
  scopeText: string;
  selectedText?: string;
  containedFilesCount?: number;
  containedFileList?: string[];
}

const TC_FILE_REGEX = /\.(TcPOU|TcDUT|TcGVL|TcIO|TcTTO|st|iecst)$/i;

/**
 * Normalizes a file path for case-insensitive comparison on Windows.
 */
function normalizePath(p: string): string {
  return p.replace(/\\/g, '/').toLowerCase();
}

/**
 * Resolves a plugin resource path (rules, skills, agents) to an optimal workspace-relative '@' path
 * so that Cursor can immediately index and attach the file in chat.
 */
function resolveResourceRef(resourceRelPath: string): string {
  const cleanPath = resourceRelPath.replace(/\\/g, '/').replace(/^@/, '');

  if (vscode.workspace.workspaceFolders) {
    for (const folder of vscode.workspace.workspaceFolders) {
      // 1. Direct path in workspace root (e.g. rules/twincat3-core.mdc)
      const direct = path.join(folder.uri.fsPath, cleanPath);
      if (fs.existsSync(direct)) {
        return `@${cleanPath}`;
      }

      // 2. In plugins/twincat-ai-toolkit/... (monorepo layout)
      const inPlugin = path.join(folder.uri.fsPath, 'plugins', 'twincat-ai-toolkit', cleanPath);
      if (fs.existsSync(inPlugin)) {
        return `@plugins/twincat-ai-toolkit/${cleanPath}`;
      }

      // 3. In twincat-ai-toolkit/...
      const inToolkit = path.join(folder.uri.fsPath, 'twincat-ai-toolkit', cleanPath);
      if (fs.existsSync(inToolkit)) {
        return `@twincat-ai-toolkit/${cleanPath}`;
      }
    }
  }

  // Fallback
  return `@${cleanPath}`;
}

/**
 * Recursively scans a directory for TwinCAT files.
 */
function findTwinCatFilesInDir(dirPath: string, maxFiles = 100): string[] {
  const result: string[] = [];

  function walk(currentDir: string, depth = 0) {
    if (depth > 6 || result.length >= maxFiles) return;
    try {
      const entries = fs.readdirSync(currentDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') {
          continue;
        }
        const full = path.join(currentDir, entry.name);
        if (entry.isDirectory()) {
          walk(full, depth + 1);
        } else if (entry.isFile() && TC_FILE_REGEX.test(entry.name)) {
          result.push(full);
        }
      }
    } catch {
      // ignore filesystem access errors
    }
  }

  walk(dirPath);
  return result;
}

/**
 * Resolves the target scope (single file, line selection, multiple files, or folder)
 * from editor or explorer context.
 */
function getTargetScopeInfo(uri?: vscode.Uri, uris?: vscode.Uri[]): TargetScopeInfo | undefined {
  const activeEditor = vscode.window.activeTextEditor;

  // Handle multi-selection from Explorer
  if (uris && uris.length > 1) {
    const refs = uris.map((u) => {
      let physical = u;
      if (physical.scheme === TWINCAT_ST_SCHEME) {
        physical = TwinCatVirtualDocumentProvider.toPhysicalUri(physical);
      }
      return `@${vscode.workspace.asRelativePath(physical, false).replace(/\\/g, '/')}`;
    });

    return {
      uri: uris[0],
      ref: refs.join(' '),
      displayTitle: `${uris.length} selected items`,
      isFolder: false,
      isMultiSelect: true,
      isPartialSelection: false,
      scopeText: `Multiple targets (${uris.length} items):\n${refs.map((r) => `- ${r}`).join('\n')}`,
      containedFileList: refs,
    };
  }

  // Single target resolution
  let targetUri = uri || activeEditor?.document.uri;
  if (!targetUri) {
    vscode.window.showWarningMessage('No TwinCAT file or folder selected.');
    return undefined;
  }

  // If invoked on a Virtual ST document, resolve the real physical file URI
  if (targetUri.scheme === TWINCAT_ST_SCHEME) {
    targetUri = TwinCatVirtualDocumentProvider.toPhysicalUri(targetUri);
  }

  const fsPath = targetUri.fsPath;
  let isFolder = false;
  try {
    if (fs.existsSync(fsPath) && fs.statSync(fsPath).isDirectory()) {
      isFolder = true;
    }
  } catch {
    // ignore
  }

  const relativePath = vscode.workspace.asRelativePath(targetUri, false).replace(/\\/g, '/');
  const baseName = targetUri.path.split('/').pop() || relativePath;

  // 1. If it's a folder: scan contained TwinCAT files
  if (isFolder) {
    const files = findTwinCatFilesInDir(fsPath);
    const relFiles = files.map((f) => `@${vscode.workspace.asRelativePath(f, false).replace(/\\/g, '/')}`);

    const folderRef = `@${relativePath}/`;
    return {
      uri: targetUri,
      ref: folderRef,
      displayTitle: `Folder ${baseName}`,
      isFolder: true,
      isMultiSelect: false,
      isPartialSelection: false,
      scopeText: `Folder ${folderRef} (${files.length} TwinCAT object(s) found)`,
      containedFilesCount: files.length,
      containedFileList: relFiles,
    };
  }

  // 2. Single file: check if editor is active with a selection
  let isPartialSelection = false;
  let startLine: number | undefined;
  let endLine: number | undefined;
  let scopeText = 'Entire file';
  let selectedText: string | undefined;

  if (activeEditor) {
    let editorPhysicalUri = activeEditor.document.uri;
    if (editorPhysicalUri.scheme === TWINCAT_ST_SCHEME) {
      editorPhysicalUri = TwinCatVirtualDocumentProvider.toPhysicalUri(editorPhysicalUri);
    }

    const isSameFile = normalizePath(editorPhysicalUri.fsPath) === normalizePath(targetUri.fsPath);

    if (isSameFile) {
      const selection = activeEditor.selection;
      const text = activeEditor.document.getText(selection);

      if (selection && !selection.isEmpty && text.trim().length > 0) {
        isPartialSelection = true;
        startLine = selection.start.line + 1;
        endLine =
          selection.end.character === 0 && selection.end.line > selection.start.line
            ? selection.end.line
            : selection.end.line + 1;

        selectedText = text;

        if (startLine === endLine) {
          scopeText = `Selected line ${startLine}`;
        } else {
          scopeText = `Selected lines ${startLine}-${endLine}`;
        }
      }
    }
  }

  let ref = `@${relativePath}`;
  if (isPartialSelection && startLine !== undefined && endLine !== undefined) {
    ref = startLine === endLine ? `@${relativePath}:${startLine}` : `@${relativePath}:${startLine}-${endLine}`;
  }

  return {
    uri: targetUri,
    ref,
    displayTitle: isPartialSelection ? `${baseName} (${scopeText})` : baseName,
    isFolder: false,
    isMultiSelect: false,
    isPartialSelection,
    startLine,
    endLine,
    scopeText,
    selectedText,
  };
}

/**
 * Standardized prompt builder based on BASE AI Rules.
 * Supports single files, line selections, folders, and multi-selections with optimized Cursor '@' paths.
 */
function buildStandardAiPrompt(
  slashCommand: string,
  target: TargetScopeInfo,
  baseTaskDescription: string,
  rawReferences: string[]
): string {
  // Dynamically optimize all reference paths for Cursor
  const resolvedRefs = rawReferences.map(resolveResourceRef);
  const refList = resolvedRefs.map((r) => `- ${r}`).join('\n');
  const commandPrefix = slashCommand ? `${slashCommand} ` : '';

  let scopeDetails = `- Target: ${target.ref}\n- Scope: ${target.scopeText}`;

  if (target.isFolder && target.containedFileList && target.containedFileList.length > 0) {
    const listPreview = target.containedFileList.slice(0, 20).map((f) => `  - ${f}`).join('\n');
    const remaining = target.containedFileList.length > 20 ? `\n  - ... and ${target.containedFileList.length - 20} more files` : '';
    scopeDetails += `\n- Contained Objects:\n${listPreview}${remaining}`;
  } else if (target.isPartialSelection && target.selectedText) {
    scopeDetails += `\n\n**Selected Code Section (${target.scopeText}):**\n\`\`\`iecst\n${target.selectedText}\n\`\`\``;
  }

  return `${commandPrefix}${target.ref}

**Task:**
${baseTaskDescription}${target.isPartialSelection ? ` specifically for ${target.scopeText}` : target.isFolder ? ` across all objects in ${target.ref}` : ''}.

**Target Scope:**
${scopeDetails}

**Required Rules & Skills:**
${refList}

**Base Execution Rules (Strict):**
1. Strictly follow all referenced rules, skills, checklists, and agent instructions.
2. Work autonomously, precisely, and factually without guessing or assumptions.
3. 100% IEC 61131-3 & TwinCAT 3 best practices — no pseudo-code, no placeholders, no omissions.
4. Priority stack: Safety (1) > Functionality (2) > Performance (3) > Code quality / style (4).
5. XML safety: Never alter XML elements, GUIDs, or LineIDs — modify only CDATA ST content when editing.
6. Provide complete, production-ready results. Code and comments strictly in English.

Respond in German with a short and concise summary of what was done.`;
}

/**
 * Copies the pre-structured prompt to the clipboard and opens the Cursor Chat panel
 * with the prompt prefilled (without automatically submitting).
 * The user can select their preferred model and start the generation.
 */
async function sendPromptToCursor(prompt: string, title: string): Promise<void> {
  // 1. Always copy prompt to clipboard so it's ready to paste (Ctrl+V) if needed
  await vscode.env.clipboard.writeText(prompt);

  // 2. Open Chat panel and prefill the input (does not auto-execute)
  try {
    await vscode.commands.executeCommand('workbench.action.chat.open', { query: prompt });
  } catch {
    try {
      await vscode.commands.executeCommand('aichat.newchataction');
    } catch {
      try {
        await vscode.commands.executeCommand('workbench.action.chat.open');
      } catch {
        // Ignore fallback errors
      }
    }
  }

  // 3. Inform user to select model and hit start
  vscode.window.setStatusBarMessage(`$(sparkle) [TwinCAT AI] Prompt for "${title}" ready in Chat. Select model & click Start.`, 6000);
  vscode.window.showInformationMessage(
    `[TwinCAT AI] Prompt for "${title}" inserted into Chat (and copied to clipboard). Select your model and click Start.`
  );
}

/**
 * Register the top 3 AI-driven file context commands:
 * 1. Add Comments (* *)
 * 2. Pagefault & Safety Audit
 * 3. Code Review (IEC 61131-3 & OOP)
 */
export function registerAiCommands(context: vscode.ExtensionContext) {
  // 1. Add Comments (* *)
  context.subscriptions.push(
    vscode.commands.registerCommand('twincat.ai.addComments', async (uri?: vscode.Uri, uris?: vscode.Uri[]) => {
      const target = getTargetScopeInfo(uri, uris);
      if (!target) return;

      const prompt = buildStandardAiPrompt(
        '/twincat3-cmd-comment',
        target,
        `Perform a standard-compliant, professional comment pass (* *) on ${target.ref}`,
        [
          'rules/twincat3-core.mdc',
          'rules/twincat3-comments.mdc',
          'skills/twincat3-comment/SKILL.md',
          'skills/twincat3-code-style/references/comment-rules.md',
        ]
      );

      await sendPromptToCursor(prompt, `Add Comments: ${target.displayTitle}`);
    })
  );

  // 2. Pagefault & Safety Audit
  context.subscriptions.push(
    vscode.commands.registerCommand('twincat.ai.pagefaultAudit', async (uri?: vscode.Uri, uris?: vscode.Uri[]) => {
      const target = getTargetScopeInfo(uri, uris);
      if (!target) return;

      const prompt = buildStandardAiPrompt(
        '/twincat3-cmd-pagefault-audit',
        target,
        `Perform a rigorous, InfoSys-backed static page-fault and memory safety audit on ${target.ref}`,
        [
          'rules/twincat3-core.mdc',
          'rules/twincat3-pagefault-safety.mdc',
          'skills/twincat3-pagefault-audit/SKILL.md',
          'skills/twincat3-pagefault-audit/checklist.md',
          'skills/twincat3-pagefault-audit/infosys-evidence.md',
          'agents/twincat-pagefault-auditor.md',
        ]
      );

      await sendPromptToCursor(prompt, `Pagefault Audit: ${target.displayTitle}`);
    })
  );

  // 3. TwinCAT 3 Code Review (IEC 61131-3 & OOP)
  context.subscriptions.push(
    vscode.commands.registerCommand('twincat.ai.codeReview', async (uri?: vscode.Uri, uris?: vscode.Uri[]) => {
      const target = getTargetScopeInfo(uri, uris);
      if (!target) return;

      const prompt = buildStandardAiPrompt(
        '',
        target,
        `Perform a comprehensive, rigorous IEC 61131-3 ST, OOP, and architecture code review on ${target.ref}`,
        [
          'rules/twincat3-core.mdc',
          'rules/twincat3-naming.mdc',
          'rules/twincat3-formatting.mdc',
          'rules/twincat3-comments.mdc',
          'rules/twincat3-oop.mdc',
          'rules/twincat3-pagefault-safety.mdc',
          'rules/twincat3-xml.mdc',
          'agents/twincat-code-reviewer.md',
        ]
      );

  // 4. TwinCAT 3 Fast Syntax & Diagnostics Check
  context.subscriptions.push(
    vscode.commands.registerCommand('twincat.ai.checkSyntax', async (uri?: vscode.Uri, uris?: vscode.Uri[]) => {
      const target = getTargetScopeInfo(uri, uris);
      if (!target) return;

      const prompt = buildStandardAiPrompt(
        '/twincat3-cmd-check-syntax',
        target,
        `Run fast headless syntax and semantic validation using twincat_check_syntax on ${target.ref}`,
        [
          'rules/twincat3-core.mdc',
          'rules/twincat3-mcp-syntax.mdc',
          'skills/twincat3-check-syntax/SKILL.md',
        ]
      );

      await sendPromptToCursor(prompt, `Check Syntax: ${target.displayTitle}`);
    })
  );
}
