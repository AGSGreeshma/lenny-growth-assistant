export default function Header({ onNewChat, newChatDisabled }) {
  return (
    <header className="border-b border-line bg-paper/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-4 sm:px-6">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-moss text-cream shadow-sm"
          aria-hidden="true"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 3v12" />
            <path d="M12 15c-3.5-1.8-6.5-1.3-8.5 1.6 1.5-5.6 4.7-8.8 8.5-10.1 3.8 1.3 7 4.5 8.5 10.1C18.5 13.7 15.5 13.2 12 15Z" />
            <path d="M8 21h8" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg font-semibold tracking-tight text-ink sm:text-xl">
            Lenny Growth Assistant
          </p>
          <p className="mt-0.5 truncate text-sm text-muted">
            Ask anything about product, growth, startups, and leadership.
          </p>
        </div>
        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatDisabled}
          className="shrink-0 rounded-xl border border-line bg-cream px-3.5 py-2 text-sm font-medium text-ink transition hover:border-moss/40 hover:text-moss disabled:cursor-not-allowed disabled:opacity-50"
        >
          New chat
        </button>
      </div>
    </header>
  );
}