// "HH:MM:SS" or "MM:SS" -> total seconds, or null if not a real timestamp
// (the backend defaults to the literal string "N/A" when none was
// recorded for a chunk -- see app/models/schemas.py's Source model).
function timestampToSeconds(timestamp) {
  if (typeof timestamp !== "string") return null;
  const parts = timestamp.split(":").map(Number);
  if (parts.length < 2 || parts.some((p) => Number.isNaN(p))) return null;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

function withTimestamp(url, seconds) {
  if (!url || seconds === null) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}t=${seconds}s`;
}

export default function SourceCard({ source, index }) {
  const episode = source?.episode || `Source ${index + 1}`;
  const url = typeof source?.url === "string" ? source.url.trim() : "";
  const score =
    typeof source?.score === "number" && Number.isFinite(source.score)
      ? source.score
      : null;
  const timestampSeconds = timestampToSeconds(source?.timestamp);
  const linkUrl = withTimestamp(url, timestampSeconds);

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
      <div className="mt-2 flex items-center gap-2">
        {timestampSeconds !== null ? (
          <span className="shrink-0 rounded-full border border-line bg-cream px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted">
            {source.timestamp}
          </span>
        ) : null}
        {url ? (
          <p className="truncate text-xs text-muted group-hover:text-moss">
            {url.replace(/^https?:\/\//, "")}
          </p>
        ) : (
          <p className="text-xs text-muted">Episode link unavailable</p>
        )}
      </div>
    </>
  );

  const className =
    "group block rounded-xl border border-line bg-paper/80 p-3.5 transition duration-200 hover:border-moss/25 hover:bg-cream focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss";

  if (url) {
    return (
      <a
        href={linkUrl}
        target="_blank"
        rel="noreferrer noopener"
        className={className}
      >
        {content}
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }

  return <div className={className}>{content}</div>;
}
