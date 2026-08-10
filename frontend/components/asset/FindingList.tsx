import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";

/**
 * 처분 사전판정 버킷 렌더 (S9 · `06 §2.5`).
 *
 * `POST /api/assets/{id}/disposal/precheck` 의 4버킷(`blockers`·`preconditions`·`holds`·
 * `insufficient`)은 전부 `Record<string, unknown>[]` 로 온다 — `lib/api.ts` 가 일부러
 * 좁히지 않았다(백엔드가 키를 늘려도 fetcher 가 안 바뀌게). **좁히는 책임은 여기 한 곳**이다.
 *
 * 지켜야 할 것
 *
 * - **모르는 값을 지어내지 않는다.** 문자열이 아닌 값은 빈 문자열/빈 배열이 되고,
 *   빈 값은 **렌더하지 않는다**. `"없음"`·`"정상"` 같은 문장으로 채우지 않는다 (D62).
 * - **초록은 이 파일에 없다.** 4버킷은 전부 "지금 걸려 있는 것"이라 성공색이 나올 자리가
 *   없다 — `--ok-*` 토큰을 쓰지 않는다 (D87). 판정 어휘의 색은 `DisposalPanel` 의 전역 맵이 정한다.
 * - **오렌지를 쓰지 않는다.** 오렌지는 안전·긴급 전용이다 (`frontend/README §설계 계약`).
 *   법정 차단은 `--error-tx`(적색) 계열로 구분한다.
 * - **조문 문자열을 재조립하지 않는다.** `citations[]` 는 백엔드(`engine.LawRef.citation()`)가
 *   조립한 표시 문자열이라 그대로 찍는다 — 매뉴얼 인용에서 `citationLabel()` 이 표시만
 *   담당하는 것과 같은 규칙이다 (D26·D32).
 */

/* -------------------------------------------------------------------------- */
/* 좁히기 — unknown → 화면이 읽을 수 있는 값                                    */

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const bool = (v: unknown): boolean => v === true;
const strArr = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

export interface Finding {
  ruleId: string;
  label: string;
  /** 룰이 낸 판정 — TRIGGERED | HOLD | INSUFFICIENT_FACTS | CLEAR */
  verdict: string;
  /** BLOCKING | PRECONDITION — 같은 룰이 버킷에 따라 다른 무게를 갖는다 */
  disposalType: string;
  message: string;
  /** 왜 이 판정이 나왔는지. 경계 구간·누락 사실이 여기 문장으로 들어온다 */
  reasoning: string;
  citations: string[];
  lawRefs: string[];
  resolveOptions: string[];
  requiresExpertReview: boolean;
  missingFacts: string[];
}

export function toFinding(raw: Record<string, unknown>): Finding {
  return {
    ruleId: str(raw.rule_id),
    label: str(raw.label),
    verdict: str(raw.verdict),
    disposalType: str(raw.disposal_type),
    message: str(raw.message),
    reasoning: str(raw.reasoning),
    citations: strArr(raw.citations),
    lawRefs: strArr(raw.law_refs),
    resolveOptions: strArr(raw.resolve_options),
    requiresExpertReview: bool(raw.requires_expert_review),
    missingFacts: strArr(raw.missing_facts),
  };
}

/** 체크리스트 항목(`checklist[]`) — PRECONDITION 의 `resolve_options` 를 근거와 함께 항목화한 것 */
export interface ChecklistItem {
  ruleId: string;
  label: string;
  action: string;
  citations: string[];
  requiresExpertReview: boolean;
}

export function toChecklistItem(raw: Record<string, unknown>): ChecklistItem {
  return {
    ruleId: str(raw.rule_id),
    label: str(raw.label),
    action: str(raw.action),
    citations: strArr(raw.citations),
    requiresExpertReview: bool(raw.requires_expert_review),
  };
}

/* -------------------------------------------------------------------------- */
/* 톤 — 버킷마다 사용자가 할 일이 다르다 (D79)                                  */

export type FindingTone = "block" | "hold" | "insufficient" | "precondition";

/**
 * 버킷 톤. **성공색이 없다** — 네 버킷 어디에도 `--ok-*` 를 두지 않는다 (D87).
 * `hold`·`insufficient` 의 점선은 "단정하지 않았다"는 뜻이고, 실선 적색은 확정 차단이다.
 */
const TONE: Record<FindingTone, { skin: string; head: string; mark: string }> = {
  block: {
    skin: "border:1px solid var(--error-tx)",
    head: "color:var(--error-tx)",
    mark: "■",
  },
  hold: {
    skin: "border:1px dashed var(--error-tx)",
    head: "color:var(--error-tx)",
    mark: "⏸",
  },
  insufficient: {
    skin: "border:1px dashed var(--dim2)",
    head: "color:var(--dim)",
    mark: "?",
  },
  precondition: {
    skin: "border:1px solid var(--cite-bd)",
    head: "color:var(--blue-tx)",
    mark: "□",
  },
};

/**
 * 조문 칩. 문자열은 백엔드가 조립한 것을 **그대로** 찍는다 (D26·D32 와 같은 태도).
 * 계약 근거(`contract_refs`)도 같은 배열에 섞여 오므로 "법령"이라고 단정하지 않는다.
 */
export function LawCitationChip({ text }: { text: string }) {
  return (
    <span
      style={sx(
        "display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;" +
          "border:1px solid var(--cite-bd);border-radius:4px;padding:2px 7px;" +
          "color:var(--blue-tx);background:var(--cite-bg)"
      )}
    >
      <span>▤</span> {text}
    </span>
  );
}

