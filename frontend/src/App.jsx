import { useEffect, useState } from "react";
import Header from "./components/Header.jsx";
import Chat from "./components/Chat.jsx";
import {
  createSession,
  getSessionHistory,
  sendChatMessage,
  generateEssay,
} from "./services/api.js";

const SESSION_STORAGE_KEY = "lenny_session_id";

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const PROVIDER_STORAGE_KEY = "lenny_provider_preference";

function historyToMessages(historyMessages) {
  return historyMessages.map((m) => ({
    id: createId(),
    role: m.role,
    content: m.content,
    sources: Array.isArray(m.sources) ? m.sources : [],
    artifactType: m.artifact_type || null,
  }));
}

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [artifact, setArtifact] = useState(null);
  const [essayLoading, setEssayLoading] = useState(false);
  const [initError, setInitError] = useState(null);
  const [provider, setProvider] = useState(
    () => localStorage.getItem(PROVIDER_STORAGE_KEY) || null
  );

  function handleProviderChange(nextProvider) {
    setProvider(nextProvider);
    if (nextProvider) {
      localStorage.setItem(PROVIDER_STORAGE_KEY, nextProvider);
    } else {
      localStorage.removeItem(PROVIDER_STORAGE_KEY);
    }
  }

  async function init() {
    setInitError(null);
    setIsInitializing(true);
    const storedId = localStorage.getItem(SESSION_STORAGE_KEY);

    try {
      if (storedId) {
        const history = await getSessionHistory(storedId);
        if (history) {
          setSessionId(history.session_id);
          setMessages(historyToMessages(history.messages));
          setIsInitializing(false);
          return;
        }
      }

      const session = await createSession();
      localStorage.setItem(SESSION_STORAGE_KEY, session.session_id);
      setSessionId(session.session_id);
    } catch (error) {
      // Previously this left sessionId null with no explanation, so every
      // future "Ask" click silently no-op'd. Surface it instead.
      setSessionId(null);
      setInitError(
        error instanceof Error
          ? error.message
          : "Couldn't connect to the assistant. Please make sure the backend is running."
      );
    } finally {
      setIsInitializing(false);
    }
  }

  useEffect(() => {
    init();
  }, []);

  async function startNewChat() {
    setIsInitializing(true);
    setArtifact(null);
    try {
      const session = await createSession();
      localStorage.setItem(SESSION_STORAGE_KEY, session.session_id);
      setSessionId(session.session_id);
      setMessages([]);
      setDraft("");
      setInitError(null);
    } catch (error) {
      setInitError(
        error instanceof Error
          ? error.message
          : "Couldn't start a new chat. Please try again."
      );
    } finally {
      setIsInitializing(false);
    }
  }

  async function handleGenerateEssay(topic) {
    if (!sessionId || essayLoading || !topic) return;
    setEssayLoading(true);
    try {
      const { essay, sources, provider: usedProvider } = await generateEssay(
        sessionId,
        topic,
        provider
      );
      setArtifact({
        type: "markdown",
        title: `Ship 30 for 30: ${topic.slice(0, 60)}`,
        content: essay,
        sources,
        provider: usedProvider,
      });
    } catch (error) {
      setArtifact({
        type: "markdown",
        title: "Essay generation failed",
        content:
          error instanceof Error
            ? error.message
            : "Something went wrong generating the essay. Please try again.",
      });
    } finally {
      setEssayLoading(false);
    }
  }

  async function submitQuestion(rawQuestion) {
    const question = rawQuestion.trim();
    if (!question || isLoading) return;

    if (!sessionId) {
      // Previously this just returned here, so the Ask button looked
      // clickable but silently did nothing. Surface it instead.
      setInitError(
        "No active session -- couldn't reach the assistant. Tap Retry above to reconnect."
      );
      return;
    }

    const userMessage = { id: createId(), role: "user", content: question };
    const loadingMessage = { id: createId(), role: "assistant", loading: true };

    setDraft("");
    setIsLoading(true);
    setMessages((current) => [...current, userMessage, loadingMessage]);

    try {
      const {
        answer,
        sources,
        provider: usedProvider,
        grounded,
        artifact: responseArtifact,
      } = await sendChatMessage(sessionId, question, provider);

      if (responseArtifact) {
        setArtifact({ ...responseArtifact, sources, provider: usedProvider });
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === loadingMessage.id
            ? {
                id: loadingMessage.id,
                role: "assistant",
                content: answer,
                sources,
                provider: usedProvider,
                grounded,
                hasArtifact: Boolean(responseArtifact),
              }
            : message
        )
      );
    } catch (error) {
      const friendly =
        error instanceof Error
          ? error.message
          : "Unable to connect to the assistant. Please make sure the backend is running.";

      setMessages((current) =>
        current.map((message) =>
          message.id === loadingMessage.id
            ? { id: loadingMessage.id, role: "assistant", content: friendly, error: true }
            : message
        )
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-paper">
      <Header
        onNewChat={startNewChat}
        newChatDisabled={isLoading || isInitializing}
        provider={provider}
        onProviderChange={handleProviderChange}
      />
      {initError ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-900 sm:px-6"
        >
          <span>{initError}</span>
          <button
            type="button"
            onClick={init}
            className="shrink-0 rounded-lg border border-rose-300 bg-white px-3 py-1 text-xs font-medium text-rose-900 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
          >
            Retry
          </button>
        </div>
      ) : null}
      <Chat
        messages={messages}
        draft={draft}
        onDraftChange={setDraft}
        onSubmit={() => submitQuestion(draft)}
        onExampleSelect={submitQuestion}
        isLoading={isLoading || isInitializing}
        onGenerateEssay={handleGenerateEssay}
        essayLoading={essayLoading}
        artifact={artifact}
        onCloseArtifact={() => setArtifact(null)}
      />
    </div>
  );
}