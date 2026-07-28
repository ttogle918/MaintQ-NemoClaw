import { citationLabel, type Citation } from "@/lib/citation";
import { sx } from "@/lib/sx";

/**
 * 인용 칩 — SSE `block` 이벤트 (type: citation) 의 전용 렌더 컴포넌트 (D22).
 * 채팅 텍스트에 섞지 않고 별도 컴포넌트로 두는 게 계약이다.
 *
 * `tone="safety"` 는 안전 경고 블록 안에서 쓰는 오렌지 계열 변형.
 */
export function CitationChip({
  citation,
  tone = "default",
}: {
  citation: Citation;
  tone?: "default" | "safety";
}) {
  const palette =
    tone === "safety"
      ? "color:var(--saf-cite-tx);border-color:var(--saf-cite-bd);background:var(--saf-cite-bg)"
      : "color:var(--blue-tx);border-color:var(--cite-bd);background:var(--cite-bg)";

  return (
    <span
      style={sx(
        "display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;" +
          `border:1px solid;border-radius:4px;padding:2px 7px;${palette}`
      )}
    >
      <span>▤</span> {citationLabel(citation)}
    </span>
  );
}

/** 말풍선 하단에 붙는 인용 묶음. */
export function CitationRow({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div style={sx("margin-top:8px;display:flex;gap:6px;flex-wrap:wrap")}>
      {citations.map((c) => (
        <CitationChip key={`${c.label ?? c.manual}-${c.page}`} citation={c} />
      ))}
    </div>
  );
}
