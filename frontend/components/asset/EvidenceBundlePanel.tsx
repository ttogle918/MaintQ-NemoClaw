"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import { HashFixedMark } from "@/components/queue/DecisionDetail";
import {
  ApiError,
  errorBody,
  extractDetail,
  getEvidenceBundle,
  type ApiEvidenceBundle,
} from "@/lib/api";
import {
  evidenceBundleErrorView,
  verdictHeadline,
  verdictView,
  type EvidenceBundleErrorLabel,
} from "@/lib/decisionView";
import { sx } from "@/lib/sx";
import { MODES } from "./DisposalPanel";

/**
 * 근거 번들 화면 (S10 · `04 §14`·`06 §2.5`, MQ-1001/P37).
 *
 * `GET /api/assets/{id}/evidence-bundle` 상당(`build_evidence_bundle`)을 그대로 편다 —
 * 해시 대상 **5키**(laws·rules·evaluated·contracts·facts, D83)를 전부 보여 주고,
 * `verdict` 는 5키 밖 별도 필드로만 다룬다.
 *
 * **아무것도 저장하지 않는다** (D71) — 조회뿐이고 쓰기 경로가 없다.
 * 판정 색·어휘는 이 파일에 없다 — `lib/decisionView` 의 total 맵(D87)을 그대로 재사용한다.
 */

/* -------------------------------------------------------------------------- */
/* 응답 좁혀 읽기 — 지어내지 않는다 (`DecisionDetail.tsx` 와 같은 패턴)          */

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}
function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function strings(v: unknown): string[] {
  return arr(v).filter((x): x is string => typeof x === "string");
}

/* -------------------------------------------------------------------------- */
/* 422 — `DisposalPanel.parse422` 와 같은 필드 오류 패턴 (인라인 재구현)          */

interface FieldErrors {
  mode?: string;
  date?: string;
  general?: string;
}

function parse422(body: Record<string, unknown> | null): FieldErrors {
  const detail = body?.detail;
  if (typeof detail === "string") return { general: detail };
  if (!Array.isArray(detail)) return { general: "입력값을 확인해 주세요 (422)" };

  const out: FieldErrors = {};
  for (const d of detail) {
    if (!d || typeof d !== "object") continue;
    const r = d as Record<string, unknown>;
    const loc = Array.isArray(r.loc) ? r.loc.map((x) => String(x)) : [];
    const msg = typeof r.msg === "string" ? r.msg : "입력값이 올바르지 않습니다";
    if (loc.includes("disposal_mode")) out.mode = msg;
    else if (loc.includes("disposal_date")) out.date = msg;
    else out.general = msg;
  }
  return Object.keys(out).length ? out : { general: "입력값을 확인해 주세요 (422)" };
}

interface Failure {
  title: string;
  detail: string;
}

/**
 * 409/503 — `evidenceBundleErrorView` 로 얻은 어휘 + 부속 목록.
 * 409(`law_text_unavailable`) 는 `missing_law_refs`/`missing_rules` 가 본문 최상위에 있고,
 * 503(`rule_catalog_not_loaded`) 은 `detail` 이 `{reason, message}` 객체로 한 겹 더 감싸여
 * 온다(`backend/routers/maint_value.py` `RuleCatalogError` 경로) — 두 형태를 여기서 풀어 준다.
 */
interface EvidenceFailure {
  view: EvidenceBundleErrorLabel;
  detail: string;
  missingLawRefs: string[];
  missingRules: string[];
}

