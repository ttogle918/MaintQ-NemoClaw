"use client";

import Link from "next/link";
import { useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  precheckDisposal,
  type ApiAsset,
  type ApiPrecheck,
} from "@/lib/api";
import {
  evidenceCompletenessView,
  isBlocking,
  isClearOnSaleAnomaly,
  verdictHeadline,
  verdictView,
  type VerdictLabel,
} from "@/lib/decisionView";
import { sx } from "@/lib/sx";
import {
  ChecklistBlock,
  FindingList,
  LawCitationRow,
  toChecklistItem,
  toFinding,
} from "./FindingList";

/**
 * 처분 사전판정 패널 (S9 → S10 진입점 · `06 §2.5` · D71).
 *
 * **200 과 409 를 같은 화면으로 렌더한다.** `BLOCKED`·`HOLD`·`INSUFFICIENT_FACTS` 는 409 로
 * 오지만 본문이 200 과 **같은 형태 + `detail`** 이다 — 409 를 "실패"로 뭉개면 사용자가 볼
 * 것(무엇이 막고 있고 무엇을 하면 풀리는지)이 사라진다. 백엔드가 두 응답의 모양을 맞춰 둔
 * 이유가 정확히 이것이다.
 *
 * **아무것도 저장하지 않는다** (D71). 이 패널의 유일한 쓰기 유발 경로는 "처분서 초안 요청"
 * 버튼인데, 그것도 여기서 API 를 부르지 않는다 — 채팅으로 **이동만** 하고 전송은 사람이 누른다.
 * 도구는 에이전트만 부른다(D15·D10). 화면이 도구를 부르거나 사람 전용 생성 API 를 새로
 * 만들면 쓰기 경로가 둘이 되어 `generate_disposal_document` 의 존재 이유가 흐려진다.
 *
 * **`disposal_date` 를 오늘로 자동 채우지 않는다** (D62). `build_facts` 가 NULL 컬럼의 키를
 * 빼는 것과 같은 이유다 — 모르는 날짜를 오늘로 대체하면 `INSUFFICIENT_FACTS` 여야 할 판정이
 * 조용히 확정 판정으로 바뀐다. 비어 있으면 그 결과(세액공제 조항이 사실 부족으로 남는다)를
 * 미리 알려 줄 뿐, 값을 넣어 주지 않는다.
 */

/* -------------------------------------------------------------------------- */
/* 입력 어휘 — 백엔드 `engine.DISPOSAL_MODES` 와 같은 3종                       */

const MODES = [
  { value: "SALE", label: "매각", hint: "SALE" },
  { value: "SCRAP", label: "폐기", hint: "SCRAP" },
  { value: "TRANSFER", label: "이전", hint: "TRANSFER" },
] as const;

/* -------------------------------------------------------------------------- */
/* 판정 어휘 → 표시                                                             */

/**
 * ⛔ **이 파일에는 판정 어휘 맵이 없다.** 어휘·톤·색·차단 여부는 전부
 * `lib/decisionView.ts` 의 total 맵 한 곳에서 온다 (D87).
 *
 * Stage 6 W1 이전에는 여기에 `VERDICT_VIEW`(5종) + `VERDICT_SKIN`(성공색 포함)이 따로 있었고,
 * `lib/decisionView.ts` 에 **같은 어휘의 두 번째 맵**이 있었다. 두 맵 다 폴백이 안전해서
 * 사용자에게 가짜 초록이 가지는 않았지만, D87 이 "맵 1곳"이라고 쓴 이유는 **두 곳이면 한 곳만
 * 틀려도 화면이 갈리기 때문**이다. 어휘를 다룰 일이 생기면 이 파일이 아니라 그 파일을 고친다.
 */

/* -------------------------------------------------------------------------- */
/* 응답 좁히기 — 지어내지 않는다                                                */

const recArr = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v)
    ? v.filter(
        (x): x is Record<string, unknown> => !!x && typeof x === "object" && !Array.isArray(x)
      )
    : [];

