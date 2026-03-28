export interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

/**
 * Parse an SSE stream from a fetch Response.
 * Yields parsed JSON events. Supports AbortController via the signal on fetch.
 */
export async function* parseSSE(
  response: Response,
): AsyncGenerator<SSEEvent> {
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`SSE request failed: ${response.status} ${text}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;
        const json = trimmed.slice(5).trim();
        if (json === "[DONE]") return;
        try {
          yield JSON.parse(json) as SSEEvent;
        } catch {
          // skip malformed JSON
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
