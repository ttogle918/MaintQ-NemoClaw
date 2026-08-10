import { auditRows, summarize, TONE_STYLE, type Row } from "@/lib/ownership";
import { sx } from "@/lib/sx";

/**
 * S18 실사 매트릭스 — 9카테고리 × 항목.
 *
 * ★ **이 컴포넌트는 판단하지 않는다.** `row.badge`·`row.tone` 을 그대로 찍을 뿐이다.
 *   판단(어떤 상태를 어떤 배지·색으로 보일 것인가)은 전부 `lib/ownership.ts` 에 있다.
 *
 * ⛔ 여기에 조건 분기·색 상수를 두지 말 것. 그 순간 매퍼를 우회할 수 있게 되고,
 *   "미확인이 초록으로 보이는" 실패가 이 파일에서 다시 태어난다 (D87).
 *   `spikes/ui_honesty_contract.py` 의 L2 가 이 파일 소스에서
 *   상태 문자열 리터럴·색 토큰·상태 비교가 **0건**임을 정적으로 단언한다 —
 *   즉 **이 컴포넌트에는 스스로 "확인" 여부를 말할 수단이 없다.**
 *
 * ⛔ 퍼센트 진행바를 만들지 말 것. 요약은 `summarize` 가 준 "N/M" 문자열 뿐이다
 *   (근거는 `lib/ownership.ts` 헤더 주석).
 */
export function VerificationMatrix({ rows }: { rows: Row[] }) {
  const summary = summarize(rows);
  const violations = auditRows(rows);

  return (
    <section
      style={sx(
        "width:1020px;max-width:100%;border:1px solid var(--line);border-radius:9px;" +
          "background:var(--surface);overflow:hidden"
      )}
    >
      <header
        style={sx(
          "display:flex;align-items:baseline;gap:10px;padding:11px 14px;" +
            "border-bottom:1px solid var(--line);background:var(--head)"
        )}
      >
        <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>실사 체크리스트</span>
        {/* 요약은 분자/분모 그대로. 백분율로 바꾸지 말 것 (lib/ownership.ts 헤더 주석) */}
        <span style={sx("font:600 12px 'JetBrains Mono',monospace;color:var(--dim)")}>
          {summary.text}
        </span>
        <span style={sx("margin-left:auto;font:11px 'Pretendard';color:var(--dim2)")}>
          카테고리 {countCategories(rows)}종 · 항목 {rows.length}건
        </span>
      </header>

      {violations.length > 0 && (
        <div
          style={sx(
            "padding:10px 14px;border-bottom:1px solid var(--line);" +
              "font:12px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <strong>UI 정직성 위반 {violations.length}건</strong> — 이 화면의 표시가 계약을 어겼습니다.
          아래 표를 판단 근거로 쓰지 마십시오.
          <ul style={sx("margin:6px 0 0;padding-left:18px")}>
            {violations.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        {rows.map((row, i) => (
          <div key={`${row.category}:${row.item}:${i}`}>
            {isFirstOfCategory(rows, i) && (
              <div
                style={sx(
                  "padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line);" +
                    "font:700 11px 'Pretendard';letter-spacing:.03em;color:var(--ink2)"
                )}
              >
                {row.category}
              </div>
            )}
            <div
              style={sx(
                "display:flex;align-items:flex-start;gap:10px;padding:9px 14px;" +
                  "border-bottom:1px solid var(--line)"
              )}
            >
              <span
                style={sx(
                  "flex:none;min-width:104px;border:1px solid;border-radius:3px;padding:2px 7px;" +
                    `text-align:center;font:700 10px 'JetBrains Mono',monospace;${TONE_STYLE[row.tone]}`
                )}
                title={`원문 상태 값: ${row.state}`}
              >
                {row.badge}
              </span>
              <div style={sx("flex:1;min-width:0")}>
                <div style={sx("font:12px 'Pretendard';color:var(--ink)")}>{row.item}</div>
                {row.evidence && (
                  <div style={sx("margin-top:3px;font:11px/1.6 'Pretendard';color:var(--dim)")}>
                    근거 · {row.evidence}
                  </div>
                )}
                {/* 사유가 비어 있으면 지어내지 않는다 — 그 경우는 위 위반 목록에 잡힌다 */}
                {row.limit && (
                  <div style={sx("margin-top:3px;font:11px/1.6 'Pretendard';color:var(--orange-tx)")}>
                    사유 · {row.limit}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** 카테고리 첫 행인가 — 표시용 그룹 헤더 판단일 뿐, 상태에 대한 판단이 아니다. */
function isFirstOfCategory(rows: Row[], i: number): boolean {
  return i === 0 || rows[i - 1].category !== rows[i].category;
}

function countCategories(rows: Row[]): number {
  return new Set(rows.map((r) => r.category)).size;
}
