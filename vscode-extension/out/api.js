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
exports.queryStream = queryStream;
exports.fetchProjects = fetchProjects;
const vscode = __importStar(require("vscode"));
function getConfig() {
    const cfg = vscode.workspace.getConfiguration("delphi");
    return {
        apiUrl: cfg.get("apiUrl", "http://localhost:8888"),
        project: cfg.get("project", ""),
        topK: cfg.get("topK", 5),
    };
}
async function* queryStream(question, sessionId) {
    const { apiUrl, project, topK } = getConfig();
    const resp = await fetch(`${apiUrl}/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            question,
            project,
            top_k: topK,
            session_id: sessionId ?? null,
        }),
    });
    if (!resp.ok) {
        yield { type: "error", message: `HTTP ${resp.status}: ${resp.statusText}` };
        return;
    }
    const reader = resp.body?.getReader();
    if (!reader) {
        yield { type: "error", message: "No response body" };
        return;
    }
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) {
                continue;
            }
            const json = trimmed.slice(6);
            if (json === "[DONE]") {
                return;
            }
            try {
                yield JSON.parse(json);
            }
            catch {
                // skip malformed lines
            }
        }
    }
}
async function fetchProjects() {
    const { apiUrl } = getConfig();
    const resp = await fetch(`${apiUrl}/projects`);
    if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
    }
    return resp.json();
}
//# sourceMappingURL=api.js.map