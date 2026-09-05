import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage.jsx";
import EmptyState from "./EmptyState.jsx";
import QuestionInput from "./QuestionInput.jsx";
import ArtifactViewer from "./ArtifactViewer.jsx";

export default function Chat({
  messages,
  draft,
  onDraftChange,
  onSubmit,
  onExampleSelect,
  isLoading,
  onGenerateEssay,
  essayLoading,
  artifact,
  onCloseArtifact,
}) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function topicFor(index) {
    for (let i = index - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user") return messages[i].content;
    }
    return null;
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState onSelect={onExampleSelect} disabled={isLoading} />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
              {messages.map((message, index) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  topic={topicFor(index)}
                  onGenerateEssay={
                    message.role === "assistant" && !message.loading && !message.error
                      ? onGenerateEssay
                      : undefined
                  }
                  essayLoading={essayLoading}
                />
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>
        <QuestionInput
          value={draft}
          onChange={onDraftChange}
          onSubmit={onSubmit}
          disabled={isLoading}
        />
      </div>

      {artifact ? (
        <ArtifactViewer artifact={artifact} onClose={onCloseArtifact} />
      ) : null}
    </div>
  );
}