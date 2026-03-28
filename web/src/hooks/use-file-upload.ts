import { useCallback, useRef, useState } from "react";
import { UploadManager, type UploadProgress, type UploadResult } from "@/lib/upload-manager";

// Document extensions that go to "doc" pipeline
const DOC_EXTS = new Set([".md", ".mdx", ".txt", ".rst", ".pdf", ".html", ".htm"]);

function getFileExt(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function classifyPipeline(file: File): "doc" | "media" {
  return DOC_EXTS.has(getFileExt(file.name)) ? "doc" : "media";
}

export interface FileProgress {
  file: File;
  progress: UploadProgress | null;
  result: UploadResult | null;
  error: string | null;
}

export function useFileUpload(project: string) {
  const [fileProgresses, setFileProgresses] = useState<Map<string, FileProgress>>(new Map());
  const [isUploading, setIsUploading] = useState(false);
  const managerRef = useRef(new UploadManager());

  const uploadFiles = useCallback(
    async (files: File[]) => {
      setIsUploading(true);

      // Initialize progress map
      const initial = new Map<string, FileProgress>();
      files.forEach((f) =>
        initial.set(f.name, { file: f, progress: null, result: null, error: null }),
      );
      setFileProgresses(initial);

      const results: UploadResult[] = [];

      for (const file of files) {
        try {
          const result = await managerRef.current.upload(
            file,
            project,
            classifyPipeline(file),
            (progress) => {
              setFileProgresses((prev) => {
                const next = new Map(prev);
                const entry = next.get(file.name);
                if (entry) next.set(file.name, { ...entry, progress });
                return next;
              });
            },
          );
          setFileProgresses((prev) => {
            const next = new Map(prev);
            const entry = next.get(file.name);
            if (entry) next.set(file.name, { ...entry, result });
            return next;
          });
          results.push(result);
        } catch (e) {
          const msg = e instanceof Error ? e.message : "Upload failed";
          setFileProgresses((prev) => {
            const next = new Map(prev);
            const entry = next.get(file.name);
            if (entry) next.set(file.name, { ...entry, error: msg });
            return next;
          });
        }
      }

      setIsUploading(false);
      return results;
    },
    [project],
  );

  const abort = useCallback(() => {
    managerRef.current.abort();
    setIsUploading(false);
  }, []);

  return { uploadFiles, abort, fileProgresses, isUploading };
}
