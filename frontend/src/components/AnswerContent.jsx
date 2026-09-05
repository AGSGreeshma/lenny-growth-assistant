function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${keyPrefix}-${index}`} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={`${keyPrefix}-${index}`}>{part}</span>;
  });
}

function isListItem(line) {
  return /^\s*([-*]|\d+\.)\s+/.test(line);
}

export default function AnswerContent({ text }) {
  const blocks = text
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="space-y-4">
      {blocks.map((block, blockIndex) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const listLike = lines.length > 1 && lines.every(isListItem);

        if (listLike) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const ListTag = ordered ? "ol" : "ul";

          return (
            <ListTag
              key={blockIndex}
              className={
                ordered
                  ? "list-decimal space-y-2 pl-5 marker:text-moss"
                  : "list-disc space-y-2 pl-5 marker:text-moss"
              }
            >
              {lines.map((line, lineIndex) => (
                <li key={lineIndex} className="pl-1 leading-relaxed text-ink/90">
                  {renderInline(line.replace(/^\s*([-*]|\d+\.)\s+/, ""), `${blockIndex}-${lineIndex}`)}
                </li>
              ))}
            </ListTag>
          );
        }

        return (
          <p key={blockIndex} className="leading-[1.75] text-ink/90">
            {lines.map((line, lineIndex) => (
              <span key={lineIndex}>
                {renderInline(line.replace(/^\s*([-*]|\d+\.)\s+/, ""), `${blockIndex}-${lineIndex}`)}
                {lineIndex < lines.length - 1 ? <br /> : null}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
