"use client";

import { useState, useEffect } from "react";

// Feature configuration types
interface PiiConfig {
  enabled: boolean;
  types: string[];
  customPatterns: { label: string; pattern: string; replacement: string }[];
}

interface IntelligenceConfig {
  sentiment: boolean;
  topics: boolean;
  topicsTopN: number;
  entities: boolean;
  summarize: boolean;
  summarySentences: number;
  highlights: boolean;
  maxHighlights: number;
  chapters: boolean;
  maxChapterDuration: number;
  minChapterDuration: number;
  fillerRemoval: boolean;
  fillerAggressive: boolean;
}

interface DiarizationConfig {
  enabled: boolean;
  maxSpeakers: number;
  similarityThreshold: number;
}

interface NoiseReductionConfig {
  enabled: boolean;
  mode: "near_field" | "far_field";
  propDecrease: number;
}

interface FormattingConfig {
  enabled: boolean;
  capitalize: boolean;
  numbers: boolean;
  smart: boolean;
  replacements: { find: string; replace: string }[];
}

interface ProfanityConfig {
  enabled: boolean;
  mode: "partial" | "full" | "remove";
  extraWords: string[];
}

interface TranslationConfig {
  enabled: boolean;
  targetLanguage: string;
}

interface WebhookConfig {
  enabled: boolean;
  url: string;
  maxRetries: number;
  timeout: number;
}

interface EnsembleConfig {
  enabled: boolean;
  strategy: "longest" | "confidence" | "voting";
  models: string[];
}

export interface FeaturesConfig {
  pii: PiiConfig;
  intelligence: IntelligenceConfig;
  diarization: DiarizationConfig;
  noiseReduction: NoiseReductionConfig;
  formatting: FormattingConfig;
  profanity: ProfanityConfig;
  translation: TranslationConfig;
  webhook: WebhookConfig;
  ensemble: EnsembleConfig;
}

const DEFAULT_CONFIG: FeaturesConfig = {
  pii: { enabled: false, types: ["ssn", "credit_card", "phone", "email", "ip_address"], customPatterns: [] },
  intelligence: {
    sentiment: false, topics: false, topicsTopN: 5, entities: false,
    summarize: false, summarySentences: 3, highlights: false, maxHighlights: 10,
    chapters: false, maxChapterDuration: 300, minChapterDuration: 30,
    fillerRemoval: false, fillerAggressive: false,
  },
  diarization: { enabled: false, maxSpeakers: 10, similarityThreshold: 0.55 },
  noiseReduction: { enabled: false, mode: "near_field", propDecrease: 0.8 },
  formatting: { enabled: true, capitalize: true, numbers: true, smart: false, replacements: [] },
  profanity: { enabled: false, mode: "partial", extraWords: [] },
  translation: { enabled: false, targetLanguage: "es" },
  webhook: { enabled: false, url: "", maxRetries: 3, timeout: 30 },
  ensemble: { enabled: false, strategy: "confidence", models: ["large-v3"] },
};

const STORAGE_KEY = "aavaaz-features-config";

function loadConfig(): FeaturesConfig {
  if (typeof window === "undefined") return DEFAULT_CONFIG;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return DEFAULT_CONFIG;
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
  } catch {
    return DEFAULT_CONFIG;
  }
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
          checked ? "bg-primary" : "bg-muted"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
      <span className="text-sm font-medium">{label}</span>
    </label>
  );
}

function Slider({ value, onChange, min, max, step, label, unit }: {
  value: number; onChange: (v: number) => void; min: number; max: number; step: number; label: string; unit?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">{value}{unit}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </div>
  );
}