const strArr = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

/**
 * 409 본문이 **정말 200 과 같은 형태인지** 확인한다. 형태가 다르면 판정 화면으로 렌더하지
 * 않고 일반 오류로 떨어뜨린다 — 빈 버킷을 "걸린 것 없음"으로 그리면 그게 가장 위험하다.
 */
function asPrecheck(body: Record<string, unknown> | null): ApiPrecheck | null {
  if (!body || typeof body.verdict !== "string") return null;
  for (const k of ["blockers", "preconditions", "holds", "insufficient"]) {
    if (!Array.isArray(body[k])) return null;
  }
  return body as unknown as ApiPrecheck;
}

interface FieldErrors {
  mode?: string;
  date?: string;
  general?: string;
}

/** 422 는 입력 오류다 — 배너가 아니라 **해당 입력 옆**에 붙인다. */
function parse422(body: Record<string, unknown> | null): FieldErrors {
  const detail = body?.detail;
  if (typeof detail === "string") return { general: detail };
  if (!Array.isArray(detail)) return { general: "입력값을 확인해 주세요 (422)" };

  const out: FieldErrors = {};
  for (const d of detail) {
    if (!d || typeof d !== "object") continue;
    const rec = d as Record<string, unknown>;
    const loc = Array.isArray(rec.loc) ? rec.loc.map((x) => String(x)) : [];
    const msg = typeof rec.msg === "string" ? rec.msg : "입력값이 올바르지 않습니다";
    if (loc.includes("disposal_mode")) out.mode = msg;
    else if (loc.includes("disposal_date")) out.date = msg;
    else out.general = msg;
  }
  return Object.keys(out).length ? out : { general: "입력값을 확인해 주세요 (422)" };
}

interface Failure {
  tone: "warn" | "error";
  title: string;
  detail: string;
}

/**
 * 503 은 **500 과 다른 사건**이다 (D71) — 요청이 잘못된 게 아니라 서버에 룰 카탈로그가
 * 안 실린 것이고, 사용자가 할 행동(재시도 vs 관리자 문의)이 다르다.
 */
function catalogFailure(body: Record<string, unknown> | null): Failure {
  const detail = body?.detail;
  const inner = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
  const reason = typeof inner?.reason === "string" ? inner.reason : "";
  const message =
    typeof inner?.message === "string"
      ? inner.message
      : typeof detail === "string"
        ? detail
        : "룰 카탈로그가 판정에 쓸 수 없는 상태입니다";
  return {
    tone: "error",
    title: "서버 설정 문제 — 관리자에게 문의하세요 (503)",
    detail: `${reason ? `${reason} · ` : ""}${message} 판정이 나오지 않은 것이지 '문제 없음'이 아닙니다.`,
  };
}

/* -------------------------------------------------------------------------- */

