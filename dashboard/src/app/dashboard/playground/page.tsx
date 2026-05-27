"use client";

import { useState } from "react";
import { Play, Copy, Check } from "lucide-react";

const ENDPOINTS = {
  batch: {
    label: "Batch Transcription",
    url: "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/v1/audio/transcriptions",
    method: "POST",
    description: "Upload audio file for transcription (OpenAI-compatible API)",
  },
  live: {
    label: "Live WebSocket",
    url: "wss://boxerab--aavaaz-live-livetranscriber-web.modal.run/ws",
    method: "WebSocket",
    description: "Real-time streaming transcription via WebSocket",
  },
  health_batch: {
    label: "Health (Batch)",
    url: "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/health",
    method: "GET",
    description: "Check batch service health and model info",
  },
  health_live: {
    label: "Health (Live)",
    url: "https://boxerab--aavaaz-live-livetranscriber-web.modal.run/health",
    method: "GET",
    description: "Check live service health and model info",
  },
};

type EndpointKey = keyof typeof ENDPOINTS;

const CODE_EXAMPLES: Record<string, { curl: string; python: string; javascript: string }> = {
  batch: {
    curl: `curl -X POST \\
  "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/v1/audio/transcriptions" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -F "file=@audio.mp3" \\
  -F "response_format=json"`,
    python: `import requests

url = "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/v1/audio/transcriptions"
headers = {"Authorization": "Bearer YOUR_API_KEY"}

with open("audio.mp3", "rb") as f:
    response = requests.post(
        url,
        headers=headers,
        files={"file": f},
        data={"response_format": "json"},
    )

result = response.json()
for segment in result["segments"]:
    print(f"[{segment['start']:.1f}s] {segment['text']}")`,
    javascript: `const formData = new FormData();
formData.append("file", audioFile);
formData.append("response_format", "json");

const response = await fetch(
  "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/v1/audio/transcriptions",
  {
    method: "POST",
    headers: { Authorization: "Bearer YOUR_API_KEY" },
    body: formData,
  }
);

const result = await response.json();
result.segments.forEach(seg => {
  console.log(\`[\${seg.start.toFixed(1)}s] \${seg.text}\`);
});`,
  },
  live: {
    curl: `# WebSocket — use wscat or similar
wscat -c "wss://boxerab--aavaaz-live-livetranscriber-web.modal.run/ws"
# Then send JSON options:
# {"uid":"test","language":null,"model":"large-v3","use_vad":true}
# Then send raw Float32 PCM audio at 16kHz`,
    python: `import asyncio
import json
import numpy as np
import websockets

async def transcribe_stream():
    uri = "wss://boxerab--aavaaz-live-livetranscriber-web.modal.run/ws"
    async with websockets.connect(uri) as ws:
        # Send client options
        await ws.send(json.dumps({
            "uid": "my-session",
            "language": None,
            "model": "large-v3",
            "use_vad": True,
        }))

        # Send audio chunks (16kHz Float32 PCM)
        # audio = load_audio_as_float32_16khz()
        # for chunk in np.array_split(audio, len(audio) // 4096):
        #     await ws.send(chunk.tobytes())

        # Receive transcription segments
        async for message in ws:
            data = json.loads(message)
            if "segments" in data:
                for seg in data["segments"]:
                    print(seg["text"], end=" ", flush=True)

asyncio.run(transcribe_stream())`,
    javascript: `const ws = new WebSocket(
  "wss://boxerab--aavaaz-live-livetranscriber-web.modal.run/ws"
);

ws.onopen = () => {
  ws.send(JSON.stringify({
    uid: crypto.randomUUID(),
    language: null,
    model: "large-v3",
    use_vad: true,
  }));

  // Then send Float32 PCM audio at 16kHz
  // Use AudioContext + ScriptProcessorNode to capture mic
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.segments) {
    const text = data.segments.map(s => s.text).join(" ");
    console.log(text);
  }
};`,
  },
  health_batch: {
    curl: `curl "https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/health"`,
    python: `import requests
r = requests.get("https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/health")
print(r.json())`,
    javascript: `const r = await fetch("https://boxerab--aavaaz-transcribe-transcriber-web.modal.run/health");
console.log(await r.json());`,
  },
  health_live: {
    curl: `curl "https://boxerab--aavaaz-live-livetranscriber-web.modal.run/health"`,
    python: `import requests
r = requests.get("https://boxerab--aavaaz-live-livetranscriber-web.modal.run/health")
print(r.json())`,
    javascript: `const r = await fetch("https://boxerab--aavaaz-live-livetranscriber-web.modal.run/health");
console.log(await r.json());`,
  },
};