export function LawCitationRow({ citations }: { citations: string[] }) {
  if (!citations.length) return null;
  return (
    <div style={sx("margin-top:6px;display:flex;gap:6px;flex-wrap:wrap")}>
      {citations.map((c) => (
        <LawCitationChip key={c} text={c} />
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * 버킷 하나. **0건이어도 섹션을 지우지 않는다** — 네 버킷이 늘 보여야 사용자가
 * "이 축은 검사됐고 걸린 게 없다"와 "이 축은 아예 안 봤다"를 구분할 수 있다.
 * 다만 0건을 초록·체크로 그리지 않는다 (D87) — 중립 회색 한 줄이다.
 */
export function FindingList({
  title,
  tone,
  note,
  findings,
}: {
  title: string;
  tone: FindingTone;
  /** 이 버킷이 무엇을 뜻하는지 한 줄. 사용자가 할 행동이 버킷마다 다르다 (D79) */
  note: string;
  findings: Finding[];
}) {
  const t = TONE[tone];
  return (
    <section style={sx("display:flex;flex-direction:column;gap:8px")}>
      <div style={sx("display:flex;align-items:baseline;gap:8px")}>
        <span style={sx(`font:700 12.5px 'Pretendard';${t.head}`)}>
          {t.mark} {title}
        </span>
        <Mono size={11}>{findings.length}건</Mono>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>{note}</span>
      </div>

      {findings.length === 0 ? (
        <div
          style={sx(
            "border:1px solid var(--line);border-radius:7px;padding:9px 12px;" +
              "font:11.5px 'Pretendard';color:var(--dim2);background:var(--panel)"
          )}
        >
          0건 — 이 버킷에 들어온 룰이 없습니다. (다른 버킷 결과와 함께 읽으세요)
        </div>
      ) : (
        findings.map((f) => <FindingCard key={`${f.ruleId}-${f.verdict}`} f={f} tone={tone} />)
      )}
    </section>
  );
}

function FindingCard({ f, tone }: { f: Finding; tone: FindingTone }) {
  const t = TONE[tone];
  return (
    <article
      style={sx(
        `${t.skin};border-radius:7px;padding:11px 13px;background:var(--panel);` +
          "display:flex;flex-direction:column;gap:6px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
        <Mono size={11}>{f.ruleId}</Mono>
        {f.label && (
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>{f.label}</span>
        )}
        {f.disposalType && (
          <span
            style={sx(
              "font:700 9px 'JetBrains Mono',monospace;border:1px solid var(--line2);" +
                "border-radius:3px;padding:2px 6px;color:var(--dim)"
            )}
          >
            {f.disposalType}
          </span>
        )}
        {f.requiresExpertReview && (
          <span
            style={sx(
              "font:700 9px 'JetBrains Mono',monospace;border:1px dashed var(--error-tx);" +
                "border-radius:3px;padding:2px 6px;color:var(--error-tx)"
            )}
          >
            전문가 검토 필요
          </span>
        )}
      </div>

      {f.message && (
        <div style={sx("font:12.5px/1.6 'Pretendard';color:var(--ink2)")}>{f.message}</div>
      )}

      {f.reasoning && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          판정 근거 · {f.reasoning}
        </div>
      )}

      {f.missingFacts.length > 0 && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          확인되지 않은 사실 ·{" "}
          {f.missingFacts.map((m) => (
            <Mono key={m} size={11}>
              {m}{" "}
            </Mono>
          ))}
          <span style={sx("color:var(--error-tx)")}>
            — &ldquo;조건 미해당&rdquo;이 아니라 &ldquo;모른다&rdquo;입니다
          </span>
        </div>
      )}

      {f.resolveOptions.length > 0 && (
        <ul style={sx("margin:0;padding-left:16px;font:11.5px/1.7 'Pretendard';color:var(--ink2)")}>
          {f.resolveOptions.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
      )}

      <LawCitationRow citations={f.citations} />
    </article>
  );
}

/** 선행조건 체크리스트 — 각 항목은 반드시 근거를 달고 온다 (근거 없는 지시는 백엔드가 뺀다). */
export function ChecklistBlock({ items }: { items: ChecklistItem[] }) {
  if (!items.length) return null;
  return (
    <section style={sx("display:flex;flex-direction:column;gap:8px")}>
      <div style={sx("display:flex;align-items:baseline;gap:8px")}>
        <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>이행 체크리스트</span>
        <Mono size={11}>{items.length}건</Mono>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
          근거 조문이 붙은 항목만 나옵니다 — 체크박스는 없습니다(이행 여부를 이 화면이 기록하지 않습니다)
        </span>
      </div>
      {items.map((it, i) => (
        <div
          key={`${it.ruleId}-${i}`}
          style={sx(
            "border:1px solid var(--line);border-radius:7px;padding:9px 12px;background:var(--evi);" +
              "display:flex;flex-direction:column;gap:5px"
          )}
        >
          <div style={sx("font:12.5px/1.6 'Pretendard';color:var(--ink2)")}>{it.action}</div>
          <div style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            <Mono size={10.5}>{it.ruleId}</Mono> {it.label}
          </div>
          <LawCitationRow citations={it.citations} />
        </div>
      ))}
    </section>
  );
}