function FeatureCard({ title, description, enabled, onToggle, children }: {
  title: string; description: string; enabled: boolean; onToggle: (v: boolean) => void; children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-lg border p-5 transition-colors ${enabled ? "border-primary/50 bg-primary/5" : "bg-card"}`}>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-lg">{title}</h3>
          <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
        </div>
        <Toggle checked={enabled} onChange={onToggle} label="" />
      </div>
      {enabled && children && (
        <div className="mt-4 pt-4 border-t border-border space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [config, setConfig] = useState<FeaturesConfig>(DEFAULT_CONFIG);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setConfig(loadConfig());
  }, []);

  function updateConfig(partial: Partial<FeaturesConfig>) {
    setConfig((prev) => ({ ...prev, ...partial }));
    setSaved(false);
  }

  function saveConfig() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function resetConfig() {
    setConfig(DEFAULT_CONFIG);
    localStorage.removeItem(STORAGE_KEY);
    setSaved(false);
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Feature Settings</h1>
          <p className="text-muted-foreground mt-1">
            Configure transcription pipeline features. Settings are sent with each live session.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={resetConfig}
            className="px-4 py-2 text-sm rounded-md border border-input hover:bg-muted transition-colors"
          >
            Reset Defaults
          </button>
          <button
            onClick={saveConfig}
            className={`px-4 py-2 text-sm rounded-md font-medium transition-colors ${
              saved
                ? "bg-green-600 text-white"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            }`}
          >
            {saved ? "✓ Saved" : "Save Settings"}
          </button>
        </div>
      </div>

      <div className="grid gap-4">
        {/* PII Redaction */}
        <FeatureCard
          title="PII Redaction"
          description="Automatically mask sensitive information in transcripts"
          enabled={config.pii.enabled}
          onToggle={(v) => updateConfig({ pii: { ...config.pii, enabled: v } })}
        >
          <p className="text-sm text-muted-foreground mb-2">Entity types to redact:</p>
          <div className="flex flex-wrap gap-2">
            {["ssn", "credit_card", "phone", "email", "ip_address"].map((type) => (
              <label key={type} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={config.pii.types.includes(type)}
                  onChange={(e) => {
                    const types = e.target.checked
                      ? [...config.pii.types, type]
                      : config.pii.types.filter((t) => t !== type);
                    updateConfig({ pii: { ...config.pii, types } });
                  }}
                  className="accent-primary"
                />
                <span className="text-sm font-mono">{type}</span>
              </label>
            ))}
          </div>
        </FeatureCard>

        {/* Audio Intelligence */}
        <FeatureCard
          title="Audio Intelligence"
          description="AI-powered analysis: sentiment, topics, summaries, highlights"
          enabled={config.intelligence.sentiment || config.intelligence.topics || config.intelligence.summarize || config.intelligence.highlights || config.intelligence.chapters || config.intelligence.fillerRemoval || config.intelligence.entities}
          onToggle={(v) => updateConfig({
            intelligence: {
              ...config.intelligence,
              sentiment: v, topics: v, entities: v, summarize: v,
              highlights: v, chapters: v, fillerRemoval: v,
            },
          })}
        >
          <div className="grid grid-cols-2 gap-3">
            <Toggle checked={config.intelligence.sentiment} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, sentiment: v } })} label="Sentiment Analysis" />
            <Toggle checked={config.intelligence.topics} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, topics: v } })} label="Topic Detection" />
            <Toggle checked={config.intelligence.entities} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, entities: v } })} label="Entity Extraction" />
            <Toggle checked={config.intelligence.summarize} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, summarize: v } })} label="Summarization" />
            <Toggle checked={config.intelligence.highlights} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, highlights: v } })} label="Key Highlights" />
            <Toggle checked={config.intelligence.chapters} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, chapters: v } })} label="Auto Chapters" />
            <Toggle checked={config.intelligence.fillerRemoval} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, fillerRemoval: v } })} label="Filler Removal" />
            <Toggle checked={config.intelligence.fillerAggressive} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, fillerAggressive: v } })} label="Aggressive Mode" />
          </div>
          <Slider value={config.intelligence.summarySentences} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, summarySentences: v } })} min={1} max={10} step={1} label="Summary Sentences" />
          <Slider value={config.intelligence.maxHighlights} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, maxHighlights: v } })} min={1} max={30} step={1} label="Max Highlights" />
          <Slider value={config.intelligence.maxChapterDuration} onChange={(v) => updateConfig({ intelligence: { ...config.intelligence, maxChapterDuration: v } })} min={60} max={900} step={30} label="Max Chapter Duration" unit="s" />
        </FeatureCard>

        {/* Speaker Diarization */}
        <FeatureCard
          title="Speaker Diarization"
          description="Identify and label different speakers in audio"
          enabled={config.diarization.enabled}
          onToggle={(v) => updateConfig({ diarization: { ...config.diarization, enabled: v } })}
        >
          <Slider value={config.diarization.maxSpeakers} onChange={(v) => updateConfig({ diarization: { ...config.diarization, maxSpeakers: v } })} min={2} max={20} step={1} label="Max Speakers" />
          <Slider value={config.diarization.similarityThreshold} onChange={(v) => updateConfig({ diarization: { ...config.diarization, similarityThreshold: v } })} min={0.3} max={0.9} step={0.05} label="Similarity Threshold" />
        </FeatureCard>

        {/* Noise Reduction */}
        <FeatureCard
          title="Noise Reduction"
          description="Remove background noise before transcription"
          enabled={config.noiseReduction.enabled}
          onToggle={(v) => updateConfig({ noiseReduction: { ...config.noiseReduction, enabled: v } })}
        >
          <div className="space-y-3">
            <div>
              <label className="text-sm text-muted-foreground">Mode</label>
              <select
                value={config.noiseReduction.mode}
                onChange={(e) => updateConfig({ noiseReduction: { ...config.noiseReduction, mode: e.target.value as "near_field" | "far_field" } })}
                className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="near_field">Near Field (close mic, stationary noise)</option>
                <option value="far_field">Far Field (speakerphone, non-stationary noise)</option>
              </select>
            </div>
            <Slider value={config.noiseReduction.propDecrease} onChange={(v) => updateConfig({ noiseReduction: { ...config.noiseReduction, propDecrease: v } })} min={0.1} max={1.0} step={0.05} label="Reduction Intensity" />
          </div>
        </FeatureCard>

        {/* Formatting */}
        <FeatureCard
          title="Formatting"
          description="Auto-capitalize, convert numbers, smart punctuation"
          enabled={config.formatting.enabled}
          onToggle={(v) => updateConfig({ formatting: { ...config.formatting, enabled: v } })}
        >
          <div className="grid grid-cols-2 gap-3">
            <Toggle checked={config.formatting.capitalize} onChange={(v) => updateConfig({ formatting: { ...config.formatting, capitalize: v } })} label="Capitalize Sentences" />
            <Toggle checked={config.formatting.numbers} onChange={(v) => updateConfig({ formatting: { ...config.formatting, numbers: v } })} label="Number Conversion" />
            <Toggle checked={config.formatting.smart} onChange={(v) => updateConfig({ formatting: { ...config.formatting, smart: v } })} label="Smart Format (dates, currency)" />
          </div>
        </FeatureCard>

        {/* Profanity Filter */}
        <FeatureCard
          title="Profanity Filter"
          description="Mask or remove profane language from transcripts"
          enabled={config.profanity.enabled}
          onToggle={(v) => updateConfig({ profanity: { ...config.profanity, enabled: v } })}
        >
          <div>
            <label className="text-sm text-muted-foreground">Masking Mode</label>
            <select
              value={config.profanity.mode}
              onChange={(e) => updateConfig({ profanity: { ...config.profanity, mode: e.target.value as "partial" | "full" | "remove" } })}
              className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="partial">Partial (f**k)</option>
              <option value="full">Full (****)</option>
              <option value="remove">Remove entirely</option>
            </select>
          </div>
        </FeatureCard>

        {/* Translation */}
        <FeatureCard
          title="Translation"
          description="Translate transcription output to another language"
          enabled={config.translation.enabled}
          onToggle={(v) => updateConfig({ translation: { ...config.translation, enabled: v } })}
        >
          <div>
            <label className="text-sm text-muted-foreground">Target Language</label>
            <select
              value={config.translation.targetLanguage}
              onChange={(e) => updateConfig({ translation: { ...config.translation, targetLanguage: e.target.value } })}
              className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="it">Italian</option>
              <option value="pt">Portuguese</option>
              <option value="ja">Japanese</option>
              <option value="zh">Chinese</option>
              <option value="ko">Korean</option>
              <option value="ar">Arabic</option>
              <option value="hi">Hindi</option>
            </select>
          </div>
        </FeatureCard>

        {/* Webhook */}
        <FeatureCard
          title="Webhook Notifications"
          description="Send transcription results to a callback URL"
          enabled={config.webhook.enabled}
          onToggle={(v) => updateConfig({ webhook: { ...config.webhook, enabled: v } })}
        >
          <div className="space-y-3">
            <div>
              <label className="text-sm text-muted-foreground">Callback URL</label>
              <input
                type="url"
                value={config.webhook.url}
                onChange={(e) => updateConfig({ webhook: { ...config.webhook, url: e.target.value } })}
                placeholder="https://your-server.com/webhook"
                className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <Slider value={config.webhook.maxRetries} onChange={(v) => updateConfig({ webhook: { ...config.webhook, maxRetries: v } })} min={0} max={10} step={1} label="Max Retries" />
            <Slider value={config.webhook.timeout} onChange={(v) => updateConfig({ webhook: { ...config.webhook, timeout: v } })} min={5} max={120} step={5} label="Timeout" unit="s" />
          </div>
        </FeatureCard>

        {/* Ensemble */}
        <FeatureCard
          title="Ensemble Transcription"
          description="Use multiple models and combine results for higher accuracy"
          enabled={config.ensemble.enabled}
          onToggle={(v) => updateConfig({ ensemble: { ...config.ensemble, enabled: v } })}
        >
          <div>
            <label className="text-sm text-muted-foreground">Merge Strategy</label>
            <select
              value={config.ensemble.strategy}
              onChange={(e) => updateConfig({ ensemble: { ...config.ensemble, strategy: e.target.value as "longest" | "confidence" | "voting" } })}
              className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="confidence">Confidence — pick highest-confidence model output</option>
              <option value="longest">Longest — pick model producing most text</option>
              <option value="voting">Voting — character-level majority vote across models</option>
            </select>
          </div>
          <div>
            <p className="text-sm text-muted-foreground mb-2">Models:</p>
            <div className="flex flex-wrap gap-2">
              {["large-v3", "medium", "small", "tiny"].map((m) => (
                <label key={m} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={config.ensemble.models.includes(m)}
                    onChange={(e) => {
                      const models = e.target.checked
                        ? [...config.ensemble.models, m]
                        : config.ensemble.models.filter((x) => x !== m);
                      updateConfig({ ensemble: { ...config.ensemble, models } });
                    }}
                    className="accent-primary"
                  />
                  <span className="text-sm font-mono">{m}</span>
                </label>
              ))}
            </div>
          </div>
        </FeatureCard>
      </div>

      {/* Config Preview */}
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-semibold mb-2">Configuration Preview (sent with live sessions)</h3>
        <pre className="text-xs font-mono bg-background rounded-md p-4 overflow-x-auto max-h-64 overflow-y-auto">
          {JSON.stringify(config, null, 2)}
        </pre>
      </div>
    </div>
  );
}
