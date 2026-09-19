const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function friendlyHttpError(status) {
  if (status === 404) {
    return "The assistant endpoint was not found. Please confirm the backend is running.";
  }
  if (status === 422) {
    return "That question could not be processed. Please try rephrasing it.";
  }
  if (status >= 500) {
    return "The assistant ran into a problem while generating an answer. Please try again.";
  }
  return "The assistant could not process that request. Please try again.";
}

async function parseJsonOrThrow(response) {
  if (!response.ok) {
    throw new Error(friendlyHttpError(response.status));
  }
  try {
    return await response.json();
  } catch {
    throw new Error(
      "The assistant returned an unexpected response. Please try again."
    );
  }
}

export async function createSession() {
  let response;
  try {
    response = await fetch(`${API_URL}/api/sessions`, { method: "POST" });
  } catch {
    throw new Error(
      "Unable to connect to the assistant. Please make sure the backend is running."
    );
  }
  return parseJsonOrThrow(response);
}

export async function getSessionHistory(sessionId) {
  let response;
  try {
    response = await fetch(`${API_URL}/api/sessions/${sessionId}`);
  } catch {
    throw new Error(
      "Unable to connect to the assistant. Please make sure the backend is running."
    );
  }
  if (response.status === 404) {
    return null;
  }
  return parseJsonOrThrow(response);
}

// `provider` is an optional per-request override ("ollama" | "openai") for
// the frontend's provider toggle -- see app/models/schemas.py's
// ChatRequest.provider / EssayRequest.provider / ArtifactRequest.provider.
// Undefined/null means "use the backend's normal Ollama-first fallback".
export async function sendChatMessage(sessionId, message, provider) {
  let response;
  try {
    response = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message, provider: provider || null }),
    });
  } catch {
    throw new Error(
      "Unable to connect to the assistant. Please make sure the backend is running."
    );
  }

  const data = await parseJsonOrThrow(response);
  const answer = typeof data?.answer === "string" ? data.answer.trim() : "";
  if (!answer) {
    throw new Error(
      "The assistant did not return an answer. Please try asking in a different way."
    );
  }
  return {
    sessionId: data.session_id,
    answer,
    grounded: Boolean(data.grounded),
    sources: Array.isArray(data.sources) ? data.sources : [],
    provider: data.provider,
    intent: data.intent,
    usedAgentSdk: Boolean(data.used_agent_sdk),
    artifact: data.artifact || null,
  };
}

export async function generateEssay(sessionId, topic, provider) {
  let response;
  try {
    response = await fetch(`${API_URL}/api/essay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, topic, provider: provider || null }),
    });
  } catch {
    throw new Error(
      "Unable to connect to the assistant. Please make sure the backend is running."
    );
  }

  const data = await parseJsonOrThrow(response);
  const essay = typeof data?.essay === "string" ? data.essay.trim() : "";
  if (!essay) {
    throw new Error("The assistant did not return an essay. Please try again.");
  }
  return {
    sessionId: data.session_id,
    essay,
    sources: Array.isArray(data.sources) ? data.sources : [],
    provider: data.provider,
  };
}
