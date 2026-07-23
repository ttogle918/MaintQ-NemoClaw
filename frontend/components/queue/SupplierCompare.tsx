import { sx } from "@/lib/sx";
import type { SupplierQuote } from "@/lib/types";

/**
 * 공급사 비교 — 선택은 사람이 한다 (에이전트 단독 결정 금지).
 * 긴급도 기반 자동 추천 로직 자체는 백로그 P2 이고, 여기서는 강조 테두리 자리만 잡는다.
 */
export function SupplierCompare({ quotes }: { quotes: SupplierQuote[] }) {
  return (
    <>
      <div
        style={sx(
          "font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;color:var(--dim2);margin-bottom:9px"
        )}
      >
        공급사 비교 · 선택은 사람이
      </div>
      <div
        style={sx("display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:16px")}
      >
        {quotes.map((q) => (
          <SupplierCard key={q.supplierId} quote={q} />
        ))}
      </div>
    </>
  );
}

function SupplierCard({ quote }: { quote: SupplierQuote }) {
  const frame = quote.recommended
    ? "border:2px solid var(--blue)"
    : "border:1px solid var(--line2)";

  return (
    <div
      style={sx(
        `${frame};border-radius:8px;background:var(--surface);padding:13px 14px;position:relative`
      )}
    >
      {quote.recommended && (
        <span
          style={sx(
            "position:absolute;top:-9px;left:12px;font:700 9px 'JetBrains Mono',monospace;" +
              "color:#fff;background:var(--blue);border-radius:3px;padding:2px 7px"
          )}
        >
          추천
        </span>
      )}
      <div style={sx("font:700 14px 'Pretendard';color:var(--ink);margin-bottom:8px")}>
        {quote.name}
      </div>
      <Row label="리드타임" value={`${quote.leadDays}일`} strong={quote.recommended} />
      <Row label="단가" value={`₩${quote.unitPrice.toLocaleString()}`} mono />
      <div
        style={sx(
          "margin-top:9px;padding-top:9px;border-top:1px solid var(--line);font:11px/1.4 'Pretendard';" +
            `color:${quote.recommended ? "var(--blue-tx2)" : "var(--dim2)"}`
        )}
      >
        {quote.note}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  strong = false,
  mono = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
  mono?: boolean;
}) {
  return (
    <div
      style={sx(
        "display:flex;justify-content:space-between;font:12px 'Pretendard';color:var(--ink2);margin-bottom:5px"
      )}
    >
      <span style={sx("color:var(--dim2)")}>{label}</span>
      <span
        style={sx(
          `color:var(--ink)${strong ? ";font-weight:600" : ""}${mono ? ";font-family:'JetBrains Mono',monospace" : ""}`
        )}
      >
        {value}
      </span>
    </div>
  );
}
