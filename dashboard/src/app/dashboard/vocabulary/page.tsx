"use client";

import { useState, useEffect } from "react";
import { Plus, Trash2, Save } from "lucide-react";

interface VocabEntry {
  word: string;
  boost: number; // 1-10 priority
}

const STORAGE_KEY = "aavaaz-custom-vocab";

export default function VocabularyPage() {
  const [entries, setEntries] = useState<VocabEntry[]>([]);
  const [newWord, setNewWord] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        setEntries(JSON.parse(stored));
      } catch {
        setEntries([]);
      }
    }
  }, []);

  function addWord() {
    const word = newWord.trim();
    if (!word || entries.some((e) => e.word.toLowerCase() === word.toLowerCase())) return;
    setEntries([...entries, { word, boost: 5 }]);
    setNewWord("");
    setSaved(false);
  }

  function removeWord(index: number) {
    setEntries(entries.filter((_, i) => i !== index));
    setSaved(false);
  }

  function updateBoost(index: number, boost: number) {
    const updated = [...entries];
    updated[index].boost = boost;
    setEntries(updated);
    setSaved(false);
  }

  function saveVocab() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function importList() {
    const input = prompt("Paste comma-separated words:");
    if (!input) return;
    const words = input.split(",").map((w) => w.trim()).filter(Boolean);
    const existing = new Set(entries.map((e) => e.word.toLowerCase()));
    const newEntries = words
      .filter((w) => !existing.has(w.toLowerCase()))
      .map((word) => ({ word, boost: 5 }));
    setEntries([...entries, ...newEntries]);
    setSaved(false);
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Custom Vocabulary</h1>
          <p className="text-muted-foreground mt-1">
            Boost recognition of domain-specific words, names, and jargon
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={importList}
            className="px-4 py-2 text-sm rounded-md border border-input hover:bg-muted transition-colors"
          >
            Import List
          </button>
          <button
            onClick={saveVocab}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md font-medium transition-colors ${
              saved
                ? "bg-green-600 text-white"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            }`}
          >
            <Save className="h-3.5 w-3.5" />
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>

      <div className="rounded-lg border bg-card p-5 space-y-4">
        <p className="text-sm text-muted-foreground">
          Add words that the model might not recognize correctly — proper nouns, technical terms,
          product names, acronyms. Higher boost = stronger preference for this spelling.
        </p>

        {/* Add word input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={newWord}
            onChange={(e) => setNewWord(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addWord()}
            placeholder="Add a word or phrase..."
            className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
          <button
            onClick={addWord}
            disabled={!newWord.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </button>
        </div>

        {/* Word list */}
        {entries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            No custom vocabulary words added yet.
          </div>
        ) : (
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {entries.map((entry, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-3 py-2 rounded-md border bg-background"
              >
                <span className="flex-1 font-medium text-sm">{entry.word}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Boost:</span>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={entry.boost}
                    onChange={(e) => updateBoost(i, Number(e.target.value))}
                    className="w-20 accent-primary"
                  />
                  <span className="text-xs font-mono w-4">{entry.boost}</span>
                </div>
                <button
                  onClick={() => removeWord(i)}
                  className="p-1 rounded text-muted-foreground hover:text-red-400 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="text-xs text-muted-foreground pt-2 border-t">
          {entries.length} word{entries.length !== 1 ? "s" : ""} in vocabulary.
          These will be sent with your transcription requests to improve accuracy.
        </div>
      </div>

      {/* How it works */}
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-semibold mb-2">How Custom Vocabulary Works</h3>
        <ul className="text-sm text-muted-foreground space-y-1.5 list-disc list-inside">
          <li>Words are sent as &quot;hotwords&quot; to the Whisper model during transcription</li>
          <li>Higher boost values make the model more likely to output that exact spelling</li>
          <li>Useful for: company names, product names, people&apos;s names, medical terms, legal jargon</li>
          <li>Works with both batch file upload and live streaming</li>
        </ul>
      </div>
    </div>
  );
}