export function EvidenceBundlePanel({ assetId }: { assetId: string }) {
  const [mode, setMode] = useState<string | null>(null);
  /** ⛔ 오늘 날짜로 초기화하지 않는다 (D62) — 빈 문자열 = 사용자가 아직 모른다 */
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApiEvidenceBundle | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [evidenceFailure, setEvidenceFailure] = useState<EvidenceFailure | null>(null);

  async function run() {
    if (!mode || busy) return;
    setBusy(true);
    setFieldErrors({});
    setFailure(null);
    setEvidenceFailure(null);
    setResult(null);
    try {
      const r = await getEvidenceBundle("technician", assetId, mode, date || undefined);
      if (r.status === "ok") {
        setResult(r);
      } else {
        setFailure({
          title: "응답이 정상(ok)이 아닙니다",
          detail: r.reason ?? "(사유 없음)",
        });
      }
    } catch (e) {
      if (!(e instanceof ApiError)) {
        setFailure({
          title: "백엔드에 연결하지 못했습니다",
          detail:
            "근거 번들 요청이 전달되지 않았습니다 — 결과가 없는 것이지 근거가 없다는 뜻이 아닙니다. (uv run uvicorn backend.main:app --port 8003)",
        });
        return;
      }
      const body = errorBody(e);
      if (e.status === 404) {
        setFailure({
          title: "자산을 찾을 수 없습니다 (404)",
          detail: `${assetId} — 자산 등록부에 없는 식별자입니다.`,
        });
      } else if (e.status === 422) {
        setFieldErrors(parse422(body));
      } else if (e.status === 409) {
        const reason = typeof body?.reason === "string" ? body.reason : "";
        setEvidenceFailure({
          view: evidenceBundleErrorView(reason),
          detail: typeof body?.detail === "string" ? body.detail : "",
          missingLawRefs: strings(body?.missing_law_refs),
          missingRules: strings(body?.missing_rules),
        });
      } else if (e.status === 503) {
        // `HTTPException(503, {"reason":…, "message":…})` → FastAPI 가 `{"detail": {...}}` 로 감싼다
        const inner = rec(body?.detail);
        const reason = typeof inner.reason === "string" ? inner.reason : "";
        setEvidenceFailure({
          view: evidenceBundleErrorView(reason),
          detail: typeof inner.message === "string" ? inner.message : "",
          missingLawRefs: [],
          missingRules: [],
        });
      } else {
        setFailure({
          title: `근거 번들 조회에 실패했습니다 (${e.status})`,
          detail: extractDetail(e.body),
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
        <StatusBanner tone="error">
          <span>
            <b>{failure.title}</b>
            <br />
            {failure.detail}
          </span>
        </StatusBanner>
      )}

      {evidenceFailure && <EvidenceFailureBanner failure={evidenceFailure} />}

      {result && <EvidenceBundleResult data={result} />}

      {!result && !failure && !evidenceFailure && (
        <div
          style={sx(
            "border:1px dashed var(--line2);border-radius:7px;padding:14px 16px;" +
              "font:12.5px/1.7 'Pretendard';color:var(--dim)"
          )}
        >
          아직 조회하지 않았습니다. 처분 방식을 고르고 <b>근거 번들 조회</b>를 누르세요.
          <br />
          이 화면은 <b>아무것도 저장하지 않습니다</b> (무저장, D71).
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 입력 — `DisposalPanel.ModeForm` 과 동일한 패턴(MODES 는 그 파일에서 import)     */

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
        {mode === null && (
          <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
            선택 전에는 조회하지 않습니다 (기본값을 대신 고르지 않습니다)
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
          {busy ? "조회 중…" : "근거 번들 조회"}
        </Button>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
          GET <Mono size={11}>/api/assets/{"{id}"}/evidence-bundle</Mono> — 무저장 (D71)
        </span>
      </div>
    </section>
  );
}

function FieldError({ children }: { children: React.ReactNode }) {
  return <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--error-tx)")}>⚠ {children}</div>;
}

/* -------------------------------------------------------------------------- */
/* 409/503 실패 — `evidenceBundleErrorView` 어휘 + 부속 목록                    */

function EvidenceFailureBanner({ failure }: { failure: EvidenceFailure }) {
  const { view, detail, missingLawRefs, missingRules } = failure;
  return (
    <StatusBanner tone={view.recovery === "retry" ? "warn" : "error"}>
      <span style={sx("display:flex;flex-direction:column;gap:6px")}>
        <b>{view.known ? view.title : `⚠ ${view.title}`}</b>
        {detail && <span>{detail}</span>}
        {missingLawRefs.length > 0 && (
          <span>
            미수집 조문 {missingLawRefs.length}건 — {missingLawRefs.join(", ")}
          </span>
        )}
        {missingRules.length > 0 && (
          <span>
            누락된 룰 {missingRules.length}건 — {missingRules.join(", ")}
          </span>
        )}
      </span>
    </StatusBanner>
  );
}

/* -------------------------------------------------------------------------- */
/* 결과 — 5키(D83) 전부 + 판정 + not_considered/disclaimer/built_at/bundle_hash */

function EvidenceBundleResult({ data }: { data: ApiEvidenceBundle }) {
  // ⚠ 계약 위반 신호 — status:"ok" 인데 evidence_bundle 이 없거나 객체가 아니다.
  // 5개 섹션을 지어내지 않고 그 사실만 알린다.
  if (!data.evidence_bundle || typeof data.evidence_bundle !== "object") {
    return (
      <StatusBanner tone="error">
        <span>
          <b>⚠ 계약 위반 신호</b>
          <br />
          응답이 <Mono size={11}>status: &quot;ok&quot;</Mono> 인데{" "}
          <Mono size={11}>evidence_bundle</Mono> 이 없습니다 — 5개 섹션을 만들지 않습니다.
        </span>
      </StatusBanner>
    );
  }

  const bundle = rec(data.evidence_bundle);
  const laws = arr(bundle.laws).map(rec);
  const rules = arr(bundle.rules).map(rec);
  const evaluated = arr(bundle.evaluated).map(rec);
  const contracts = arr(bundle.contracts).map(rec);
  const facts = rec(bundle.facts);
  const factRows = Object.entries(facts);
  const notConsidered = strings(data.not_considered);
  const view = verdictView(data.verdict);

  return (
    <div style={sx("display:flex;flex-direction:column;gap:15px")}>
      {/* a. 판정 배너 — 어휘·톤은 전부 lib/decisionView 총칭 맵 (D87) */}
      <section
        style={sx(
          `${view.skin};border-radius:8px;padding:13px 15px;` +
            "display:flex;flex-direction:column;gap:7px"
        )}
      >
        <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
          <span style={sx("font:700 16px 'JetBrains Mono',monospace")}>
            {verdictHeadline(data.verdict)}
          </span>
        </div>
        <div style={sx("font:12.5px/1.7 'Pretendard'")}>{view.note}</div>
      </section>

      {/* b. hash_fixed 의미 고지 — 고정 문구 (04 §14 근거) */}
      <div
        style={sx(
          "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:7px;" +
            "padding:10px 12px;font:11.5px/1.7 'Pretendard';color:var(--saf-cite-tx)"
        )}
      >
        <Mono size={11}>bundle_hash</Mono>는 이 화면의 5개 항목(laws·rules·evaluated·contracts·
        facts)만 고정합니다. 렌더된 문서나 증빙 패키지는 해시 대상이 아닙니다.
      </div>

      {/* c. laws[] */}
      <Panel title={`인용 조문 · laws (${laws.length}건)`}>
        {laws.length === 0 ? (
          <Empty>4버킷 findings 가 인용한 조문이 없습니다.</Empty>
        ) : (
          <RowList>
            {laws.map((l, i) => (
              <Row key={str(l.law_ref_id) ?? i}>
                <Mono size={11.5}>{str(l.law_ref_id) ?? "?"}</Mono>
                <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
                  시행 {str(l.effective_from) ?? "미상"}
                </span>
                <HashTag value={l.text_hash} />
              </Row>
            ))}
          </RowList>
        )}
      </Panel>

      {/* d. rules[] */}
      <Panel title={`인용 룰 · rules (${rules.length}건)`}>
        {rules.length === 0 ? (
          <Empty>인용된 룰이 없습니다.</Empty>
        ) : (
          <RowList>
            {rules.map((r, i) => (
              <Row key={`${str(r.rule_id) ?? i}-${num(r.rule_version) ?? 0}`}>
                <Mono size={11.5}>
                  {str(r.rule_id) ?? "?"} v{num(r.rule_version) ?? "?"}
                </Mono>
                <HashTag value={r.rule_hash} />
              </Row>
            ))}
          </RowList>
        )}
      </Panel>

      {/* e. evaluated[] — 룰 단위 verdict 는 자산 판정 5종과 다른 어휘, 무채색으로만 찍는다 */}
      <Panel title={`평가된 전체 룰 · evaluated (${evaluated.length}건)`}>
        {evaluated.length === 0 ? (
          <Empty>평가된 룰이 없습니다 — 계약 위반 신호일 수 있습니다.</Empty>
        ) : (
          <RowList>
            {evaluated.map((e, i) => {
              const lawRefs = strings(e.law_refs);
              return (
                <Row key={`${str(e.rule_id) ?? i}-${num(e.rule_version) ?? 0}`}>
                  <Mono size={11.5}>
                    {str(e.rule_id) ?? "?"} v{num(e.rule_version) ?? "?"}
                  </Mono>
                  <span style={sx("font:600 11px 'JetBrains Mono',monospace;color:var(--ink2)")}>
                    {str(e.verdict) ?? "?"}
                  </span>
                  {lawRefs.length > 0 && (
                    <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
                      {lawRefs.join(", ")}
                    </span>
                  )}
                </Row>
              );
            })}
          </RowList>
        )}
      </Panel>

      {/* f. contracts[] */}
      <Panel title={`계약 근거 · contracts (${contracts.length}건)`}>
        {contracts.length === 0 ? (
          <Empty>계약 근거가 인용되지 않았습니다.</Empty>
        ) : (
          <RowList>
            {contracts.map((c, i) => (
              <Row key={str(c.contract_ref) ?? i}>
                <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>
                  {str(c.contract_ref) ?? "?"}
                </span>
                <HashFixedMark value={c.hash_fixed} note={str(c.note)} />
              </Row>
            ))}
          </RowList>
        )}
      </Panel>

      {/* g. facts — key-value grid, 기본 펼침 (D62 — DisposalPanel.FactsUsed 와 같은 문안) */}
      <details
        open
        style={sx("border:1px solid var(--line);border-radius:8px;background:var(--panel)")}
      >
        <summary
          style={sx(
            "cursor:pointer;padding:10px 14px;font:700 12px 'Pretendard';color:var(--ink2);list-style:none"
          )}
        >
          판정에 쓰인 사실 {factRows.length}건 (facts) — 여기 없는 항목은 &ldquo;모른다&rdquo;입니다
        </summary>
        <div
          style={sx(
            "padding:0 14px 12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:5px"
          )}
        >
          {factRows.length === 0 ? (
            <Empty>facts 가 비어 있습니다.</Empty>
          ) : (
            factRows.map(([k, v]) => (
              <div key={k} style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim)")}>
                {k} · <span style={sx("color:var(--ink2)")}>{JSON.stringify(v)}</span>
              </div>
            ))
          )}
        </div>
      </details>

      {/* h. not_considered / disclaimer / built_at / bundle_hash */}
      <Panel title="고려하지 않은 것 (not_considered)">
        {notConsidered.length ? (
          <ul style={sx("margin:0;padding-left:16px;font:12px/1.8 'Pretendard';color:var(--dim)")}>
            {notConsidered.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <span style={sx("font:12px 'Pretendard';color:var(--dim2)")}>
            응답에 항목이 없습니다 — 고려 범위가 넓다는 뜻이 아닙니다.
          </span>
        )}
        {str(data.disclaimer) && (
          <div style={sx("margin-top:9px;font:11.5px/1.7 'Pretendard';color:var(--dim)")}>
            {str(data.disclaimer)}
          </div>
        )}
      </Panel>

      <Panel title="번들 메타">
        <Row>
          <span style={sx("font:700 10.5px 'Pretendard';color:var(--dim2)")}>built_at</span>
          <span style={sx("font:11.5px 'JetBrains Mono',monospace;color:var(--ink2)")}>
            {str(data.built_at) ?? "미상"}
          </span>
        </Row>
        <Row>
          <span style={sx("font:700 10.5px 'Pretendard';color:var(--dim2)")}>bundle_hash</span>
          {/* 서명 검증 대조값 — 축약하지 않고 전체 표시 (D86) */}
          <Mono size={11}>{str(data.bundle_hash) ?? "해시 없음 (확인 필요)"}</Mono>
        </Row>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 표시 프리미티브 — 어휘 판단 없음, 배치만 담당                                */

function HashTag({ value }: { value: unknown }) {
  const s = typeof value === "string" && value ? value : null;
  if (!s) {
    return <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>해시 없음</span>;
  }
  return (
    <span title={s} style={sx("cursor:help")}>
      <Mono size={10.5}>{s.slice(0, 16)}…</Mono>
    </span>
  );
}

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

function RowList({ children }: { children: React.ReactNode }) {
  return <div style={sx("display:flex;flex-direction:column;gap:6px")}>{children}</div>;
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "border:1px solid var(--line2);border-radius:6px;background:var(--evi);padding:7px 10px;" +
          "display:flex;align-items:center;gap:10px;flex-wrap:wrap"
      )}
    >
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>{children}</div>
  );
}
