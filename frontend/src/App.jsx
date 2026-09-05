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

function historyToMessages(historyMessages) {
  return historyMessages.map((m) => ({
    id: createId(),
    role: m.role,
    content: m.content,
    sources: Array.isArray(m.sources) ? m.sources : [],
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

  useEffect(() => {
    let cancelled = false;

    async function init() {
      const storedId = localStorage.getItem(SESSION_STORAGE_KEY);

      try {
        if (storedId) {
          const history = await getSessionHistory(storedId);
          if (history && !cancelled) {
            setSessionId(history.session_id);
            setMessages(historyToMessages(history.messages));
            setIsInitializing(false);
            return;
          }
        }

        const session = await createSession();
        if (!cancelled) {
          localStorage.setItem(SESSION_STORAGE_KEY, session.session_id);
          setSessionId(session.session_id);
        }
      } catch {
        // Leave sessionId null; submitQuestion will surface a connection error.
      } finally {
        if (!cancelled) setIsInitializing(false);
      }
    }

    init();
    return () => {
      cancelled = true;
    };
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
    } catch {
      // Leave the current session active if creating a new one fails.
    } finally {
      setIsInitializing(false);
    }
  }

  async function handleGenerateEssay(topic) {
    if (!sessionId || essayLoading || !topic) return;
    setEssayLoading(true);
    try {
      const { essay, sources } = await generateEssay(sessionId, topic);
      setArtifact({
        type: "markdown",
        title: `Ship 30 for 30: ${topic.slice(0, 60)}`,
        content: essay,
        sources,
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
    if (!question || isLoading || !sessionId) return;

    const userMessage = { id: createId(), role: "user", content: question };
    const loadingMessage = { id: createId(), role: "assistant", loading: true };

    setDraft("");
    setIsLoading(true);
    setMessages((current) => [...current, userMessage, loadingMessage]);

    try {
      const { answer, sources } = await sendChatMessage(sessionId, question);
      setMessages((current) =>
        current.map((message) =>
          message.id === loadingMessage.id
            ? { id: loadingMessage.id, role: "assistant", content: answer, sources }
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
      <Header onNewChat={startNewChat} newChatDisabled={isLoading || isInitializing} />
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