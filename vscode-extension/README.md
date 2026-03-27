# Delphi Assistant — VS Code Extension

Ask questions about your Delphi knowledge base directly from VS Code.

## Features

- Sidebar chat panel for knowledge base Q&A
- Right-click selected code and choose "Ask Delphi"
- Streaming responses
- Clickable source references that jump to the relevant file and line

## Setup

```bash
cd vscode-extension
npm install
npm run compile
```

Then press **F5** in VS Code to launch the Extension Development Host.

## Configuration

| Setting          | Default                  | Description                  |
|------------------|--------------------------|------------------------------|
| `delphi.apiUrl`  | `http://localhost:8888`  | Delphi API server URL        |
| `delphi.project` | `""`                     | Default project for queries  |
| `delphi.topK`    | `5`                      | Number of results to retrieve|
