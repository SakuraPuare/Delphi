// @ts-nocheck
(function () {
  const vscode = acquireVsCodeApi();

  const messagesEl = document.getElementById("messages");
  const questionEl = document.getElementById("question");
  const sendBtn = document.getElementById("send-btn");

  let currentAssistantBody = null;
  let busy = false;

  // ---- Send question ----
  function send() {
    const text = questionEl.value.trim();
    if (!text || busy) return;
    questionEl.value = "";
    vscode.postMessage({ type: "ask", question: text });
  }

  sendBtn.addEventListener("click", send);
  questionEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  // ---- Render helpers ----
  function addMessage(role, bodyHtml) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg msg-${role}`;

    const roleEl = document.createElement("div");
    roleEl.className = "msg-role";
    roleEl.textContent = role === "user" ? "You" : "Delphi";
    wrapper.appendChild(roleEl);

    const body = document.createElement("div");
    body.className = "msg-body";
    if (bodyHtml !== undefined) body.innerHTML = bodyHtml;
    wrapper.appendChild(body);

    messagesEl.appendChild(wrapper);
    scrollToBottom();
    return body;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderSources(sources) {
    if (!sources || sources.length === 0) return;

    const container = document.createElement("div");
    container.className = "sources";

    const title = document.createElement("div");
    title.className = "sources-title";
    title.textContent = "Sources";
    container.appendChild(title);

    for (const src of sources) {
      const card = document.createElement("div");
      card.className = "source-card";
      card.addEventListener("click", () => {
        vscode.postMessage({ type: "openFile", source: src });
      });

      const fileEl = document.createElement("span");
      fileEl.className = "source-file";
      const lineInfo =
        src.start_line != null ? `:${src.start_line}` : "";
      fileEl.textContent = src.file + lineInfo;
      fileEl.title = src.file;
      card.appendChild(fileEl);

      const scoreEl = document.createElement("span");
      scoreEl.className = "source-score";
      scoreEl.textContent = (src.score * 100).toFixed(0) + "%";
      card.appendChild(scoreEl);

      container.appendChild(card);
    }

    // Append sources after the current assistant message
    if (currentAssistantBody && currentAssistantBody.parentElement) {
      currentAssistantBody.parentElement.appendChild(container);
    } else {
      messagesEl.appendChild(container);
    }
    scrollToBottom();
  }

  function setBusy(val) {
    busy = val;
    sendBtn.disabled = val;
    questionEl.disabled = val;
  }

  // ---- Handle messages from extension ----
  window.addEventListener("message", (event) => {
    const msg = event.data;
    switch (msg.type) {
      case "setQuestion":
        addMessage("user", escapeHtml(msg.question));
        vscode.postMessage({ type: "ask", question: msg.question });
        break;

      case "answerStart":
        setBusy(true);
        currentAssistantBody = addMessage("assistant");
        break;

      case "token":
        if (currentAssistantBody) {
          currentAssistantBody.textContent += msg.content;
          scrollToBottom();
        }
        break;

      case "sources":
        renderSources(msg.sources);
        break;

      case "done":
        setBusy(false);
        currentAssistantBody = null;
        break;

      case "error":
        if (currentAssistantBody) {
          currentAssistantBody.innerHTML +=
            '<span class="error-text">\nError: ' +
            escapeHtml(msg.message) +
            "</span>";
        } else {
          addMessage(
            "assistant",
            '<span class="error-text">Error: ' +
              escapeHtml(msg.message) +
              "</span>"
          );
        }
        setBusy(false);
        currentAssistantBody = null;
        break;
    }
  });
})();
