"use client";

import { useState, useRef } from "react";
import { Volume2, Download, Loader2, Play, Pause } from "lucide-react";

const TTS_ENDPOINT = "https://boxerab--aavaaz-tts.modal.run/v1/tts";
const TTS_STREAM_ENDPOINT = "https://boxerab--aavaaz-tts.modal.run/v1/tts/stream";

const EXAMPLE_TEXTS = [
  "Welcome to Aavaaz, the open-source speech AI platform. We provide state-of-the-art transcription and text-to-speech services.",
  "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet.",
  "In a world driven by artificial intelligence, the ability to convert text to natural-sounding speech opens up countless possibilities for accessibility, content creation, and human-computer interaction.",
];

export default function TTSPage() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState("");
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [processingTime, setProcessingTime] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function startProgress() {
    setProgress(2);
    setProgressStage("Connecting to GPU...");
  }

  function stopProgress() {
    if (progressRef.current) {
      clearInterval(progressRef.current);
      progressRef.current = null;
    }
  }

  async function synthesize() {
    if (!text.trim()) return;
    setLoading(true);
    setError("");
    setAudioUrl(null);
    setProcessingTime(null);
    startProgress();

    try {
      // Use streaming endpoint for real progress
      const res = await fetch(TTS_STREAM_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.trim() }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.error) {
              throw new Error(event.error);
            }

            if (event.progress !== undefined) {
              setProgress(event.progress);
            }
            if (event.stage) {
              setProgressStage(event.stage);
            }

            if (event.audio) {
              // Final event with audio
              const binaryStr = atob(event.audio);
              const bytes = new Uint8Array(binaryStr.length);
              for (let i = 0; i < binaryStr.length; i++) {
                bytes[i] = binaryStr.charCodeAt(i);
              }
              const blob = new Blob([bytes], { type: "audio/wav" });
              const url = URL.createObjectURL(blob);
              setAudioUrl(url);
              if (event.processing_time) {
                setProcessingTime(event.processing_time);
              }
            }
          } catch (parseErr) {
            if (parseErr instanceof Error && parseErr.message !== jsonStr) {
              throw parseErr;
            }
          }
        }
      }

      if (!audioUrl) {
        // Fallback: check if we got audio in the last buffer
        setProgress(100);
        setProgressStage("Done!");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Synthesis failed");
      setProgress(0);
      setProgressStage("");
    } finally {
      stopProgress();
      setLoading(false);
    }
  }

  function togglePlayback() {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  }

  function downloadAudio() {
    if (!audioUrl) return;
    const a = document.createElement("a");
    a.href = audioUrl;
    a.download = "aavaaz-tts-output.wav";
    a.click();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Text to Speech</h1>
        <p className="text-muted-foreground mt-1">
          Generate natural speech from text using Fish Speech AI
        </p>
      </div>

      {/* Cold start warning */}
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
        <strong>Note:</strong> First request may take 30-60s while the GPU container starts up (cold start).
        Subsequent requests are much faster.
      </div>

      {/* Text input */}
      <div className="rounded-lg border bg-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Input Text</h3>
          <span className="text-xs text-muted-foreground">{text.length}/5000</span>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, 5000))}
          placeholder="Enter text to convert to speech..."
          rows={5}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y min-h-[120px]"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={synthesize}
            disabled={loading || !text.trim()}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Volume2 className="h-4 w-4" />
                Generate Speech
              </>
            )}
          </button>
          {processingTime && (
            <span className="text-xs text-muted-foreground">
              Generated in {processingTime}
            </span>
          )}
        </div>
      </div>

      {/* Example texts */}
      <div className="rounded-lg border bg-card p-5 space-y-3">
        <h3 className="font-semibold text-sm text-muted-foreground">Try an example</h3>
        <div className="space-y-2">
          {EXAMPLE_TEXTS.map((example, i) => (
            <button
              key={i}
              onClick={() => setText(example)}
              className="block w-full text-left rounded-md px-3 py-2 text-sm border border-input hover:bg-muted/50 transition-colors truncate"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {/* Progress bar */}
      {loading && (
        <div className="rounded-lg border bg-card p-5 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{progressStage}</span>
            <span className="font-mono text-xs">{progress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Audio output */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {audioUrl && (
        <div className="rounded-lg border bg-card p-5 space-y-4">
          <h3 className="font-semibold">Generated Audio</h3>
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlayback}
              className="h-12 w-12 rounded-full bg-primary flex items-center justify-center hover:bg-primary/90 transition-colors"
            >
              {isPlaying ? (
                <Pause className="h-5 w-5 text-primary-foreground" />
              ) : (
                <Play className="h-5 w-5 text-primary-foreground ml-0.5" />
              )}
            </button>
            <audio
              ref={audioRef}
              src={audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="flex-1"
              controls
            />
            <button
              onClick={downloadAudio}
              className="p-2.5 rounded-md border border-input hover:bg-muted transition-colors"
              title="Download WAV"
            >
              <Download className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* API docs */}
      <div className="rounded-lg border bg-card p-5 space-y-3">
        <h3 className="font-semibold">API Usage</h3>
        <pre className="rounded-md bg-muted/50 p-4 text-xs overflow-x-auto">
          <code>{`curl -X POST ${TTS_ENDPOINT} \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Hello world"}' \\
  --output speech.wav`}</code>
        </pre>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="p-3 rounded bg-muted/30">
            <p className="font-medium text-xs text-muted-foreground">Model</p>
            <p>Fish Speech 1.5</p>
          </div>
          <div className="p-3 rounded bg-muted/30">
            <p className="font-medium text-xs text-muted-foreground">Languages</p>
            <p>13+ (EN, ZH, JA, KO, ...)</p>
          </div>
          <div className="p-3 rounded bg-muted/30">
            <p className="font-medium text-xs text-muted-foreground">Output Format</p>
            <p>WAV (44.1kHz)</p>
          </div>
        </div>
      </div>
    </div>
  );
}
