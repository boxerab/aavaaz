import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center space-y-8">
        <h1 className="text-5xl font-bold tracking-tight text-foreground">
          Aavaaz
        </h1>
        <p className="text-xl text-muted-foreground">
          Enterprise-grade speech-to-text platform. Real-time streaming, batch
          processing, speaker diarization, PII redaction, and more.
        </p>

        <div className="flex gap-4 justify-center">
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-6 py-3 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            Create Account
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-8">
          <div className="rounded-lg border bg-card p-6 text-left">
            <h3 className="font-semibold text-card-foreground">
              Real-Time Streaming
            </h3>
            <p className="text-sm text-muted-foreground mt-2">
              WebSocket-based live transcription with sub-second latency.
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-left">
            <h3 className="font-semibold text-card-foreground">
              Batch Processing
            </h3>
            <p className="text-sm text-muted-foreground mt-2">
              Upload files via REST API. OpenAI-compatible endpoint.
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-left">
            <h3 className="font-semibold text-card-foreground">
              Intelligence
            </h3>
            <p className="text-sm text-muted-foreground mt-2">
              Diarization, sentiment, topics, entities, summarization.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
