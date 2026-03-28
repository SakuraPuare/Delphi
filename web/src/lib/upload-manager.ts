import { computeSHA256 } from "./hash";

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
const API_BASE = "/api";

export type UploadPhase = "hashing" | "uploading" | "assembling" | "done" | "skipped";

export interface UploadProgress {
  phase: UploadPhase;
  percent: number;
  fileName: string;
}

interface InitResponse {
  status: "exists" | "ready" | "partial";
  upload_id?: string;
  received_chunks?: number[];
}

interface CompleteResponse {
  status: "ok" | "hash_mismatch";
  file_path?: string;
  task_id?: string;
}

export interface UploadResult {
  status: "exists" | "ok" | "hash_mismatch";
  filePath?: string;
  taskId?: string;
}

export class UploadManager {
  private abortController: AbortController | null = null;

  abort(): void {
    this.abortController?.abort();
    this.abortController = null;
  }

  async upload(
    file: File,
    project: string,
    pipeline: "doc" | "media",
    onProgress?: (p: UploadProgress) => void,
  ): Promise<UploadResult> {
    this.abortController = new AbortController();
    const { signal } = this.abortController;

    // Phase 1: Hash
    const hash = await computeSHA256(file, (percent) =>
      onProgress?.({ phase: "hashing", percent, fileName: file.name }),
    );

    // Phase 2: Init
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const initRes = await this.post<InitResponse>("/import/upload/init", {
      file_name: file.name,
      file_size: file.size,
      file_hash: hash,
      total_chunks: totalChunks,
      project,
      pipeline,
    }, signal);

    if (initRes.status === "exists") {
      onProgress?.({ phase: "skipped", percent: 100, fileName: file.name });
      return { status: "exists" };
    }

    // Phase 3: Upload chunks
    const uploadId = initRes.upload_id!;
    const received = new Set(initRes.received_chunks ?? []);
    let uploaded = received.size;

    for (let i = 0; i < totalChunks; i++) {
      if (received.has(i)) continue;
      signal.throwIfAborted();

      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);

      const res = await fetch(`${API_BASE}/import/upload/${uploadId}/chunks/${i}`, {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
        body: chunk,
        signal,
      });
      if (!res.ok) throw new Error(`Chunk ${i} upload failed: ${res.status}`);

      uploaded++;
      onProgress?.({
        phase: "uploading",
        percent: Math.round((uploaded / totalChunks) * 100),
        fileName: file.name,
      });
    }

    // Phase 4: Complete
    onProgress?.({ phase: "assembling", percent: 99, fileName: file.name });
    const completeRes = await this.post<CompleteResponse>(
      `/import/upload/${uploadId}/complete`,
      { trigger_pipeline: true },
      signal,
    );

    if (completeRes.status === "hash_mismatch") {
      return { status: "hash_mismatch" };
    }

    onProgress?.({ phase: "done", percent: 100, fileName: file.name });
    return {
      status: "ok",
      filePath: completeRes.file_path ?? undefined,
      taskId: completeRes.task_id ?? undefined,
    };
  }

  private async post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(text);
    }
    return res.json();
  }
}
