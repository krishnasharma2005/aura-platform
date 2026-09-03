"use client";

import * as React from "react";
import { UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";

const ACCEPTED = ".pdf,.doc,.docx,.txt";

export function Dropzone({ onFiles, disabled }: { onFiles: (files: FileList) => void; disabled?: boolean }) {
  const [isDragging, setIsDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        if (disabled) return;
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
        isDragging ? "border-primary bg-primary/5" : "border-border bg-card/50 hover:border-foreground/25",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
        <UploadCloud className="h-5 w-5" strokeWidth={1.75} />
      </span>
      <div>
        <p className="text-sm font-medium text-foreground">Drag a file here, or click to browse</p>
        <p className="mt-0.5 text-xs text-muted-foreground">PDF or Word documents, up to 20MB each</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        multiple
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
