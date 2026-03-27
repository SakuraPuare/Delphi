import * as vscode from "vscode";
import { queryStream, Source } from "./api";

export class DelphiChatProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "delphi-chat";

  private view?: vscode.WebviewView;
  private sessionId?: string;

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this.extensionUri, "src", "webview"),
      ],
    };

    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.type) {
        case "ask":
          await this.handleQuestion(msg.question);
          break;
        case "openFile":
          await this.openSource(msg.source);
          break;
      }
    });
  }

  /** Send a question from outside (e.g. right-click Ask Delphi). */
  public sendQuestion(question: string) {
    if (this.view) {
      this.view.show?.(true);
      this.view.webview.postMessage({ type: "setQuestion", question });
    }
  }

  private async handleQuestion(question: string) {
    const webview = this.view?.webview;
    if (!webview) {
      return;
    }

    webview.postMessage({ type: "answerStart" });

    try {
      for await (const event of queryStream(question, this.sessionId)) {
        switch (event.type) {
          case "token":
            webview.postMessage({
              type: "token",
              content: event.content,
            });
            break;
          case "sources":
            webview.postMessage({
              type: "sources",
              sources: event.sources,
            });
            break;
          case "done":
            this.sessionId = event.session_id;
            webview.postMessage({ type: "done" });
            break;
          case "error":
            webview.postMessage({
              type: "error",
              message: event.message,
            });
            break;
        }
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unknown error";
      webview.postMessage({ type: "error", message });
    }
  }

  private async openSource(source: Source) {
    try {
      const uri = vscode.Uri.file(source.file);
      const doc = await vscode.workspace.openTextDocument(uri);
      const startLine = Math.max(0, (source.start_line ?? 1) - 1);
      const endLine = Math.max(startLine, (source.end_line ?? startLine + 1) - 1);
      const range = new vscode.Range(startLine, 0, endLine, 0);
      await vscode.window.showTextDocument(doc, {
        selection: range,
        preview: true,
      });
    } catch {
      vscode.window.showErrorMessage(
        `Cannot open file: ${source.file}`
      );
    }
  }

  private getHtml(webview: vscode.Webview): string {
    const cssUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "src", "webview", "chat.css")
    );
    const jsUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "src", "webview", "chat.js")
    );

    return /*html*/ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${cssUri}" />
</head>
<body>
  <div id="messages"></div>
  <div id="input-area">
    <textarea id="question" rows="2" placeholder="Ask Delphi a question..."></textarea>
    <button id="send-btn" title="Send">&#9654;</button>
  </div>
  <script src="${jsUri}"></script>
</body>
</html>`;
  }
}
