import AnswerContent from "./AnswerContent.jsx";
import SourceCard from "./SourceCard.jsx";

function LoadingBubble() {
  return (
    <div
      className="max-w-2xl rounded-2xl border border-line bg-cream px-5 py-4 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss/50" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-moss" />
        </span>
        <div>
          <p className="text-sm font-medium text-ink">Searching Lenny&apos;s Podcast...</p>
          <p className="mt-0.5 text-xs text-muted">
            Retrieving relevant episodes and generating an answer.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ChatMessage({ message, topic, onGenerateEssay, essayLoading }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end animate-fade-up">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-moss px-4 py-3 text-sm leading-relaxed text-cream sm:max-w-xl">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.loading) {
    return (
      <div className="flex justify-start animate-fade-up">
        <LoadingBubble />
      </div>
    );
  }

  if (message.error) {
    return (
      <div className="flex justify-start animate-fade-up">
        <div
          className="max-w-2xl rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm leading-relaxed text-rose-900"
          role="alert"
        >
          {message.content}
        </div>
      </div>
    );
  }

  const sources = Array.isArray(message.sources) ? message.sources : [];
  const notGrounded = message.grounded === false;

  return (
    <div className="flex justify-start animate-fade-up">
      <article
        className={
          "w-full max-w-2xl rounded-2xl border px-5 py-5 shadow-sm sm:px-6 " +
          (notGrounded ? "border-amber-200 bg-amber-50" : "border-line bg-cream")
        }
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <p
              className={
                "text-[11px] font-medium uppercase tracking-[0.16em] " +
                (notGrounded ? "text-amber-700" : "text-moss")
              }
            >
              {notGrounded ? "Not grounded" : "Answer"}
            </p>
            {message.provider ? (
              <span
                className="rounded-full border border-line bg-paper px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted"
                title={
                  message.provider === "ollama"
                    ? "Generated locally via Ollama"
                    : "Generated via OpenAI (Ollama unavailable or slow)"
                }
              >
                {message.provider === "ollama" ? "Local (Ollama)" : "Cloud (OpenAI)"}
              </span>
            ) : null}
          </div>
          {onGenerateEssay && !notGrounded && !message.hasArtifact ? (
            <button
              type="button"
              onClick={() => onGenerateEssay(topic || message.content)}
              disabled={essayLoading}
              className="shrink-0 rounded-lg border border-line bg-paper px-2.5 py-1 text-[11px] font-medium text-ink transition hover:border-moss/40 hover:text-moss focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss disabled:cursor-not-allowed disabled:opacity-50"
            >
              {essayLoading ? "Writing essay..." : "Turn into essay"}
            </button>
          ) : null}
        </div>
        <div className="font-display text-[1.05rem] text-ink">
          <AnswerContent text={message.content} />
        </div>
        {sources.length > 0 ? (
          <section className="mt-6 border-t border-line pt-4">
            <h2 className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
              Sources
            </h2>
            <div className="mt-3 grid gap-2.5">
              {sources.map((source, index) => (
                <SourceCard
                  key={`${source.episode || "source"}-${index}`}
                  source={source}
                  index={index}
                />
              ))}
            </div>
          </section>
        ) : null}
      </article>
    </div>
  );
}