export function DisposalPanel({ asset }: { asset: ApiAsset }) {
  const [mode, setMode] = useState<string | null>(null);
  /** ⛔ 오늘 날짜로 초기화하지 않는다 (D62). 빈 문자열 = 사용자가 아직 모른다 */
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApiPrecheck | null>(null);
  const [httpStatus, setHttpStatus] = useState<number | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<Failure | null>(null);

  async function run() {
    if (!mode || busy) return;
    setBusy(true);
    setFieldErrors({});
    setFailure(null);
    try {
      const r = await precheckDisposal("technician", asset.asset_id, {
        disposal_mode: mode,
        disposal_date: date || null,
      });
      setResult(r);
      setHttpStatus(200);
    } catch (e) {
      const body = errorBody(e);
      if (!(e instanceof ApiError)) {
        setResult(null);
        setHttpStatus(null);
        setFailure({
          tone: "error",
          title: "백엔드에 연결하지 못했습니다",
          detail:
            "판정 요청이 전달되지 않았습니다 — 결과가 없는 것이지 '처분 가능'이 아닙니다. (uv run uvicorn backend.main:app --port 8003)",
        });
        return;
      }
      if (e.status === 409) {
        // ★ 정상 렌더 경로다. 본문 형태가 200 과 같을 때만 판정 화면으로 넘긴다.
        const p = asPrecheck(body);
        if (p) {
          setResult(p);
          setHttpStatus(409);
          return;
        }
        setResult(null);
        setHttpStatus(null);
        setFailure({
          tone: "error",
          title: "409 응답을 판정 결과로 읽을 수 없습니다",
          detail: "본문이 사전판정 형태가 아닙니다 — 계약 위반 신호입니다. 원문: " + e.body.slice(0, 200),
        });
        return;
      }
      setResult(null);
      setHttpStatus(null);
      if (e.status === 422) {
        setFieldErrors(parse422(body));
      } else if (e.status === 503) {
        setFailure(catalogFailure(body));
      } else if (e.status === 404) {
        setFailure({
          tone: "error",
          title: "자산을 찾을 수 없습니다 (404)",
          detail: `${asset.asset_id} — 자산 등록부에 없는 식별자입니다.`,
        });
      } else {
        setFailure({
          tone: "error",
          title: `판정에 실패했습니다 (${e.status})`,
          detail:
            e.status >= 500
              ? "서버 오류입니다. 503(카탈로그 미적재)과 달리 원인이 특정되지 않았습니다 — 로그를 확인하세요."
              : e.body.slice(0, 200),
        });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:16px;padding:16px 18px")}>
      <ModeForm
        mode={mode}
        date={date}
        busy={busy}
        errors={fieldErrors}
        onMode={setMode}
        onDate={setDate}
        onRun={() => void run()}
      />

      {failure && (
        <StatusBanner tone={failure.tone}>
          <span>
            <b>{failure.title}</b>
            <br />
            {failure.detail}
          </span>
        </StatusBanner>
      )}

      {/* ★ 결과 화면은 **응답이 실어 온 값**만 읽는다. 폼 state 를 함께 읽으면 판정 후 날짜를
          바꿨을 때 화면이 "판정에 쓰이지 않은 날짜"를 판정 옆에 붙여 버린다 */}
      {result && <PrecheckResult asset={asset} result={result} httpStatus={httpStatus} />}

      {!result && !failure && (
        <div
          style={sx(
            "border:1px dashed var(--line2);border-radius:7px;padding:14px 16px;" +
              "font:12.5px/1.7 'Pretendard';color:var(--dim)"
          )}
        >
          아직 판정하지 않았습니다. 처분 방식을 고르고 <b>사전판정</b>을 누르세요.
          <br />
          사전판정은 <b>아무것도 저장하지 않습니다</b> — 처분 요청도, 이력도 남지 않습니다 (D71).
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 입력                                                                         */

function ModeForm({
  mode,
  date,
  busy,
  errors,
  onMode,
  onDate,
  onRun,
}: {
  mode: string | null;
  date: string;
  busy: boolean;
  errors: FieldErrors;
  onMode: (m: string) => void;
  onDate: (d: string) => void;
  onRun: () => void;
}) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:11px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>처분 방식</span>
        <div style={sx("display:flex;gap:7px")}>
          {MODES.map((m) => {
            const on = mode === m.value;
            return (
              <button
                key={m.value}
                onClick={() => onMode(m.value)}
                aria-pressed={on}
                style={sx(
                  "border-radius:14px;padding:5px 13px;cursor:pointer;font:12px 'Pretendard';" +
                    (on
                      ? "border:1px solid var(--blue-br);background:var(--cite-bg);color:var(--blue-tx)"
                      : "border:1px solid var(--line2);background:var(--raise);color:var(--dim)")
                )}
              >
                {m.label} <Mono size={10.5}>{m.hint}</Mono>
              </button>
            );
          })}
        </div>
        {/* 기본값을 만들지 않는다 — 고르지 않으면 판정하지 않는다 */}
        {mode === null && (
          <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
            선택 전에는 판정하지 않습니다 (기본값을 대신 고르지 않습니다)
          </span>
        )}
      </div>
      {errors.mode && <FieldError>{errors.mode}</FieldError>}

      <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>처분 예정일</span>
        <input
          type="date"
          value={date}
          onChange={(e) => onDate(e.target.value)}
          aria-label="처분 예정일"
          style={sx(
            "height:32px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
          )}
        />
        {date === "" && (
          <span style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
            미입력 시 세액공제 조항이 <b style={sx("color:var(--ink2)")}>사실 부족</b>으로 남습니다
            — 화면이 오늘 날짜로 채우지 않습니다 (D62)
          </span>
        )}
        {date !== "" && (
          <button
            onClick={() => onDate("")}
            style={sx(
              "border:1px solid var(--line2);background:transparent;border-radius:6px;" +
                "padding:4px 10px;font:11.5px 'Pretendard';color:var(--dim);cursor:pointer"
            )}
          >
            날짜 지우기
          </button>
        )}
      </div>
      {errors.date && <FieldError>{errors.date}</FieldError>}
      {errors.general && <FieldError>{errors.general}</FieldError>}

      <div style={sx("display:flex;align-items:center;gap:10px")}>
        <Button
          onClick={mode && !busy ? onRun : undefined}
          style={mode && !busy ? "" : "opacity:.5;cursor:not-allowed"}
        >
          {busy ? "판정 중…" : "사전판정"}
        </Button>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
          POST <Mono size={11}>/api/assets/{"{id}"}/disposal/precheck</Mono> — 무저장 (D71)
        </span>
      </div>
    </section>
  );
}

function FieldError({ children }: { children: React.ReactNode }) {
  return (
    <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--error-tx)")}>⚠ {children}</div>
  );
}

/* -------------------------------------------------------------------------- */
/* 결과                                                                         */

function PrecheckResult({
  asset,
  result,
  httpStatus,
}: {
  asset: ApiAsset;
  result: ApiPrecheck;
  httpStatus: number | null;
}) {
  const view = verdictView(result.verdict);
  const blockers = recArr(result.blockers).map(toFinding);
  const preconditions = recArr(result.preconditions).map(toFinding);
  const holds = recArr(result.holds).map(toFinding);
  const insufficient = recArr(result.insufficient).map(toFinding);
  const checklist = recArr(result.checklist).map(toChecklistItem);

  const resolveOptions = strArr(result.resolve_options);
  const missingFacts = strArr(result.missing_facts);
  const notConsidered = strArr(result.not_considered);
  const disclaimer = typeof result.disclaimer === "string" ? result.disclaimer : "";
  const note = typeof result.note === "string" ? result.note : "";
  const detail = typeof result.detail === "string" ? result.detail : "";

  // 순서 보존 dedup — 조문 칩은 4버킷 + 체크리스트에서 모은다
  const citations: string[] = [];
  for (const f of [...blockers, ...holds, ...insufficient, ...preconditions]) {
    for (const c of f.citations) if (!citations.includes(c)) citations.push(c);
  }

  // D78 부수 확정 — SALE 은 최소 한 개의 PRECONDITION(세금계산서)이 항상 발화하므로
  // `CLEAR` 가 나올 수 없다. 그럼에도 나왔다면 룰 카탈로그·엔진 쪽 계약 위반 신호다.
  // 판단은 `lib/decisionView` 의 술어가 한다 — 여기에 어휘 비교를 두지 않는다 (D87).
  const clearOnSale = isClearOnSaleAnomaly(result.verdict, result.disposal_mode);

  return (
    <div style={sx("display:flex;flex-direction:column;gap:15px")}>
      {clearOnSale && (
        <StatusBanner tone="warn">
          <span>
            <b>⚠ 계약 위반 신호</b> — <Mono>SALE</Mono> 인데 판정이 <Mono>CLEAR</Mono> 입니다.
            매각은 세금계산서 선행조건이 항상 발화해 <Mono>CONDITIONAL</Mono> 이하로 나와야
            합니다 (D78 부수 확정). 룰 카탈로그 적재 상태를 확인하세요.
          </span>
        </StatusBanner>
      )}

      <VerdictBanner
        view={view}
        headline={verdictHeadline(result.verdict)}
        result={result}
        httpStatus={httpStatus}
        detail={detail}
      />

      {citations.length > 0 && (
        <section style={sx("display:flex;flex-direction:column;gap:6px")}>
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>인용 조문·계약</span>
          <LawCitationRow citations={citations} />
        </section>
      )}

      <FindingList
        title="차단 (BLOCKING)"
        tone="block"
        note="해소하거나 서명 시 우회(사유 필수)"
        findings={blockers}
      />
      <FindingList
        title="보류 (HOLD)"
        tone="hold"
        note="경계 구간 — 전문가 검토가 필요합니다"
        findings={holds}
      />
      <FindingList
        title="사실 부족 (INSUFFICIENT_FACTS)"
        tone="insufficient"
        note="값을 모르는 것이지 조건 미해당이 아닙니다"
        findings={insufficient}
      />
      <FindingList
        title="선행조건 (PRECONDITION)"
        tone="precondition"
        note="이행 후 진행할 수 있습니다"
        findings={preconditions}
      />

      <ChecklistBlock items={checklist} />

      {missingFacts.length > 0 && (
        <Panel title="채워야 할 사실 (missing_facts)">
          <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}>
            {missingFacts.map((m) => (
              <span
                key={m}
                style={sx(
                  "font:600 11px 'JetBrains Mono',monospace;border:1px dashed var(--dim2);" +
                    "border-radius:4px;padding:3px 8px;color:var(--ink2)"
                )}
              >
                {m}
              </span>
            ))}
          </div>
          <div style={sx("margin-top:7px;font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
            자산 등록부에 값이 들어오면 판정이 바뀝니다. 이 화면에서는 입력하지 않습니다 —
            자산 데이터는 사전판정이 고칠 수 있는 것이 아닙니다 (무저장, D71).
          </div>
        </Panel>
      )}

      {resolveOptions.length > 0 && (
        <Panel title="해소 경로 (resolve_options)">
          <ul
            style={sx("margin:0;padding-left:16px;font:12.5px/1.8 'Pretendard';color:var(--ink2)")}
          >
            {resolveOptions.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </Panel>
      )}

      <DraftRequest asset={asset} result={result} />

      <Panel title="고려하지 않은 것 (not_considered)">
        {notConsidered.length ? (
          <ul
            style={sx("margin:0;padding-left:16px;font:12px/1.8 'Pretendard';color:var(--dim)")}
          >
            {notConsidered.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <span style={sx("font:12px 'Pretendard';color:var(--dim2)")}>
            응답에 항목이 없습니다 — 고려 범위가 넓다는 뜻이 아닙니다.
          </span>
        )}
        {disclaimer && (
          <div style={sx("margin-top:9px;font:11.5px/1.7 'Pretendard';color:var(--dim)")}>
            {disclaimer}
          </div>
        )}
        {note && (
          <div style={sx("margin-top:6px;font:11.5px/1.7 'Pretendard';color:var(--dim2)")}>
            {note}
          </div>
        )}
      </Panel>

      <FactsUsed result={result} />
    </div>
  );
}

function VerdictBanner({
  view,
  headline,
  result,
  httpStatus,
  detail,
}: {
  /** 색·문안 전부 `lib/decisionView` 가 정해 준 것 — 여기서 다시 해석하지 않는다 */
  view: VerdictLabel;
  headline: string;
  result: ApiPrecheck;
  httpStatus: number | null;
  detail: string;
}) {
  return (
    <section
      style={sx(
        `${view.skin};border-radius:8px;padding:13px 15px;` +
          "display:flex;flex-direction:column;gap:7px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={sx("font:700 16px 'JetBrains Mono',monospace")}>{headline}</span>
        <span style={sx("font:11px 'JetBrains Mono',monospace;opacity:.8")}>
          HTTP {httpStatus ?? "?"}
        </span>
        <span style={sx("font:11px 'JetBrains Mono',monospace;opacity:.8")}>
          {result.disposal_mode}
        </span>
        <span style={sx("font:11px 'JetBrains Mono',monospace;opacity:.8")}>
          처분일 {result.disposal_date ?? "미입력"}
        </span>
        <span style={sx("font:11px 'JetBrains Mono',monospace;opacity:.8")}>
          기준일 {result.evaluated_at}
        </span>
        <EvidenceCompletenessBadge value={result.evidence_completeness} />
      </div>

      <div style={sx("font:12.5px/1.7 'Pretendard'")}>{view.guidance}</div>

      {detail && (
        <div style={sx("font:12px/1.6 'Pretendard';opacity:.9")}>
          <b>사유</b> · {detail}
        </div>
      )}

      {result.disposal_date === null && (
        <div style={sx("font:11.5px/1.6 'Pretendard';opacity:.85")}>
          처분일을 넣지 않았습니다 — 세액공제 사후관리 판정은 이 값 없이는 나오지 않습니다.
        </div>
      )}
    </section>
  );
}

/**
 * 근거(조문 원문) 수집 상태 배지.
 *
 * ⛔ 어휘 판단(`COMPLETE`·`LAW_TEXT_PENDING`·키 부재·미지 값)과 색은 전부
 * `lib/decisionView.evidenceCompletenessView()` 가 한다 — 이 컴포넌트에는 어휘 비교도
 * 성공색 토큰도 없다 (D87). 여기 남는 것은 **상태와 무관한 타이포뿐**이다.
 */
function EvidenceCompletenessBadge({ value }: { value: unknown }) {
  const type =
    "font:700 9.5px 'JetBrains Mono',monospace;border-radius:3px;padding:3px 7px;white-space:nowrap";
  const badge = evidenceCompletenessView(value);

  return (
    <span title={badge.hint || undefined} style={sx(`${type};${badge.skin}`)}>
      {badge.text}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* 처분서 초안 요청 — 채팅 경유 (신규 API 0 · 신규 SSE 소비 0)                  */

/**
 * 버튼은 **이동만** 한다. `/technician?prefill=…` 로 가서 컴포저에 문장을 채워 넣고,
 * **전송은 사람이 누른다.**
 *
 * ⛔ 자동 전송 금지 — 사람이 무엇을 요청하는지 보고 눌러야 한다 (D29 와 같은 태도:
 *    이력을 남기는 행동은 명시적 액션이어야 한다).
 * ⛔ 이 버튼이 도구를 부르거나 생성 API 를 치지 않는다 — 도구는 에이전트만 부른다(D15·D10).
 */
function DraftRequest({ asset, result }: { asset: ApiAsset; result: ApiPrecheck }) {
  // 문장은 **판정에 실제로 쓰인 값**으로 만든다 (폼 state 가 아니라 응답).
  const when = result.disposal_date
    ? `처분 예정일은 ${result.disposal_date}야`
    : "처분 예정일은 아직 정하지 않았어";
  const sentence =
    `${asset.asset_id} 자산의 처분서 초안을 만들어 줘. ` +
    `처분 방식은 ${result.disposal_mode}이고, ${when}.`;

  // 하위 설비가 **정확히 1대일 때만** 장비를 실어 보낸다. 여러 대 중 하나를 골라 보내면
  // 화면이 사실을 지어내는 것이다 (D68 — 처분의 단위는 호스트 자산이지 인버터가 아니다).
  const equipment = Array.isArray(asset.equipment) ? asset.equipment : [];
  const soleEquipment =
    equipment.length === 1 && typeof equipment[0]?.equipment_id === "string"
      ? (equipment[0].equipment_id as string)
      : null;

  const href =
    `/technician?prefill=${encodeURIComponent(sentence)}` +
    (soleEquipment ? `&equipment=${encodeURIComponent(soleEquipment)}` : "");

  // 차단 어휘 판단은 `lib/decisionView` 의 총칭 술어가 한다 (D87).
  // **모르는 판정도 차단으로 본다** — 예전 `=== "BLOCKED" || …` 비교는 미지 어휘를 조용히
  // 안심 문안 쪽으로 떨어뜨렸다. 알려진 5종의 표시는 이전과 동일하다.
  const needsOverride = isBlocking(result.verdict);

  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--pocard);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:9px"
      )}
    >
      <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>처분서 초안 요청</span>

      <div style={sx("font:12px/1.7 'Pretendard';color:var(--dim)")}>
        초안 생성은 <b style={sx("color:var(--ink2)")}>에이전트가 도구를 호출</b>해서 합니다 —
        이 화면은 채팅으로 이동해 문장을 채워 넣을 뿐이고,{" "}
        <b style={sx("color:var(--ink2)")}>전송은 직접 누르셔야 합니다.</b>
      </div>

      <div
        style={sx(
          "border:1px dashed var(--line2);border-radius:6px;padding:9px 11px;" +
            "font:12px/1.6 'Pretendard';color:var(--ink2);background:var(--evi)"
        )}
      >
        &ldquo;{sentence}&rdquo;
      </div>

      <div style={sx("display:flex;align-items:center;gap:11px;flex-wrap:wrap")}>
        <Link href={href} style={sx("text-decoration:none")}>
          <Button>진단 콘솔에서 초안 요청 →</Button>
        </Link>
        <Link
          href="/manager"
          style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          승인 큐 열기 →
        </Link>
      </div>

      <div style={sx("font:11.5px/1.7 'Pretendard';color:var(--dim2)")}>
        {needsOverride ? (
          <>
            지금 판정은 <Mono size={11}>{result.verdict}</Mono> 입니다 — 초안은 만들 수 있지만
            서명에는 <b style={sx("color:var(--error-tx)")}>우회(override)와 사유</b>가
            필요합니다. 우회는 사람만 넣을 수 있고 서명자와 함께 기록됩니다.
          </>
        ) : (
          <>
            초안이 만들어지면 <b style={sx("color:var(--ink2)")}>승인 큐</b>로 제출해 팀장 서명을
            받습니다. 확정은 서명으로만 이뤄집니다 — 이 화면에서 확정되지 않습니다.
          </>
        )}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:12px 14px;" +
          "display:flex;flex-direction:column;gap:7px"
      )}
    >
      <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>{title}</span>
      {children}
    </section>
  );
}

/** 판정에 실제로 쓰인 사실. **키가 없으면 그 사실을 모른다는 뜻**이다 (`build_facts`, D62). */
function FactsUsed({ result }: { result: ApiPrecheck }) {
  const facts =
    result.facts_used && typeof result.facts_used === "object"
      ? (result.facts_used as Record<string, unknown>)
      : {};
  const rows = Object.entries(facts);
  if (!rows.length) return null;

  return (
    <details style={sx("border:1px solid var(--line);border-radius:8px;background:var(--panel)")}>
      <summary
        style={sx(
          "cursor:pointer;padding:10px 14px;font:700 12px 'Pretendard';color:var(--ink2);list-style:none"
        )}
      >
        판정에 쓰인 사실 {rows.length}건 (facts_used) — 여기 없는 항목은 &ldquo;모른다&rdquo;입니다
      </summary>
      <div
        style={sx(
          "padding:0 14px 12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:5px"
        )}
      >
        {rows.map(([k, v]) => (
          <div key={k} style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim)")}>
            {k} · <span style={sx("color:var(--ink2)")}>{JSON.stringify(v)}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
