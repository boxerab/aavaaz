"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { billing, UsageSummary } from "@/lib/api";

export default function UsagePage() {
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
          // API not connected
        }
      }
    }
    load();
  }, [getToken]);

  const quota = usage?.quota || { audio_minutes_limit: 60, audio_minutes_used: 0 };
  const percentUsed = quota.audio_minutes_limit
    ? (quota.audio_minutes_used / quota.audio_minutes_limit) * 100
    : 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Usage</h1>
        <p className="text-muted-foreground mt-1">
          Monitor your transcription usage and quotas
        </p>
      </div>

      {/* Quota bar */}
      <div className="rounded-lg border bg-card p-6">
        <div className="flex justify-between items-center mb-3">
          <span className="text-sm font-medium">Monthly Audio Minutes</span>
          <span className="text-sm text-muted-foreground">
            {quota.audio_minutes_used.toFixed(1)} /{" "}
            {quota.audio_minutes_limit} min
          </span>
        </div>
        <div className="h-3 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all"
            style={{ width: `${Math.min(percentUsed, 100)}%` }}
          />
        </div>
        {percentUsed > 80 && (
          <p className="text-xs text-amber-500 mt-2">
            You&apos;re approaching your monthly limit. Consider upgrading your
            plan.
          </p>
        )}
      </div>

      {/* Daily usage chart (table form for MVP) */}
      <div className="rounded-lg border">
        <div className="p-4 border-b">
          <h3 className="font-semibold">Daily Usage (Current Month)</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="text-left p-4 font-medium">Date</th>
              <th className="text-right p-4 font-medium">Minutes</th>
              <th className="text-right p-4 font-medium">Requests</th>
              <th className="text-right p-4 font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            {usage?.daily_usage && usage.daily_usage.length > 0 ? (
              usage.daily_usage.map((day) => (
                <tr key={day.date} className="border-b last:border-0">
                  <td className="p-4">{day.date}</td>
                  <td className="p-4 text-right">
                    {day.audio_minutes.toFixed(1)}
                  </td>
                  <td className="p-4 text-right">{day.requests}</td>
                  <td className="p-4 text-right">${day.cost_usd.toFixed(4)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={4}
                  className="p-8 text-center text-muted-foreground"
                >
                  No usage data yet. Make your first API call to see stats here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
