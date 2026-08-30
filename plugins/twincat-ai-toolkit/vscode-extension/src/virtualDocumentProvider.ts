import * as vscode from 'vscode';
import { LanguageClient } from 'vscode-languageclient/node';

export const TWINCAT_ST_SCHEME = 'twincat-st';

export interface VirtualSectionInfo {
  sectionIndex: number;
  kind: string;
  label: string;
  virtStartLine: number;
  virtEndLine: number;
  xmlStartLine: number;
  xmlEndLine: number;
}

export interface VirtualStGetResponse {
  uri: string;
  virtualSt: string;
  sections: VirtualSectionInfo[];
}

export interface VirtualStSaveResponse {
  uri: string;
  success: boolean;
  newXml: string;
}

export class TwinCatVirtualDocumentProvider implements vscode.TextDocumentContentProvider {
  private _onDidChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this._onDidChange.event;

  private client: LanguageClient | undefined;

  constructor() {}

  public setClient(client: LanguageClient) {
    this.client = client;
  }

  public refresh(uri: vscode.Uri): void {
    this._onDidChange.fire(uri);
  }

  public static toVirtualUri(physicalUri: vscode.Uri): vscode.Uri {
    return vscode.Uri.parse(
      `${TWINCAT_ST_SCHEME}:${encodeURIComponent(physicalUri.toString())}.st`
    );
  }

  public static toPhysicalUri(virtualUri: vscode.Uri): vscode.Uri {
    const raw = virtualUri.path.replace(/\.st$/, '');
    const decoded = decodeURIComponent(raw);
    return vscode.Uri.parse(decoded);
  }

  async provideTextDocumentContent(
    uri: vscode.Uri,
    _token: vscode.CancellationToken
  ): Promise<string> {
    if (!this.client) {
      return '// TwinCAT Language Server is not connected.';
    }

    const physicalUri = TwinCatVirtualDocumentProvider.toPhysicalUri(uri);

    try {
      const resp = await this.client.sendRequest<VirtualStGetResponse>(
        'twincat/virtualSt/get',
        { uri: physicalUri.toString() }
      );
      return resp.virtualSt;
    } catch (err: any) {
      vscode.window.showErrorMessage(
        `Failed to project Virtual ST: ${err?.message || err}`
      );
      return `// Error loading Virtual ST for ${physicalUri.fsPath}\n// ${err?.message || err}`;
    }
  }

  async saveVirtualSt(document: vscode.TextDocument): Promise<boolean> {
    if (!this.client) {
      vscode.window.showErrorMessage('TwinCAT Language Server is not running.');
      return false;
    }

    if (document.uri.scheme !== TWINCAT_ST_SCHEME) {
      return false;
    }

    const physicalUri = TwinCatVirtualDocumentProvider.toPhysicalUri(document.uri);
    const virtualText = document.getText();

    try {
      const resp = await this.client.sendRequest<VirtualStSaveResponse>(
        'twincat/virtualSt/save',
        {
          uri: physicalUri.toString(),
          virtualSt: virtualText,
        }
      );

      if (resp.success && resp.newXml) {
        // Write updated XML to physical file
        const encoder = new TextEncoder();
        await vscode.workspace.fs.writeFile(physicalUri, encoder.encode(resp.newXml));
        vscode.window.setStatusBarMessage(
          `TwinCAT: Synced Virtual ST to ${physicalUri.path.split('/').pop()}`,
          3000
        );
        return true;
      }
      return false;
    } catch (err: any) {
      vscode.window.showErrorMessage(
        `Failed to sync Virtual ST back to XML: ${err?.message || err}`
      );
      return false;
    }
  }
}
