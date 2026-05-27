"use client";

import { useState, useEffect } from "react";
import { Trash2, RefreshCw } from "lucide-react";

interface LogEntry {
  id: string;
  timestamp: string;
  type: "batch" | "live";
  file?: string;
  size?: number;
  duration?: number;
  format?: string;
  status: "success" | "error";
  error?: string;
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    loadLogs();
  }, []);

  function loadLogs() {
    const stored = localStorage.getItem("aavaaz-request-logs");
    if (stored) {
      try {
        setLogs(JSON.parse(stored));
      } catch {
        setLogs([]);
      }
    }
  }

  function clearLogs() {
    localStorage.removeItem("aavaaz-request-logs");
    setLogs([]);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Request Logs</h1>
          <p className="text-muted-foreground mt-1">
            History of API requests from this browser
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadLogs}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border text-sm hover:bg-muted transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            onClick={clearLogs}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-500/30 text-sm text-red-400 hover:bg-red-500/5 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </button>
        </div>
      </div>

      {logs.length === 0 ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <p className="text-muted-foreground">No requests logged yet.</p>
          <p className="text-sm text-muted-foreground mt-1">
            Transcribe a file or use the Live Demo to see logs here.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Time</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">File</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Size</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Format</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {formatDate(log.timestamp)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                      log.type === "batch"
                        ? "bg-blue-500/10 text-blue-400"
                        : "bg-purple-500/10 text-purple-400"
                    }`}>
                      {log.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-foreground truncate max-w-[200px]">
                    {log.file || "—"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                    {log.size ? formatSize(log.size) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {log.format || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {log.status === "success" ? (
                      <span className="inline-flex items-center gap-1 text-green-400 text-xs">
                        <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
                        OK
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-400 text-xs" title={log.error}>
                        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                        Error
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-xs text-muted-foreground">
        Logs are stored in your browser&apos;s localStorage (max 100 entries). 
        They are not synced to the server.
      </div>
    </div>
  );
}
