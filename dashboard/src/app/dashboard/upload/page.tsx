"use client";

import { useState, useRef, useCallback } from "react";
import { Upload, FileAudio, Loader2, Download, Copy, Check } from "lucide-react";

const BATCH_URL =
  process.env.NEXT_PUBLIC_BATCH_URL ||
  "https://gh0edmarma.execute-api.us-east-1.amazonaws.com/v1/audio/transcriptions";

interface Segment {
  start: number;
  end: number;
  text: string;
  words?: { word: string; start: number; end: number; probability: number }[];
}

interface TranscriptionResult {
  text?: string;
  segments: Segment[];
  language?: string;
  duration?: number;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const [format, setFormat] = useState<"json" | "text" | "srt" | "vtt">("json");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  async function transcribe() {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    const t0 = Date.now();

    try {
      // Load feature config from settings
      let features = null;
      try {
        const stored = localStorage.getItem("aavaaz-features-config");
        if (stored) features = JSON.parse(stored);
      } catch { /* ignore */ }

      const formData = new FormData();
      formData.append("file", file);
      formData.append("response_format", format);
      if (features) {
        formData.append("features", JSON.stringify(features));
      }

      const apiKey = localStorage.getItem("aavaaz-api-key") || "";
      const headers: Record<string, string> = {};
      if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

      const res = await fetch(BATCH_URL, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }

      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await res.json();
        setResult(data);
      } else {
        const text = await res.text();
        setResult({ segments: [], text });
      }
      setElapsed(Date.now() - t0);

      // Save to logs
      const logs = JSON.parse(localStorage.getItem("aavaaz-request-logs") || "[]");
      logs.unshift({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        type: "batch",
        file: file.name,
        size: file.size,
        duration: elapsed / 1000,
        format,
        status: "success",
      });
      localStorage.setItem("aavaaz-request-logs", JSON.stringify(logs.slice(0, 100)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      // Log error too
      const logs = JSON.parse(localStorage.getItem("aavaaz-request-logs") || "[]");
      logs.unshift({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        type: "batch",
        file: file.name,
        size: file.size,
        format,
        status: "error",
        error: err instanceof Error ? err.message : "Unknown",
      });
      localStorage.setItem("aavaaz-request-logs", JSON.stringify(logs.slice(0, 100)));
    } finally {
      setLoading(false);
    }
  }

  function getFullText(): string {
    if (result?.text) return result.text;
    if (result?.segments) return result.segments.map((s) => s.text).join(" ");
    return "";
  }

  function copyText() {
    navigator.clipboard.writeText(getFullText());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadResult() {
    const text = format === "json" ? JSON.stringify(result, null, 2) : getFullText();
    const ext = format === "json" ? "json" : format === "srt" ? "srt" : format === "vtt" ? "vtt" : "txt";
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${file?.name || "transcript"}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">File Transcription</h1>
        <p className="text-muted-foreground mt-1">
          Upload audio or video files for batch transcription
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
        <strong>Note:</strong> First request may take 30–60s for cold start.
        Supports MP3, WAV, M4A, FLAC, OGG, MP4, WebM, and more.
      </div>

      {/* Upload area */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragging(false)}
        onClick={() => fileInputRef.current?.click()}
        className={`rounded-lg border-2 border-dashed p-12 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-primary bg-primary/5"
            : file
            ? "border-green-500/50 bg-green-500/5"
            : "border-border hover:border-primary/50 hover:bg-muted/50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.ogg,.mp4,.webm,.wma"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="hidden"
        />
        {file ? (
          <div className="space-y-2">
            <FileAudio className="h-12 w-12 mx-auto text-green-500" />
            <p className="font-medium text-foreground">{file.name}</p>
            <p className="text-sm text-muted-foreground">
              {(file.size / 1024 / 1024).toFixed(1)} MB
            </p>
            <p className="text-xs text-muted-foreground">Click or drop to change</p>
          </div>
        ) : (
          <div className="space-y-2">
            <Upload className="h-12 w-12 mx-auto text-muted-foreground" />
            <p className="font-medium">Drop audio file here or click to browse</p>
            <p className="text-sm text-muted-foreground">
              MP3, WAV, M4A, FLAC, OGG, MP4, WebM up to 100MB
            </p>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div>
          <label className="text-sm text-muted-foreground mr-2">Output Format:</label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as "json" | "text" | "srt" | "vtt")}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          >
            <option value="json">JSON (segments + timestamps)</option>
            <option value="text">Plain Text</option>
            <option value="srt">SRT Subtitles</option>
            <option value="vtt">VTT Subtitles</option>
          </select>
        </div>
        <button
          onClick={transcribe}
          disabled={!file || loading}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Transcribing...
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              Transcribe
            </>
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <h2 className="text-xl font-semibold">Results</h2>
              <p className="text-sm text-muted-foreground">
                {result.duration && `Duration: ${formatTime(result.duration)}`}
                {result.language && ` • Language: ${result.language}`}
                {elapsed > 0 && ` • Processed in ${(elapsed / 1000).toFixed(1)}s`}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={copyText}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-sm hover:bg-muted transition-colors"
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
              <button
                onClick={downloadResult}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-sm hover:bg-muted transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </button>
            </div>
          </div>

          {/* Segments with timestamps */}
          {result.segments && result.segments.length > 0 ? (
            <div className="rounded-lg border bg-card divide-y divide-border max-h-[500px] overflow-y-auto">
              {result.segments.map((seg, i) => (
                <div key={i} className="flex gap-4 px-4 py-3">
                  <span className="text-xs font-mono text-primary whitespace-nowrap pt-0.5">
                    {formatTime(seg.start)}
                  </span>
                  <p className="text-sm text-foreground leading-relaxed">{seg.text}</p>
                </div>
              ))}
            </div>
          ) : result.text ? (
            <div className="rounded-lg border bg-card p-6">
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{result.text}</pre>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
