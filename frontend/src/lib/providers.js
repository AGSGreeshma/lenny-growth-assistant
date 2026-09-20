// Shared between ChatMessage.jsx and ArtifactViewer.jsx so both provider
// badges stay in sync -- adding a provider means adding one entry here,
// not auditing every place a provider name is displayed.
export const PROVIDER_LABELS = {
  ollama: { badge: "Local (Ollama)", title: "Generated locally via Ollama" },
  gemini: {
    badge: "Cloud (Gemini)",
    title: "Generated via Gemini (Ollama unavailable or slow)",
  },
  openai: {
    badge: "Cloud (OpenAI)",
    title: "Generated via OpenAI (explicitly selected)",
  },
};
