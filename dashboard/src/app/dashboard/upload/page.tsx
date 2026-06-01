"use client";

import { useState, useRef, useCallback } from "react";
import { Upload, FileAudio, Loader2, Download, Copy, Check, XCircle } from "lucide-react";
import { useUpload, type TranscriptionResult } from "@/lib/upload-context";

const BATCH_URL =
  process.env.NEXT_PUBLIC_BATCH_URL ||
  "https://gh0edmarma.execute-api.us-east-1.amazonaws.com/v1/audio/transcriptions";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://gh0edmarma.execute-api.us-east-1.amazonaws.com";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function UploadPage() {
  const {
    file, setFile,
    loading, setLoading,
    progress, setProgress,
    progressStage, setProgressStage,
    result, setResult,
    error, setError,
    elapsed, setElapsed,
    format, setFormat,
  } = useUpload();
  const [dragging, setDragging] = useState(false);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeXhrRef = useRef<XMLHttpRequest | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeUploadKeyRef = useRef<string | null>(null);
  const cancelRequestedRef = useRef(false);

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
    cancelRequestedRef.current = false;
    abortControllerRef.current = new AbortController();
    activeUploadKeyRef.current = null;
    setLoading(true);
    setError("");
    setResult(null);
    setProgress(0);
    setProgressStage("Preparing...");
    const t0 = Date.now();

    try {
      // Load feature config from settings
      let features = null;
      try {
        const stored = localStorage.getItem("aavaaz-features-config");
        if (stored) features = JSON.parse(stored);
      } catch { /* ignore */ }

      const apiKey = localStorage.getItem("aavaaz-api-key") || "";

      // For files > 4MB, use S3 presigned URL upload path
      // For smaller files, use direct base64 JSON (faster, no S3 round-trip)
      if (file.size > 4 * 1024 * 1024) {
        await transcribeLargeFile(file, features, apiKey, t0);
      } else {
        await transcribeSmallFile(file, features, apiKey, t0);
      }
    } catch (err) {
      if (cancelRequestedRef.current) {
        setError("Transcription canceled.");
        return;
      }
      setError(err instanceof Error ? err.message : "Unknown error");
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
      activeXhrRef.current = null;
      abortControllerRef.current = null;
    }
  }

  async function cancelTranscription() {
    cancelRequestedRef.current = true;
    activeXhrRef.current?.abort();
    abortControllerRef.current?.abort();

    const key = activeUploadKeyRef.current;
    if (key) {
      const encodedKey = btoa(key).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      const apiKey = localStorage.getItem("aavaaz-api-key") || "";
      const headers: Record<string, string> = {};
      if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

      try {
        await fetch(`${API_BASE}/v1/transcription/${encodedKey}`, {
          method: "DELETE",
          headers,
        });
      } catch {
        // Local cancellation should still complete if remote cleanup is unavailable.
      }
    }

    setLoading(false);
    setProgress(0);
    setProgressStage("Canceled");
    setError("Transcription canceled.");
  }

  async function transcribeLargeFile(
    file: File,
    features: Record<string, unknown> | null,
    apiKey: string,
    t0: number
  ) {
    // Step 1: Get presigned upload URL
    setProgress(5);
    setProgressStage("Getting upload URL...");
    const urlParams = new URLSearchParams({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
    });
    const headers: Record<string, string> = {};
    if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    const urlRes = await fetch(`${API_BASE}/v1/upload-url?${urlParams}`, {
      headers,
      signal: abortControllerRef.current?.signal,
    });
    if (!urlRes.ok) {
      throw new Error(`Failed to get upload URL: ${await urlRes.text()}`);
    }
    const { upload_url, key } = await urlRes.json();
    activeUploadKeyRef.current = key;

    // Step 2: Upload file directly to S3 via presigned URL (no size limit)
    setProgress(10);
    setProgressStage("Uploading to S3...");

    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      activeXhrRef.current = xhr;
      xhr.open("PUT", upload_url);
      xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = 10 + (e.loaded / e.total) * 40;
          setProgress(Math.round(pct));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`S3 upload failed: HTTP ${xhr.status}`));
      };
      xhr.onerror = () => reject(new Error("S3 upload network error"));
      xhr.onabort = () => reject(new Error("Upload canceled"));
      xhr.timeout = 300000;
      xhr.ontimeout = () => reject(new Error("Upload timed out"));
      xhr.send(file);
    });

    // Step 3: Poll for transcription result (S3 trigger handles processing)
    setProgress(55);
    setProgressStage("Transcribing audio...");

    // Encode the upload key as URL-safe base64 for the status endpoint
    const keyBase64 = btoa(key).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

    const headers2: Record<string, string> = {};
    if (apiKey) headers2["Authorization"] = `Bearer ${apiKey}`;

    // Poll until transcription completes
    const maxWait = 300000; // 5 minutes
    const pollInterval = 3000; // 3 seconds
    const startPoll = Date.now();
    let data: TranscriptionResult | null = null;

    while (Date.now() - startPoll < maxWait) {
      if (cancelRequestedRef.current) throw new Error("Transcription canceled");
      await new Promise((r) => setTimeout(r, pollInterval));

      const statusRes = await fetch(
        `${API_BASE}/v1/transcription/${keyBase64}`,
        { headers: headers2, signal: abortControllerRef.current?.signal }
      );

      if (!statusRes.ok) {
        // Keep polling on transient errors
        continue;
      }

      const statusData = await statusRes.json();

      if (statusData.status === "failed") {
        throw new Error(statusData.error || "Transcription failed");
      }

      if (statusData.status === "canceled") {
        throw new Error("Transcription canceled");
      }

      if (statusData.status === "completed") {
        // Parse the transcript (it's stored as a JSON string)
        try {
          data = typeof statusData.transcript === "string"
            ? JSON.parse(statusData.transcript)
            : statusData.transcript;
        } catch {
          data = { segments: [], text: statusData.transcript };
        }
        break;
      }

      // Update progress from server
      if (statusData.progress) {
        const serverPct = Math.min(90, 55 + Math.round(statusData.progress * 0.35));
        setProgress(serverPct);
      } else {
        // Simulate slow progress
        const elapsed = (Date.now() - startPoll) / 1000;
        setProgress(Math.min(88, 55 + Math.round(elapsed / 3)));
      }
    }

    if (!data) {
      throw new Error("Transcription timed out — file may still be processing");
    }

    setProgress(95);
    setProgressStage("Processing result...");
    setResult(data);
    setProgress(100);
    setProgressStage("Done!");
    setElapsed(Date.now() - t0);
    logSuccess(file, t0);
  }

  async function transcribeSmallFile(
    file: File,
    features: Record<string, unknown> | null,
    apiKey: string,
    t0: number
  ) {
    // Direct base64 upload (faster for small files)
    setProgress(10);
    setProgressStage("Encoding audio...");
    const arrayBuffer = await file.arrayBuffer();
    const base64 = btoa(
      new Uint8Array(arrayBuffer).reduce(
        (data, byte) => data + String.fromCharCode(byte),
        ""
      )
    );

    setProgress(25);
    setProgressStage("Uploading to server...");

    const body: Record<string, unknown> = {
      audio_base64: base64,
      response_format: format,
    };
    if (features) body.features = features;

    // Use XMLHttpRequest for upload progress
    const response = await new Promise<string>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      activeXhrRef.current = xhr;
      xhr.open("POST", BATCH_URL);
      xhr.setRequestHeader("Content-Type", "application/json");
      if (apiKey) xhr.setRequestHeader("Authorization", `Bearer ${apiKey}`);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const uploadPct = 25 + (e.loaded / e.total) * 25;
          setProgress(Math.round(uploadPct));
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.responseText);
        } else {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText}`));
        }
      };

        xhr.onerror = () => reject(new Error("Network error — check your connection"));
        xhr.onabort = () => reject(new Error("Transcription canceled"));
      xhr.ontimeout = () => reject(new Error("Request timed out (>5min)"));
      xhr.timeout = 300000;

      xhr.upload.onload = () => {
        setProgress(50);
        setProgressStage("Transcribing audio...");
        let pct = 50;
        const interval = setInterval(() => {
          pct = Math.min(pct + 2, 90);
          setProgress(pct);
        }, 1000);
        xhr.onloadend = () => clearInterval(interval);
      };

      xhr.send(JSON.stringify(body));
    });

    setProgress(95);
    setProgressStage("Processing result...");

    try {
      const data = JSON.parse(response);
      setResult(data);
    } catch {
      setResult({ segments: [], text: response });
    }

    setProgress(100);
    setProgressStage("Done!");
    setElapsed(Date.now() - t0);
    logSuccess(file, t0);
  }

  function logSuccess(file: File, t0: number) {
    const logs = JSON.parse(localStorage.getItem("aavaaz-request-logs") || "[]");
    logs.unshift({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      type: "batch",
      file: file.name,
      size: file.size,
      duration: (Date.now() - t0) / 1000,
      format,
      status: "success",
    });
    localStorage.setItem("aavaaz-request-logs", JSON.stringify(logs.slice(0, 100)));
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
        Supports MP3, WAV, M4A, FLAC, OGG, MOV, MP4, WebM, and more.
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
          accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.ogg,.mov,.mp4,.webm,.wma"
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
              MP3, WAV, M4A, FLAC, OGG, MOV, MP4, WebM up to 25MB
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
        {loading && (
          <button
            onClick={cancelTranscription}
            className="inline-flex items-center gap-2 rounded-md border border-red-500/40 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-500/10 transition-colors"
          >
            <XCircle className="h-4 w-4" />
            Cancel
          </button>
        )}
      </div>

      {/* Progress bar */}
      {loading && (
        <div className="rounded-lg border bg-card p-5 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{progressStage}</span>
            <span className="font-mono text-primary">{progress}%</span>
          </div>
          <div className="h-3 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {progress < 50
              ? "Uploading audio to transcription server..."
              : progress < 90
              ? "AI model is processing your audio. This may take a moment for longer files..."
              : "Almost done..."}
          </p>
        </div>
      )}

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
