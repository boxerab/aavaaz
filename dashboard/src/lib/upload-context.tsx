"use client";

import { createContext, useContext, useState, useRef, useCallback, type ReactNode } from "react";

interface Segment {
  start: number;
  end: number;
  text: string;
  words?: { word: string; start: number; end: number; probability: number }[];
}

export interface TranscriptionResult {
  text?: string;
  segments: Segment[];
  language?: string;
  duration?: number;
}

interface UploadState {
  file: File | null;
  loading: boolean;
  progress: number;
  progressStage: string;
  result: TranscriptionResult | null;
  error: string;
  elapsed: number;
  format: "json" | "text" | "srt" | "vtt";
}

interface UploadContextValue extends UploadState {
  setFile: (f: File | null) => void;
  setLoading: (v: boolean) => void;
  setProgress: (v: number) => void;
  setProgressStage: (v: string) => void;
  setResult: (v: TranscriptionResult | null) => void;
  setError: (v: string) => void;
  setElapsed: (v: number) => void;
  setFormat: (v: "json" | "text" | "srt" | "vtt") => void;
}

const UploadContext = createContext<UploadContextValue | null>(null);

export function UploadProvider({ children }: { children: ReactNode }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState("");
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [format, setFormat] = useState<"json" | "text" | "srt" | "vtt">("json");

  return (
    <UploadContext.Provider
      value={{
        file, setFile,
        loading, setLoading,
        progress, setProgress,
        progressStage, setProgressStage,
        result, setResult,
        error, setError,
        elapsed, setElapsed,
        format, setFormat,
      }}
    >
      {children}
    </UploadContext.Provider>
  );
}

export function useUpload() {
  const ctx = useContext(UploadContext);
  if (!ctx) throw new Error("useUpload must be used within UploadProvider");
  return ctx;
}
