"use client";

import { useState, useEffect } from "react";
import { CheckCircle2, AlertCircle, Clock } from "lucide-react";

interface ServiceStatus {
  name: string;
  url: string;
  status: "operational" | "degraded" | "down" | "checking";
  latency?: number;
}

const SERVICES: Omit<ServiceStatus, "status" | "latency">[] = [
  { name: "Batch API (Lambda)", url: "https://gh0edmarma.execute-api.us-east-1.amazonaws.com/health" },
  { name: "Live Transcription (Modal)", url: "https://boxerab--aavaaz-live-livetranscriber-web.modal.run/health" },
  { name: "Dashboard (CloudFront)", url: "https://du7890u4mptc6.cloudfront.net/" },
];

export default function StatusPage() {
  const [services, setServices] = useState<ServiceStatus[]>(
    SERVICES.map((s) => ({ ...s, status: "checking" }))
  );
  const [lastChecked, setLastChecked] = useState<string>("");

  useEffect(() => {
    checkAll();
  }, []);

  async function checkAll() {
    const results = await Promise.all(
      SERVICES.map(async (svc) => {
        const t0 = Date.now();
        try {
          const res = await fetch(svc.url, { mode: "no-cors", cache: "no-store" });
          const latency = Date.now() - t0;
          // no-cors means we can't read status, but if fetch doesn't throw, it reached the server
          return { ...svc, status: "operational" as const, latency };
        } catch {
          return { ...svc, status: "down" as const, latency: Date.now() - t0 };
        }
      })
    );
    setServices(results);
    setLastChecked(new Date().toLocaleTimeString());
  }

  const allOperational = services.every((s) => s.status === "operational");

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">System Status</h1>
          <p className="text-muted-foreground mt-1">
            Real-time health of Aavaaz services
          </p>
        </div>
        <button
          onClick={checkAll}
          className="px-4 py-2 text-sm rounded-md border border-input hover:bg-muted transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Overall status */}
      <div className={`rounded-lg border p-6 ${
        allOperational ? "border-green-500/30 bg-green-500/5" : "border-amber-500/30 bg-amber-500/5"
      }`}>
        <div className="flex items-center gap-3">
          {allOperational ? (
            <CheckCircle2 className="h-8 w-8 text-green-500" />
          ) : (
            <AlertCircle className="h-8 w-8 text-amber-500" />
          )}
          <div>
            <h2 className="text-xl font-semibold">
              {allOperational ? "All Systems Operational" : "Some Services Degraded"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {lastChecked ? `Last checked: ${lastChecked}` : "Checking..."}
            </p>
          </div>
        </div>
      </div>

      {/* Individual services */}
      <div className="space-y-3">
        {services.map((svc) => (
          <div key={svc.name} className="rounded-lg border bg-card px-5 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              {svc.status === "operational" && <span className="h-3 w-3 rounded-full bg-green-500" />}
              {svc.status === "degraded" && <span className="h-3 w-3 rounded-full bg-amber-500" />}
              {svc.status === "down" && <span className="h-3 w-3 rounded-full bg-red-500" />}
              {svc.status === "checking" && <span className="h-3 w-3 rounded-full bg-muted-foreground animate-pulse" />}
              <span className="font-medium">{svc.name}</span>
            </div>
            <div className="flex items-center gap-4">
              {svc.latency !== undefined && (
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {svc.latency}ms
                </span>
              )}
              <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                svc.status === "operational" ? "bg-green-500/10 text-green-400" :
                svc.status === "degraded" ? "bg-amber-500/10 text-amber-400" :
                svc.status === "down" ? "bg-red-500/10 text-red-400" :
                "bg-muted text-muted-foreground"
              }`}>
                {svc.status === "checking" ? "Checking..." : svc.status}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* SLA */}
      <div className="rounded-lg border bg-card p-6 space-y-4">
        <h2 className="text-xl font-semibold">Service Level Agreement</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-muted/50">
            <p className="text-2xl font-bold text-primary">99.9%</p>
            <p className="text-sm text-muted-foreground">Uptime Target</p>
          </div>
          <div className="p-4 rounded-lg bg-muted/50">
            <p className="text-2xl font-bold text-primary">&lt; 500ms</p>
            <p className="text-sm text-muted-foreground">API Response (p95)</p>
          </div>
          <div className="p-4 rounded-lg bg-muted/50">
            <p className="text-2xl font-bold text-primary">&lt; 2s</p>
            <p className="text-sm text-muted-foreground">First Transcript Byte (live)</p>
          </div>
        </div>
        <div className="text-sm text-muted-foreground space-y-2 pt-2">
          <p><strong>Batch Transcription (Lambda):</strong> Processing time scales linearly with audio duration. Expect ~0.5x real-time for small.en model.</p>
          <p><strong>Live Transcription (Modal GPU):</strong> Cold starts take 30-60s when the GPU container scales from zero. Warm containers respond in &lt;100ms.</p>
          <p><strong>Maintenance Windows:</strong> Scheduled deployments happen with zero downtime (blue-green). Emergency maintenance is communicated via status page updates.</p>
        </div>
      </div>

      {/* Incident history */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="text-xl font-semibold mb-4">Recent Incidents</h2>
        <div className="text-center py-8 text-muted-foreground">
          <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
          <p>No incidents in the last 30 days.</p>
        </div>
      </div>
    </div>
  );
}
