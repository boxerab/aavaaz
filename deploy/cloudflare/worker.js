/**
 * Aavaaz — Cloudflare Workers AI batch transcription
 *
 * Receives audio via POST, transcribes with @cf/openai/whisper,
 * applies Aavaaz post-processing (PII redaction, formatting),
 * and returns the transcript or stores it in R2.
 *
 * Environment bindings (wrangler.toml):
 *   AI          — Workers AI binding
 *   TRANSCRIPTS — R2 bucket (optional, for storing results)
 *
 * Environment variables:
 *   AAVAAZ_ENABLE_PII    — "1" to redact PII (default: "0")
 *   AAVAAZ_ENABLE_FORMAT — "1" to apply smart formatting (default: "1")
 *   AAVAAZ_OUTPUT_FORMAT — "json" | "text" | "srt" | "vtt" (default: "json")
 *   AAVAAZ_API_KEY       — optional API key for authentication
 */

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
      });
    }

    if (request.method !== "POST") {
      return jsonResponse({ error: "Method not allowed" }, 405);
    }

    // Auth check
    const apiKey = env.AAVAAZ_API_KEY;
    if (apiKey) {
      const auth = request.headers.get("Authorization");
      if (!auth || auth !== `Bearer ${apiKey}`) {
        return jsonResponse({ error: "Unauthorized" }, 401);
      }
    }

    try {
      const contentType = request.headers.get("Content-Type") || "";
      let audioData;
      let filename = "audio.wav";

      if (contentType.includes("application/json")) {
        const body = await request.json();
        if (body.audio_base64) {
          audioData = base64ToArrayBuffer(body.audio_base64);
          filename = body.filename || filename;
        } else if (body.audio_url && env.TRANSCRIPTS) {
          // Fetch from R2
          const key = body.audio_url.replace(/^r2:\/\//, "");
          const obj = await env.TRANSCRIPTS.get(key);
          if (!obj) {
            return jsonResponse({ error: "Object not found in R2" }, 404);
          }
          audioData = await obj.arrayBuffer();
          filename = key.split("/").pop() || filename;
        } else {
          return jsonResponse(
            { error: "Provide 'audio_base64' or 'audio_url' (r2://key)" },
            400,
          );
        }
      } else {
        // Raw binary upload
        audioData = await request.arrayBuffer();
        filename =
          request.headers.get("X-Filename") ||
          new URL(request.url).searchParams.get("filename") ||
          filename;
      }

      if (!audioData || audioData.byteLength === 0) {
        return jsonResponse({ error: "Empty audio data" }, 400);
      }

      // Transcribe with Workers AI
      const result = await env.AI.run("@cf/openai/whisper", {
        audio: [...new Uint8Array(audioData)],
      });

      // Build segments from Workers AI response
      let segments = [];
      if (result.words && result.words.length > 0) {
        // Workers AI returns word-level data — group into segments
        segments = groupWordsIntoSegments(result.words);
      } else if (result.text) {
        segments = [{ start: 0, end: 0, text: result.text.trim() }];
      }

      // Apply post-processing pipeline
      const enablePII = env.AAVAAZ_ENABLE_PII === "1";
      const enableFormat = (env.AAVAAZ_ENABLE_FORMAT || "1") === "1";

      for (let i = 0; i < segments.length; i++) {
        if (enableFormat) {
          segments[i] = applySmartFormatting(segments[i]);
        }
        if (enablePII) {
          segments[i] = redactPII(segments[i]);
        }
      }

      const transcript = {
        text: result.text || "",
        word_count: result.word_count || 0,
        segments,
      };

      const outputFormat = env.AAVAAZ_OUTPUT_FORMAT || "json";
      const output = formatOutput(transcript, outputFormat);

      // Optionally store in R2
      if (env.TRANSCRIPTS) {
        const stem = filename.replace(/\.[^.]+$/, "");
        const ext = outputFormat === "json" ? "json" : "txt";
        const key = `transcripts/${stem}.${ext}`;
        await env.TRANSCRIPTS.put(key, output);
      }

      const ct =
        outputFormat === "json" ? "application/json" : "text/plain";
      return new Response(output, {
        headers: {
          "Content-Type": ct,
          "Access-Control-Allow-Origin": "*",
        },
      });
    } catch (err) {
      console.error("Transcription error:", err);
      return jsonResponse({ error: err.message || "Internal error" }, 500);
    }
  },
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function groupWordsIntoSegments(words, maxGapSec = 1.5) {
  const segments = [];
  let current = { start: 0, end: 0, text: "", words: [] };

  for (const w of words) {
    if (
      current.words.length > 0 &&
      w.start - current.end > maxGapSec
    ) {
      current.text = current.text.trim();
      segments.push(current);
      current = { start: w.start, end: w.end, text: "", words: [] };
    }
    if (current.words.length === 0) {
      current.start = w.start;
    }
    current.end = w.end;
    current.text += w.word;
    current.words.push(w);
  }

  if (current.words.length > 0) {
    current.text = current.text.trim();
    segments.push(current);
  }

  return segments;
}

// ── Smart Formatting ─────────────────────────────────────────────────────────

function applySmartFormatting(segment) {
  let text = segment.text;
  // Capitalize first letter
  if (text.length > 0) {
    text = text.charAt(0).toUpperCase() + text.slice(1);
  }
  // Ensure trailing period
  if (text.length > 0 && !/[.!?]$/.test(text)) {
    text += ".";
  }
  return { ...segment, text };
}

// ── PII Redaction ────────────────────────────────────────────────────────────

const PII_PATTERNS = [
  { pattern: /\b\d{3}[-.]?\d{2}[-.]?\d{4}\b/g, replacement: "[SSN_REDACTED]" },
  {
    pattern: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
    replacement: "[CARD_REDACTED]",
  },
  {
    pattern: /\b[\w.+-]+@[\w-]+\.[\w.]+\b/g,
    replacement: "[EMAIL_REDACTED]",
  },
  {
    pattern: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
    replacement: "[PHONE_REDACTED]",
  },
];

function redactPII(segment) {
  let text = segment.text;
  for (const { pattern, replacement } of PII_PATTERNS) {
    text = text.replace(pattern, replacement);
  }
  return { ...segment, text };
}

// ── Output Formatting ────────────────────────────────────────────────────────

function formatOutput(transcript, format) {
  if (format === "text") {
    return transcript.segments.map((s) => s.text).join("\n");
  }
  if (format === "srt") {
    return transcript.segments
      .map((s, i) => {
        return `${i + 1}\n${formatTS(s.start)} --> ${formatTS(s.end)}\n${s.text}\n`;
      })
      .join("\n");
  }
  if (format === "vtt") {
    return (
      "WEBVTT\n\n" +
      transcript.segments
        .map((s) => `${formatTS(s.start)} --> ${formatTS(s.end)}\n${s.text}\n`)
        .join("\n")
    );
  }
  return JSON.stringify(transcript, null, 2);
}

function formatTS(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(ms).padStart(3, "0")}`;
}
