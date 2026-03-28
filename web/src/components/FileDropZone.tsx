import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { useTranslation } from "react-i18next";

interface FileDropZoneProps {
  accept: string;
  multiple?: boolean;
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
}

export function FileDropZone({ accept, multiple = true, onFilesSelected, disabled }: FileDropZoneProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) onFilesSelected(files);
  }, [disabled, onFilesSelected]);

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = "";
  };

  return (
    <div
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
        isDragging
          ? "border-blue-500 bg-blue-500/10"
          : disabled
            ? "cursor-not-allowed border-zinc-700 opacity-50"
            : "border-zinc-600 hover:border-zinc-500 hover:bg-zinc-800/50"
      }`}
    >
      <Upload className="mb-2 h-8 w-8 text-zinc-400" />
      <p className="text-sm text-zinc-400">{t("import.dropzone")}</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleChange}
        className="hidden"
      />
    </div>
  );
}