export default function PlaygroundPage() {
  const [endpoint, setEndpoint] = useState<EndpointKey>("batch");
  const [lang, setLang] = useState<"curl" | "python" | "javascript">("curl");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const ep = ENDPOINTS[endpoint];
  const code = CODE_EXAMPLES[endpoint]?.[lang] || "";

  async function tryEndpoint() {
    if (ep.method === "WebSocket") {
      setResponse("WebSocket endpoints can't be tested directly here.\nUse the Live Demo page or wscat in terminal.");
      return;
    }
    setLoading(true);
    setResponse("");
    try {
      const res = await fetch(ep.url, { method: ep.method });
      const text = await res.text();
      try {
        setResponse(JSON.stringify(JSON.parse(text), null, 2));
      } catch {
        setResponse(text);
      }
    } catch (err) {
      setResponse(`Error: ${err instanceof Error ? err.message : "Unknown"}`);
    } finally {
      setLoading(false);
    }
  }

  function copyCode() {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">API Playground</h1>
        <p className="text-muted-foreground mt-1">
          Explore and test the Aavaaz API endpoints
        </p>
      </div>

      {/* Endpoint selector */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {(Object.entries(ENDPOINTS) as [EndpointKey, typeof ENDPOINTS[EndpointKey]][]).map(([key, ep]) => (
          <button
            key={key}
            onClick={() => setEndpoint(key)}
            className={`rounded-lg border p-4 text-left transition-colors ${
              endpoint === key
                ? "border-primary bg-primary/5"
                : "hover:border-border hover:bg-muted/50"
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                ep.method === "POST" ? "bg-green-500/10 text-green-400" :
                ep.method === "GET" ? "bg-blue-500/10 text-blue-400" :
                "bg-purple-500/10 text-purple-400"
              }`}>{ep.method}</span>
              <span className="text-sm font-medium">{ep.label}</span>
            </div>
            <p className="text-xs text-muted-foreground">{ep.description}</p>
          </button>
        ))}
      </div>

      {/* Endpoint details */}
      <div className="rounded-lg border bg-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-lg">{ep.label}</h2>
            <code className="text-xs text-muted-foreground font-mono">{ep.method} {ep.url}</code>
          </div>
          {ep.method !== "WebSocket" && (
            <button
              onClick={tryEndpoint}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {loading ? "Running..." : "Try it"}
            </button>
          )}
        </div>

        {response && (
          <div className="rounded-md bg-background border p-4">
            <p className="text-xs text-muted-foreground mb-2">Response:</p>
            <pre className="text-sm font-mono overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">{response}</pre>
          </div>
        )}
      </div>

      {/* Code examples */}
      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="flex items-center justify-between border-b px-4 py-2">
          <div className="flex gap-1">
            {(["curl", "python", "javascript"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  lang === l
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {l === "curl" ? "cURL" : l === "python" ? "Python" : "JavaScript"}
              </button>
            ))}
          </div>
          <button
            onClick={copyCode}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <pre className="p-4 text-sm font-mono overflow-x-auto max-h-96 overflow-y-auto leading-relaxed">
          <code>{code}</code>
        </pre>
      </div>

      {/* OpenAI compatibility note */}
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-semibold mb-2">OpenAI-Compatible API</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          The batch transcription endpoint is compatible with the OpenAI Audio API.
          You can use the official OpenAI SDK by changing the base URL:
        </p>
        <pre className="mt-3 text-sm font-mono bg-background rounded-md p-3 overflow-x-auto">{`from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://boxerab--aavaaz-transcribe-transcriber-web.modal.run"
)

transcript = client.audio.transcriptions.create(
    model="large-v3",
    file=open("audio.mp3", "rb"),
)`}</pre>
      </div>
    </div>
  );
}
