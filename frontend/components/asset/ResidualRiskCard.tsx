import { sx } from "@/lib/sx";

/**
 * 잔존위험 · 완화 방안 카드 (`04 §9` · D78).
 *
 * ★ **항상 렌더한다.** 값이 비어 있어도 카드를 지우지 않고 "산출 없음"이라고 밝힌다 —
 *   카드가 사라지면 사용자는 "잔존위험이 없다"고 읽는다. 실제로는 "산출하지 못했다"다 (D62·D65).
 *
 * ★ `insured=false`(확인된 미부보)처럼 **확인됐는데도 위험이 남는** 사실이 여기 실린다.
 *   즉 이 카드는 매트릭스가 전부 확인 상태여도 비어 있지 않을 수 있다 (D78).
 */
export function ResidualRiskCard({
  residualRisk,
  mitigation,
  notConsidered,
  disclaimer,
}: {
  residualRisk: unknown;
  mitigation: unknown;
  notConsidered?: unknown;
  disclaimer?: unknown;
}) {
  const items: string[] = Array.isArray(notConsidered)
    ? notConsidered.filter((v): v is string => typeof v === "string")
    : [];

  return (
    <section
      style={sx(
        "width:1020px;max-width:100%;border:1px solid var(--line);border-radius:9px;" +
          "background:var(--surface);padding:13px 15px;display:flex;flex-direction:column;gap:11px"
      )}
    >
      <Field label="잔존위험 (residual_risk)" value={text(residualRisk)} />
      <Field label="완화 방안 (mitigation)" value={text(mitigation)} />

      {items.length > 0 && (
        <div>
          <div style={sx("font:700 11px 'Pretendard';color:var(--dim);margin-bottom:4px")}>
            보지 않은 것 (not_considered)
          </div>
          <ul style={sx("margin:0;padding-left:17px;font:11px/1.7 'Pretendard';color:var(--ink2)")}>
            {items.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      {typeof disclaimer === "string" && disclaimer.trim() !== "" && (
        <p
          style={sx(
            "margin:0;padding-top:9px;border-top:1px dashed var(--line2);" +
              "font:11px/1.7 'Pretendard';color:var(--dim)"
          )}
        >
          {disclaimer}
        </p>
      )}
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div style={sx("font:700 11px 'Pretendard';color:var(--dim);margin-bottom:4px")}>{label}</div>
      {value ? (
        <p style={sx("margin:0;font:12px/1.7 'Pretendard';color:var(--ink)")}>{value}</p>
      ) : (
        // ⛔ "없음" 이라고만 쓰면 "위험이 없다"로 읽힌다. 무엇이 없는지 명시한다.
        <p style={sx("margin:0;font:12px/1.7 'Pretendard';color:var(--orange-tx)")}>
          산출 없음 — 이 항목을 산출할 원천이 없었습니다. 위험이 없다는 뜻이 아닙니다.
        </p>
      )}
    </div>
  );
}

function text(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}
