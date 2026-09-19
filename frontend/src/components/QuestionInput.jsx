import { useEffect, useRef } from "react";

export default function QuestionInput({
  value,
  onChange,
  onSubmit,
  disabled,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  const canSubmit = Boolean(value.trim()) && !disabled;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="border-t border-line bg-paper/95 px-4 py-4 sm:px-6"
    >
      <div className="mx-auto flex max-w-3xl items-end gap-3 rounded-2xl border border-line bg-cream p-2 shadow-sm transition focus-within:border-moss/35 focus-within:shadow-md">
        <label htmlFor="question" className="sr-only">
          Ask a question
        </label>
        <textarea
          id="question"
          ref={textareaRef}
          rows={1}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about growth, product, startups, or leadership..."
          aria-describedby="question-hint"
          className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-relaxed text-ink placeholder:text-muted/80 focus:outline-none disabled:cursor-not-allowed disabled:opacity-70"
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="mb-0.5 rounded-xl bg-moss px-4 py-2.5 text-sm font-medium text-cream transition duration-200 hover:bg-moss-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-moss/40"
        >
          Ask
        </button>
      </div>
      <p id="question-hint" className="mx-auto mt-2 max-w-3xl px-1 text-xs text-muted">
        Enter to send · Shift + Enter for a new line
      </p>
    </form>
  );
}
