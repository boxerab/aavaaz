"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { apiKeys, ApiKey } from "@/lib/api";
import { Key, Plus, Trash2, Copy, Check } from "lucide-react";

export default function ApiKeysPage() {
  const { getToken } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadKeys();
  }, []);

  async function loadKeys() {
    const token = await getToken();
    if (token) {
      try {
        const data = await apiKeys.list(token);
        setKeys(data);
      } catch {
        // API not connected yet
      }
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setCreating(true);

    try {
      const token = await getToken();
      if (token) {
        const result = await apiKeys.create(token, newKeyName);
        setNewKeySecret(result.secret);
        setKeys((prev) => [...prev, result.key]);
        setNewKeyName("");
      }
    } catch {
      // handle error
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(keyId: string) {
    if (!confirm("Are you sure? This cannot be undone.")) return;
    const token = await getToken();
    if (token) {
      await apiKeys.revoke(token, keyId);
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">API Keys</h1>
        <p className="text-muted-foreground mt-1">
          Manage your API keys for authentication
        </p>
      </div>

      {/* New key created banner */}
      {newKeySecret && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
          <p className="text-sm font-medium mb-2">
            Your new API key (copy it now — it won&apos;t be shown again):
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-muted rounded px-3 py-2 text-sm font-mono">
              {newKeySecret}
            </code>
            <button
              onClick={() => copyToClipboard(newKeySecret)}
              className="p-2 rounded-md hover:bg-accent transition-colors"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
          </div>
          <button
            onClick={() => setNewKeySecret(null)}
            className="text-xs text-muted-foreground mt-2 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Create new key */}
      <form onSubmit={handleCreate} className="flex gap-3">
        <input
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder="Key name (e.g., Production, Dev)"
          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={creating || !newKeyName.trim()}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Create Key
        </button>
      </form>

      {/* Keys list */}
      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="text-left p-4 font-medium">Name</th>
              <th className="text-left p-4 font-medium">Key Prefix</th>
              <th className="text-left p-4 font-medium">Created</th>
              <th className="text-left p-4 font-medium">Last Used</th>
              <th className="text-right p-4 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-muted-foreground">
                  <Key className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  No API keys yet. Create one to get started.
                </td>
              </tr>
            ) : (
              keys.map((key) => (
                <tr key={key.id} className="border-b last:border-0">
                  <td className="p-4 font-medium">{key.name}</td>
                  <td className="p-4 font-mono text-muted-foreground">
                    {key.prefix}...
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {new Date(key.created_at).toLocaleDateString()}
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {key.last_used
                      ? new Date(key.last_used).toLocaleDateString()
                      : "Never"}
                  </td>
                  <td className="p-4 text-right">
                    <button
                      onClick={() => handleRevoke(key.id)}
                      className="inline-flex items-center gap-1 text-destructive hover:text-destructive/80 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                      Revoke
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
