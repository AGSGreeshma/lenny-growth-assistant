export default function SourceCard({ source, index }) {
  const episode = source?.episode || `Source ${index + 1}`;
  const url = typeof source?.url === "string" ? source.url.trim() : "";
  const score =
    typeof source?.score === "number" && Number.isFinite(source.score)
      ? source.score
      : null;

  const similarity =
    score === null
      ? null
      : score <= 1
        ? Math.round(score * 100)
        : Math.round(score);

  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium leading-snug text-ink">{episode}</p>
        {similarity !== null ? (
          <span className="shrink-0 rounded-full bg-paper px-2 py-0.5 text-[11px] font-medium text-moss">
            {similarity}% match
          </span>
        ) : null}
      </div>
      {url ? (
        <p className="mt-2 truncate text-xs text-muted group-hover:text-moss">
          {url.replace(/^https?:\/\//, "")}
        </p>
      ) : (
        <p className="mt-2 text-xs text-muted">Episode link unavailable</p>
      )}
    </>
  );

  const className =
    "group block rounded-xl border border-line bg-paper/80 p-3.5 transition duration-200 hover:border-moss/25 hover:bg-cream focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss";

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer noopener"
        className={className}
      >
        {content}
      </a>
    );
  }

  return <div className={className}>{content}</div>;
}
