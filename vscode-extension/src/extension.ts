import * as vscode from "vscode";
import { DelphiChatProvider } from "./chatPanel";

let chatProvider: DelphiChatProvider;

export function activate(context: vscode.ExtensionContext) {
  chatProvider = new DelphiChatProvider(context.extensionUri);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      DelphiChatProvider.viewType,
      chatProvider
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("delphi.askQuestion", () => {
      // Focus the sidebar panel — VS Code will auto-resolve the webview
      vscode.commands.executeCommand("delphi-chat.focus");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("delphi.askAboutSelection", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        return;
      }

      const selection = editor.document.getText(editor.selection);
      if (!selection) {
        vscode.window.showInformationMessage("No text selected.");
        return;
      }

      const fileName = vscode.workspace.asRelativePath(
        editor.document.uri
      );
      const lang = editor.document.languageId;
      const question = `Explain the following code from \`${fileName}\`:\n\n\`\`\`${lang}\n${selection}\n\`\`\``;

      // Ensure sidebar is visible, then send the question
      vscode.commands.executeCommand("delphi-chat.focus").then(() => {
        // Small delay to let the webview resolve if it wasn't open yet
        setTimeout(() => chatProvider.sendQuestion(question), 300);
      });
    })
  );
}

export function deactivate() {
  // nothing to clean up
}
