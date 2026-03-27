"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.DelphiChatProvider = void 0;
const vscode = __importStar(require("vscode"));
const api_1 = require("./api");
class DelphiChatProvider {
    extensionUri;
    static viewType = "delphi-chat";
    view;
    sessionId;
    constructor(extensionUri) {
        this.extensionUri = extensionUri;
    }
    resolveWebviewView(webviewView, _context, _token) {
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
    sendQuestion(question) {
        if (this.view) {
            this.view.show?.(true);
            this.view.webview.postMessage({ type: "setQuestion", question });
        }
    }
    async handleQuestion(question) {
        const webview = this.view?.webview;
        if (!webview) {
            return;
        }
        webview.postMessage({ type: "answerStart" });
        try {
            for await (const event of (0, api_1.queryStream)(question, this.sessionId)) {
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
        }
        catch (err) {
            const message = err instanceof Error ? err.message : "Unknown error";
            webview.postMessage({ type: "error", message });
        }
    }
    async openSource(source) {
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
        }
        catch {
            vscode.window.showErrorMessage(`Cannot open file: ${source.file}`);
        }
    }
    getHtml(webview) {
        const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, "src", "webview", "chat.css"));
        const jsUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, "src", "webview", "chat.js"));
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
exports.DelphiChatProvider = DelphiChatProvider;
//# sourceMappingURL=chatPanel.js.map