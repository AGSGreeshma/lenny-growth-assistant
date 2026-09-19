import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const components = {
  p: ({ node, ...props }) => <p className="leading-[1.75] text-ink/90" {...props} />,
  strong: ({ node, ...props }) => <strong className="font-semibold text-ink" {...props} />,
  a: ({ node, ...props }) => (
    <a className="text-moss underline underline-offset-2 hover:text-moss/80" {...props} />
  ),
  ul: ({ node, ...props }) => (
    <ul className="list-disc space-y-2 pl-5 marker:text-moss" {...props} />
  ),
  ol: ({ node, ...props }) => (
    <ol className="list-decimal space-y-2 pl-5 marker:text-moss" {...props} />
  ),
  li: ({ node, ...props }) => <li className="pl-1 leading-relaxed text-ink/90" {...props} />,
  h1: ({ node, ...props }) => (
    <h1 className="mt-2 text-xl font-semibold text-ink" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 className="mt-2 text-lg font-semibold text-ink" {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 className="mt-2 text-base font-semibold text-ink" {...props} />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote className="border-l-2 border-moss/40 pl-3 italic text-ink/80" {...props} />
  ),
  code: ({ node, inline, ...props }) =>
    inline ? (
      <code className="rounded bg-ink/5 px-1 py-0.5 text-[0.9em]" {...props} />
    ) : (
      <code className="block overflow-x-auto rounded-lg bg-ink/5 p-3 text-[0.9em]" {...props} />
    ),
  hr: () => <hr className="border-line" />,
  table: ({ node, ...props }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...props} />
    </div>
  ),
  th: ({ node, ...props }) => (
    <th className="border-b border-line px-2 py-1.5 text-left font-semibold text-ink" {...props} />
  ),
  td: ({ node, ...props }) => <td className="border-b border-line/60 px-2 py-1.5" {...props} />,
};

export default function AnswerContent({ text }) {
  return (
    <div className="space-y-4">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
