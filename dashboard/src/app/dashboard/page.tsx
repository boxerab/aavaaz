"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { billing, UsageSummary } from "@/lib/api";

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    async function load() {
      const token = await getToken();
      if (token) {
        try {
          const data = await billing.usage(token);
          setUsage(data);
        } catch {
          // API not yet connected — show placeholder
        }
      }
    }
    load();
  }, [getToken]);

  const stats = usage?.current_month || {
    audio_minutes: 0,
    requests: 0,
    cost_usd: 0,
  };
  const quota = usage?.quota || { audio_minutes_limit: 60, audio_minutes_used: 0 };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Your transcription platform overview
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          label="Audio Minutes"
          value={stats.audio_minutes.toFixed(1)}
          subtitle={`of ${quota.audio_minutes_limit} min quota`}
        />
        <StatCard
          label="API Requests"
          value={stats.requests.toLocaleString()}
          subtitle="this month"
        />
        <StatCard
          label="Cost"
          value={`$${stats.cost_usd.toFixed(2)}`}
          subtitle="current month"
        />
        <StatCard
          label="Plan"
          value={usage?.plan || "Free"}
          subtitle="current tier"
        />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-lg border bg-card p-6">
          <h3 className="font-semibold text-lg mb-2">Quick Start</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Use your API key to transcribe audio via our REST API:
          </p>
          <pre className="bg-muted rounded-md p-4 text-xs overflow-x-auto">
{`curl -X POST https://api.aavaaz.dev/v1/audio/transcriptions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -F file=@audio.wav -F model=large-v3`}
          </pre>
        </div>

        <div className="rounded-lg border bg-card p-6">
          <h3 className="font-semibold text-lg mb-2">WebSocket Streaming</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Connect via WebSocket for real-time live transcription:
          </p>
          <pre className="bg-muted rounded-md p-4 text-xs overflow-x-auto">
{`const ws = new WebSocket(
  "wss://api.aavaaz.dev/ws?token=YOUR_API_KEY"
);
ws.onmessage = (e) => console.log(JSON.parse(e.data));`}
          </pre>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value: string;
  subtitle: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-6">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
    </div>
  );
}
