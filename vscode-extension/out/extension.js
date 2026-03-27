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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const chatPanel_1 = require("./chatPanel");
let chatProvider;
function activate(context) {
    chatProvider = new chatPanel_1.DelphiChatProvider(context.extensionUri);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(chatPanel_1.DelphiChatProvider.viewType, chatProvider));
    context.subscriptions.push(vscode.commands.registerCommand("delphi.askQuestion", () => {
        // Focus the sidebar panel — VS Code will auto-resolve the webview
        vscode.commands.executeCommand("delphi-chat.focus");
    }));
    context.subscriptions.push(vscode.commands.registerCommand("delphi.askAboutSelection", () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showInformationMessage("No text selected.");
            return;
        }
        const fileName = vscode.workspace.asRelativePath(editor.document.uri);
        const lang = editor.document.languageId;
        const question = `Explain the following code from \`${fileName}\`:\n\n\`\`\`${lang}\n${selection}\n\`\`\``;
        // Ensure sidebar is visible, then send the question
        vscode.commands.executeCommand("delphi-chat.focus").then(() => {
            // Small delay to let the webview resolve if it wasn't open yet
            setTimeout(() => chatProvider.sendQuestion(question), 300);
        });
    }));
}
function deactivate() {
    // nothing to clean up
}
//# sourceMappingURL=extension.js.map