import { createSHA256 } from "hash-wasm";

const HASH_CHUNK_SIZE = 2 * 1024 * 1024; // 2MB

/**
 * Compute SHA-256 hash of a File with progress callback.
 * Uses streaming hash-wasm for memory efficiency on large files.
 */
export async function computeSHA256(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<string> {
  const hasher = await createSHA256();
  hasher.init();

  const totalSize = file.size;
  let offset = 0;

  while (offset < totalSize) {
    const end = Math.min(offset + HASH_CHUNK_SIZE, totalSize);
    const slice = file.slice(offset, end);
    const buffer = new Uint8Array(await slice.arrayBuffer());
    hasher.update(buffer);
    offset = end;
    onProgress?.(Math.round((offset / totalSize) * 100));
  }

  return hasher.digest("hex");
}
