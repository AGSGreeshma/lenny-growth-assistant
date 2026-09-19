const EXAMPLES = [
  "How can I improve product growth?",
  "What are the best product-led growth strategies?",
  "How should startups find product-market fit?",
  "How do great product teams prioritize?",
];

export default function EmptyState({ onSelect, disabled }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-10 text-center">
      <div className="max-w-xl animate-fade-up">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-moss">
          Grounded in Lenny&apos;s Podcast
        </p>
        <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
          A quieter way to think about growth.
        </h2>
        <p className="mt-4 text-base leading-relaxed text-muted">
          Ask a product, growth, startup, or leadership question. The assistant
          retrieves relevant ideas from Lenny&apos;s Podcast transcripts and
          writes an answer from that knowledge — not from generic internet advice.
        </p>
      </div>

      <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-2">
        {EXAMPLES.map((question) => (
          <button
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
            className="group rounded-2xl border border-line bg-cream px-4 py-4 text-left text-sm leading-snug text-ink shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-moss/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className="mb-2 block text-[11px] font-medium uppercase tracking-[0.14em] text-moss/80">
              Try asking
            </span>
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
