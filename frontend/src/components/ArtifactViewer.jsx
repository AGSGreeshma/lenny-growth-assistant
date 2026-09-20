import { useEffect, useMemo } from "react";
import AnswerContent from "./AnswerContent.jsx";
import { PROVIDER_LABELS } from "../lib/providers.js";

export default function ArtifactViewer({ artifact, onClose }) {
  const isHtml = artifact?.type === "html";

  const iframeSrcDoc = useMemo(() => {
    if (!isHtml || !artifact?.content) return "";
    return artifact.content;
  }, [isHtml, artifact]);

  useEffect(() => {
    if (!artifact) return;
    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [artifact, onClose]);

  if (!artifact) return null;

  return (
    <aside
      aria-label="Generated artifact"
      className="flex h-full w-full flex-col border-l border-line bg-cream sm:w-[420px] lg:w-[480px]">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-moss">
            Artifact
          </p>
          <p className="truncate text-sm font-medium text-ink">
            {artifact.title || "Ship 30 for 30 Essay"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {artifact.provider ? (
            <span
              className="rounded-full border border-line bg-paper px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted"
              title={PROVIDER_LABELS[artifact.provider]?.title ?? artifact.provider}
            >
              {PROVIDER_LABELS[artifact.provider]?.badge ?? artifact.provider}
            </span>
          ) : null}
          <span
            className="rounded-full border border-line bg-paper px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted"
            title={
              isHtml
                ? "Rendered in a sandboxed iframe with no access to this page's cookies or storage"
                : "Plain-text Markdown rendering -- no HTML execution"
            }
          >
            {isHtml ? "Sandboxed HTML" : "Markdown"}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-line bg-paper px-2 py-1 text-xs font-medium text-ink hover:border-moss/40 hover:text-moss focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss"
          >
            Close
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {isHtml ? (
          <iframe
            title={artifact.title || "artifact"}
            srcDoc={iframeSrcDoc}
            sandbox="allow-scripts"
            className="h-full w-full rounded-xl border border-line bg-white"
          />
        ) : (
          <article className="font-display text-[1.02rem] text-ink">
            <AnswerContent text={artifact.content || ""} />
          </article>
        )}
      </div>
    </aside>
  );
}