interface HighlightTextProps {
  text: string;
  query: string;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^{}()|[\]\\$]/g, '\\$&');
}

export function HighlightText({ text, query }: HighlightTextProps) {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((term) => term.length > 2)
    .map(escapeRegExp);
  if (terms.length === 0) return <>{text}</>;

  const pattern = new RegExp('(' + terms.join('|') + ')', 'gi');
  const exactMatch = new RegExp('^(?:' + terms.join('|') + ')$', 'i');
  return (
    <>
      {text.split(pattern).map((part, index) =>
        exactMatch.test(part) ? (
          <mark key={index} className="rounded-sm bg-info/15 px-0.5 text-info">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
