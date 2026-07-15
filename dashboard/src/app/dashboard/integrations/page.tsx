"use client";

import { ExternalLink, Copy, Check } from "lucide-react";
import { useState } from "react";

interface Integration {
  id: string;
  name: string;
  description: string;
  category: "automation" | "storage" | "communication" | "analytics";
  icon: string;
  webhookTemplate?: string;
  docsUrl?: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "zapier",
    name: "Zapier",
    description: "Connect Aavaaz to 5000+ apps. Trigger workflows when transcripts complete.",
    category: "automation",
    icon: "⚡",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://hooks.zapier.com/hooks/catch/YOUR_HOOK_ID",
  "payload": {
    "text": "{{transcript.text}}",
    "duration": "{{transcript.duration}}",
    "language": "{{transcript.language}}",
    "segments": "{{transcript.segments}}"
  }
}`,
    docsUrl: "https://zapier.com/apps/webhook",
  },
  {
    id: "n8n",
    name: "n8n",
    description: "Open-source workflow automation. Self-host or use cloud.",
    category: "automation",
    icon: "🔄",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://your-n8n.example.com/webhook/aavaaz",
  "payload": {
    "text": "{{transcript.text}}",
    "file": "{{transcript.filename}}",
    "timestamp": "{{transcript.created_at}}"
  }
}`,
    docsUrl: "https://docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.webhook/",
  },
  {
    id: "slack",
    name: "Slack",
    description: "Post transcription results to a Slack channel automatically.",
    category: "communication",
    icon: "💬",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
  "payload": {
    "text": "📝 New transcript ready:\\n*File:* {{transcript.filename}}\\n*Duration:* {{transcript.duration}}s\\n*Language:* {{transcript.language}}\\n\\n> {{transcript.text | truncate:500}}"
  }
}`,
    docsUrl: "https://api.slack.com/messaging/webhooks",
  },
  {
    id: "s3",
    name: "Amazon S3",
    description: "Automatically store transcripts in your S3 bucket.",
    category: "storage",
    icon: "🪣",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "storage": {
    "type": "s3",
    "bucket": "your-bucket-name",
    "prefix": "transcripts/",
    "format": "json",
    "region": "us-east-1"
  }
}`,
    docsUrl: "https://docs.aws.amazon.com/s3/",
  },
  {
    id: "gcs",
    name: "Google Cloud Storage",
    description: "Export transcripts to GCS buckets.",
    category: "storage",
    icon: "☁️",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "storage": {
    "type": "gcs",
    "bucket": "your-gcs-bucket",
    "prefix": "aavaaz-transcripts/"
  }
}`,
  },
  {
    id: "discord",
    name: "Discord",
    description: "Send transcript notifications to Discord channels.",
    category: "communication",
    icon: "🎮",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://discord.com/api/webhooks/YOUR/WEBHOOK",
  "payload": {
    "content": "📝 **New Transcript**\\nFile: {{transcript.filename}}\\nDuration: {{transcript.duration}}s\\n\\n\`\`\`\\n{{transcript.text | truncate:1800}}\\n\`\`\`"
  }
}`,
    docsUrl: "https://discord.com/developers/docs/resources/webhook",
  },
  {
    id: "datadog",
    name: "Datadog",
    description: "Send transcription metrics and events to Datadog for monitoring.",
    category: "analytics",
    icon: "📊",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://http-intake.logs.datadoghq.com/api/v2/logs",
  "headers": {
    "DD-API-KEY": "YOUR_DATADOG_API_KEY"
  },
  "payload": {
    "ddsource": "aavaaz",
    "service": "transcription",
    "message": "Transcription completed: {{transcript.filename}}",
    "ddtags": "env:production,service:aavaaz"
  }
}`,
    docsUrl: "https://docs.datadoghq.com/logs/log_collection/",
  },
  {
    id: "custom",
    name: "Custom Webhook",
    description: "Send results to any HTTP endpoint. Full control over payload format.",
    category: "automation",
    icon: "🔗",
    webhookTemplate: `{
  "trigger": "transcription.complete",
  "webhook_url": "https://your-server.com/api/webhook",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer YOUR_SECRET",
    "Content-Type": "application/json"
  },
  "payload": {
    "event": "transcription.complete",
    "data": {
      "id": "{{transcript.id}}",
      "text": "{{transcript.text}}",
      "segments": "{{transcript.segments}}",
      "duration": "{{transcript.duration}}",
      "language": "{{transcript.language}}",
      "model": "{{transcript.model}}",
      "created_at": "{{transcript.created_at}}"
    }
  },
  "retry": {
    "max_attempts": 3,
    "backoff": "exponential"
  }
}`,
  },
];

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "automation", label: "Automation" },
  { id: "communication", label: "Communication" },
  { id: "storage", label: "Storage" },
  { id: "analytics", label: "Analytics" },
];

export default function IntegrationsPage() {
  const [category, setCategory] = useState("all");
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
  const [copied, setCopied] = useState(false);

  const filtered = category === "all"
    ? INTEGRATIONS
    : INTEGRATIONS.filter((i) => i.category === category);

  function copyTemplate() {
    if (selectedIntegration?.webhookTemplate) {
      navigator.clipboard.writeText(selectedIntegration.webhookTemplate);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Integrations</h1>
        <p className="text-muted-foreground mt-1">
          Reference recipes for delivering transcripts to your tools via webhooks
        </p>
      </div>

      {/* Category filter */}
      <div className="flex gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setCategory(cat.id)}
            className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
              category === cat.id
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Integration cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((integration) => (
          <button
            key={integration.id}
            onClick={() => setSelectedIntegration(integration)}
            className={`rounded-lg border p-5 text-left transition-colors hover:border-primary/50 ${
              selectedIntegration?.id === integration.id
                ? "border-primary bg-primary/5"
                : "bg-card"
            }`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="text-2xl">{integration.icon}</span>
              <h3 className="font-semibold">{integration.name}</h3>
            </div>
            <p className="text-sm text-muted-foreground">{integration.description}</p>
            {integration.docsUrl && (
              <span className="inline-flex items-center gap-1 text-xs text-primary mt-2">
                <ExternalLink className="h-3 w-3" />
                Docs
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Webhook template */}
      {selectedIntegration && selectedIntegration.webhookTemplate && (
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <h3 className="font-semibold">
              {selectedIntegration.icon} {selectedIntegration.name} — Webhook Template
            </h3>
            <button
              onClick={copyTemplate}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="p-4 text-sm font-mono overflow-x-auto max-h-80 overflow-y-auto leading-relaxed">
            <code>{selectedIntegration.webhookTemplate}</code>
          </pre>
          <div className="px-4 py-3 border-t bg-muted/30 text-xs text-muted-foreground">
            Pass a <code>callback_url</code> on your transcription request and Aavaaz POSTs the
            completed transcript as JSON to it. This snippet is a reference for the receiving
            tool &mdash; Aavaaz sends its standard transcript JSON and does not substitute{" "}
            {"{{variables}}"}.
          </div>
        </div>
      )}
    </div>
  );
}
