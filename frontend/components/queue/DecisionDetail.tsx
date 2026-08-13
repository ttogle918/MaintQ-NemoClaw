"use client";

import { KindBadge, StateBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import type { ApiDecision } from "@/lib/api";
import { bannerSkin, verdictHeadline, verdictView } from "@/lib/decisionView";
import type { QueueTone } from "@/lib/queueState";
import { sx } from "@/lib/sx";
import type { EvidenceEntry } from "@/lib/types";
import { EvidenceCard } from "./EvidenceCard";
import { SignBar } from "./SignBar";

/**
 * 처분 결정 상세 (S10 계층 3) — `GET /api/decisions/{id}` 를 그대로 화면에 편다.
 *
 * ★ 이 화면이 지키는 세 가지
 *   ① **차단 판정을 성공처럼 그리지 않는다** (D87). 판정 → 톤 매핑은
 *      `lib/decisionView.verdictView()` 의 total 맵 한 곳이고, 맵 밖 값은 `warn` + 원문이다.
 *   ② **빠진 것을 숨기지 않는다** (D65·D86). `missing_sections` 는 접히지 않는 자리에 렌더하고,
 *      `hash_fixed:false` 는 "해시로 고정되지 않은 근거"라고 항목마다 밝힌다.
 *   ③ **근거의 성격을 섞지 않는다** — 법령·계약 근거 칩(`§`)과 매뉴얼 인용 칩
 *      (`CitationChip`, `▤`)은 시각적으로 다르다. 하나는 조문이고 하나는 페이지다.
 *
 * ⛔ 문서 문안을 프론트가 만들지 않는다. `documents` 는 백엔드가 번들에서 렌더한 것이고
 *   (D86 — 저장하지 않고 조립 시점 계산), 여기서는 **옮겨 적기만** 한다.
 */
export function DecisionDetail({
  decision,
  onUpdated,
  onReload,
}: {
  decision: ApiDecision;
  /** 서명·반려 성공 — 갱신된 결정으로 교체된다 (상세가 `signed` 로 전환되고 버튼이 사라진다) */
  onUpdated?: (updated: ApiDecision) => void;
  /** 409 뒤 재조회 */
  onReload?: () => void;
}) {
  const docs = rec(decision.documents);
  const approval = rec(docs.approval);
  const warranty = rec(docs.representation_warranty);
  const evidence = rec(docs.evidence_package);
  const footnotes = footnoteMap(arr(approval.law_footnotes));

  const buckets = BUCKETS.map((b) => ({ ...b, items: arr(approval[b.key]).map(rec) }));
  const resolveOptions = uniqueSorted(
    buckets.flatMap((b) => b.items.flatMap((i) => strings(i.resolve_options)))
  );

  const v = verdictView(decision.verdict_at_signing);

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px")}>
      {/* ── 헤더 ─────────────────────────────────────────────────────────── */}
      <div style={sx("display:flex;align-items:center;gap:9px;margin-bottom:14px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{decision.decision_id}</Mono>{" "}
          {str(decision.asset_name) ?? decision.asset_id}
        </span>
        <KindBadge kind="disposal" size={10} />
        <StateBadge kind="disposal" state={decision.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {decision.requested_by_name || "-"}
          {decision.created_at ? ` · ${decision.created_at}` : ""}
        </span>
      </div>

      {/* ── 판정 배너 — 차단 어휘는 경고 톤 + 해소 경로 (⛔ 성공 톤 금지, D87) ── */}
      <VerdictBanner
        tone={v.tone}
        headline={verdictHeadline(decision.verdict_at_signing)}
        note={v.note}
        resolveOptions={v.resolveRequired ? resolveOptions : []}
      />

      <EvidenceCard title="처분 결정 요약 · 근거는 대화가 아니라 법령·룰이다" entries={summary(decision, approval)} />

      {/* ── 판정 근거 4버킷 ──────────────────────────────────────────────── */}
      <Section
        title="판정 근거 · 4버킷"
        sub="차단 / 선결 / 보류 / 근거부족 — 0건인 버킷도 숨기지 않는다"
      >
        <div style={sx("font:11px/1.6 'Pretendard';color:var(--dim2);margin-bottom:10px")}>
          <LawChipSample /> 법령·계약 근거(조문) · <ManualChipSample /> 매뉴얼 인용(페이지) —
          근거의 성격이 다릅니다.
        </div>
        {buckets.map((b) => (
          <Bucket key={b.key} label={b.label} hint={b.hint} items={b.items} footnotes={footnotes} />
        ))}
      </Section>

      {/* ── 문서 미리보기 (D86 — 저장하지 않고 조립 시점 렌더) ─────────────── */}
      {/* 톤을 문구에서 추측하지 않는다 — 상태값(template_reviewed)으로 정한다 (D87·D90).
          미검수면 경고, 검수 완료면 정보. 검수가 끝나도 줄을 없애지 않는 이유는
          법적 문서에 "언제 검수했는가" 가 남아야 하기 때문이다. */}
      {str(docs.template_review_notice) && (
        <Notice tone={docs.template_reviewed === true ? "info" : "warn"}>
          {docs.template_reviewed === true ? "✓ " : "⚠ "}
          {str(docs.template_review_notice)}
        </Notice>
      )}

      <Section
        title={str(approval.title) ?? "처분 승인서"}
        sub="미리보기 — 백엔드가 근거 번들에서 렌더한 문안"
      >
        <ApprovalPreview approval={approval} footnotes={footnotes} />
      </Section>

      <Section
        title={str(warranty.title) ?? "진술 및 보장서"}
        sub="미리보기 — 룰 해석 문안을 그대로 옮긴다"
      >
        <WarrantyPreview warranty={warranty} footnotes={footnotes} />
      </Section>

      <Section
        title={str(evidence.title) ?? "처분 증빙 패키지"}
        sub="빠진 절과 해시 고정 여부를 함께 싣는다 (D65·D86)"
      >
        <MissingSections values={strings(docs.missing_sections)} />
        <HashFixedNotice value={docs.hash_fixed} note={str(docs.hash_fixed_note)} />
        <EvidencePackage evidence={evidence} />
      </Section>

      <SignBar
        decisionId={decision.decision_id}
        state={decision.state}
        requiresOverride={decision.requires_override}
        onSigned={onUpdated}
        onRejected={onUpdated}
        onReload={onReload}
      />
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 응답 좁혀 읽기                                                             */
/*                                                                            */
/* `ApiDecision.documents` 는 `Record<string, unknown>` 이다 — 백엔드가 키를    */
/* 더할 때마다 `lib/api.ts` 가 흔들리지 않게 일부러 열어 둔 계약이라, 좁히는   */
/* 책임이 렌더 쪽에 있다. **없으면 없다고 그린다. 기본값으로 메우지 않는다.**  */

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
function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

interface Footnote {
  citation: string | null;
  effectiveFrom: string | null;
  note: string | null;
}

/** `law_ref_id` → 조문 표기. 표기를 프론트가 만들지 않는다 — 백엔드 각주를 찾아 쓸 뿐이다. */
function footnoteMap(list: unknown[]): Record<string, Footnote> {
  const out: Record<string, Footnote> = {};
  for (const raw of list) {
    const f = rec(raw);
    const id = str(f.law_ref_id);
    if (!id) continue;
    out[id] = {
      citation: str(f.citation),
      effectiveFrom: str(f.effective_from),
      note: str(f.note),
    };
  }
  return out;
}

const BUCKETS: { key: string; label: string; hint: string }[] = [
  { key: "blockers", label: "차단 (BLOCKING)", hint: "우회 없이는 처분할 수 없는 근거" },
  { key: "preconditions", label: "선결 (PRECONDITION)", hint: "처분 전에 이행해야 하는 조건" },
  { key: "holds", label: "보류 (HOLD)", hint: "판단을 멈출 사유" },
  {
    key: "insufficient",
    label: "근거부족 (INSUFFICIENT_FACTS)",
    hint: "'문제 없음'이 아니라 '아직 모른다'",
  },
];

function summary(d: ApiDecision, approval: Record<string, unknown>): EvidenceEntry[] {
  const asset = rec(approval.asset);
  const rows: EvidenceEntry[] = [
    {
      label: "ASSET",
      value: (
        <>
          {str(asset.name) ?? str(d.asset_name) ?? "-"} · <Mono>{d.asset_id}</Mono>
          {str(asset.category) && ` · ${str(asset.category)}`}
        </>
      ),
    },
    {
      label: "처분",
      value: (
        <>
          {str(approval.disposal_mode_label) ?? "-"}{" "}
          <Mono size={11}>{str(d.disposal_mode) ?? "-"}</Mono>
          {" · 예정일 "}
          {str(d.disposal_date) ?? "미정 (지정되지 않음)"}
        </>
      ),
    },
  ];

  const book = num(asset.book_value);
  if (book !== null) {
    rows.push({ label: "장부가", value: `${book.toLocaleString()} 원` });
  }

  if (d.signed_at) {
    rows.push({
      label: "서명",
      value: `${d.reviewed_by_name || d.reviewed_by || "-"} · ${d.signed_at}`,
    });
    // D63 — 우회는 막는 게 아니라 **기록**한다. 서명된 건에는 우회 여부를 반드시 남긴다.
    rows.push({
      label: "우회",
      value: d.override ? (
        <b style={sx("color:var(--orange-tx)")}>
          예 — {str(d.override_reason) ?? "사유가 기록되지 않았습니다 (확인 필요)"}
        </b>
      ) : (
        "아니오"
      ),
    });
  }

  rows.push({
    label: "BUNDLE",
    value: <Mono size={11}>{str(d.bundle_hash) ?? "해시 없음 (확인 필요)"}</Mono>,
  });
  return rows;
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 표시 프리미티브                                                            */

/**
 * 톤 → 색은 **이 파일에 없다.** `lib/decisionView.bannerSkin()` 한 곳이 정한다 (D87) —
 * 컴포넌트에 `--ok-*` 가 남아 있으면 "색은 맵 한 곳"이라는 문언이 여기서 반증된다.
 * (Stage 6 W1 이전에는 여기 `BANNER_TONE` 이 있었다. 값은 그대로 옮겼다.)
 */

function VerdictBanner({
  tone,
  headline,
  note,
  resolveOptions,
}: {
  tone: QueueTone;
  /** `verdictHeadline()` 이 만든 제목 — 미지 값의 `⚠` 도 거기서 붙는다 */
  headline: string;
  note: string;
  resolveOptions: string[];
}) {
  return (
    <div
      style={sx(
        `${bannerSkin(tone)};border-radius:8px;padding:12px 14px;margin-bottom:14px;` +
          "display:flex;flex-direction:column;gap:7px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:8px")}>
        <span style={sx("font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;opacity:.8")}>
          판정
        </span>
        <Mono size={14}>{headline}</Mono>
      </div>
      <div style={sx("font:12.5px/1.6 'Pretendard'")}>{note}</div>
      {resolveOptions.length > 0 && (
        <div style={sx("font:12px/1.7 'Pretendard'")}>
          <b>해소 경로</b>
          <ul style={sx("margin:3px 0 0;padding-left:18px")}>
            {resolveOptions.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * 법령·계약 근거 칩.
 *
 * **매뉴얼 인용 칩(`CitationChip`, `▤` + 파란 실선)과 일부러 다르게 그린다** — 하나는
 * 법령 조문이고 하나는 매뉴얼 페이지다. 같은 모양으로 그리면 "매뉴얼에 이렇게 적혀 있다"와
 * "법이 이렇게 정한다"가 화면에서 같은 무게로 읽힌다.
 * 조문 표기 문자열은 백엔드 각주(`law_footnotes[].citation`)를 옮길 뿐 여기서 만들지 않는다.
 */
function LawChip({ id, foot }: { id: string; foot?: Footnote }) {
  const text = foot?.citation;
  return (
    <span
      title={foot?.effectiveFrom ? `시행 ${foot.effectiveFrom}` : undefined}
      style={sx(
        "display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;" +
          "border:1px dashed var(--line2);border-radius:4px;padding:2px 7px;" +
          "background:var(--raise);color:var(--ink2)"
      )}
    >
      <span>§</span> {text ?? `${id} — ${foot?.note ?? "조문 사본 없음"}`}
    </span>
  );
}

function LawChipSample() {
  return <span style={sx("font:600 11px 'JetBrains Mono',monospace;color:var(--ink2)")}>§</span>;
}
function ManualChipSample() {
  return <span style={sx("font:600 11px 'JetBrains Mono',monospace;color:var(--blue-tx)")}>▤</span>;
}

function Section({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--surface);" +
          "padding:14px 16px;margin-bottom:14px"
      )}
    >
      <div style={sx("margin-bottom:11px")}>
        <div
          style={sx(
            "font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--ink2)"
          )}
        >
          {title}
        </div>
        {sub && (
          <div style={sx("font:11px 'Pretendard';color:var(--dim2);margin-top:3px")}>{sub}</div>
        )}
      </div>
      {children}
    </div>
  );
}

function Notice({ tone, children }: { tone: QueueTone; children: React.ReactNode }) {
  return (
    <div
      style={sx(
        `${bannerSkin(tone)};border-radius:7px;padding:9px 12px;margin-bottom:14px;` +
          "font:12px/1.6 'Pretendard'"
      )}
    >
      {children}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 버킷                                                                       */

function Bucket({
  label,
  hint,
  items,
  footnotes,
}: {
  label: string;
  hint: string;
  items: Record<string, unknown>[];
  footnotes: Record<string, Footnote>;
}) {
  return (
    <div style={sx("margin-bottom:12px")}>
      <div style={sx("display:flex;align-items:baseline;gap:8px;margin-bottom:6px")}>
        <span style={sx("font:700 11px 'JetBrains Mono',monospace;color:var(--ink2)")}>
          {label}
        </span>
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          {items.length}건
        </span>
        <span style={sx("font:11px 'Pretendard';color:var(--dim3)")}>{hint}</span>
      </div>
      {items.length === 0 ? (
        <div style={sx("font:11.5px 'Pretendard';color:var(--dim2);padding-left:2px")}>
          해당 없음 — 이 버킷에서 발화한 룰이 없습니다.
        </div>
      ) : (
        <div style={sx("display:flex;flex-direction:column;gap:8px")}>
          {items.map((item, i) => (
            <BucketItem
              key={`${str(item.rule_id) ?? i}-${num(item.rule_version) ?? 0}`}
              item={item}
              footnotes={footnotes}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BucketItem({
  item,
  footnotes,
}: {
  item: Record<string, unknown>;
  footnotes: Record<string, Footnote>;
}) {
  const laws = strings(item.law_refs);
  const options = strings(item.resolve_options);
  return (
    <div
      style={sx(
        "border:1px solid var(--line2);border-radius:7px;background:var(--evi);padding:10px 12px;" +
          "display:flex;flex-direction:column;gap:6px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
        <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>
          {str(item.label) ?? "(제목 없음)"}
        </span>
        <Mono size={10.5}>
          {str(item.rule_id) ?? "?"} v{num(item.rule_version) ?? "?"}
        </Mono>
        {/* true 일 때만 그린다 — false 를 "검토 불필요"로 그리면 없는 확인이 생긴다 */}
        {item.requires_expert_review === true && (
          <span
            style={sx(
              "font:700 10px 'JetBrains Mono',monospace;color:var(--orange-tx);" +
                "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);" +
                "border-radius:3px;padding:2px 6px"
            )}
          >
            전문가 검토 필요
          </span>
        )}
      </div>
      {str(item.message) && (
        <div style={sx("font:12.5px/1.6 'Pretendard';color:var(--ink2)")}>
          {str(item.message)}
        </div>
      )}
      {laws.length > 0 && (
        <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}>
          {laws.map((id) => (
            <LawChip key={id} id={id} foot={footnotes[id]} />
          ))}
        </div>
      )}
      {options.length > 0 && (
        <div style={sx("font:12px/1.7 'Pretendard';color:var(--dim)")}>
          해소 경로
          <ul style={sx("margin:2px 0 0;padding-left:18px")}>
            {options.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 문서 미리보기                                                              */

function ApprovalPreview({
  approval,
  footnotes,
}: {
  approval: Record<string, unknown>;
  footnotes: Record<string, Footnote>;
}) {
  const asset = rec(approval.asset);
  const ids = Object.keys(footnotes);
  return (
    <div style={sx("display:flex;flex-direction:column;gap:9px")}>
      <Field label="자산">
        {str(asset.name) ?? "-"} <Mono size={11}>{str(asset.asset_id) ?? "-"}</Mono>
        {str(asset.category) && ` · ${str(asset.category)}`}
        {str(asset.acquired_at) && ` · 취득 ${str(asset.acquired_at)}`}
      </Field>
      <Field label="처분 방식">
        {str(approval.disposal_mode_label) ?? "-"}{" "}
        <Mono size={11}>{str(approval.disposal_mode) ?? "-"}</Mono>
      </Field>
      <Field label="처분 예정일">{str(approval.disposal_date) ?? "미정 (지정되지 않음)"}</Field>
      <Field label="인용 조문">
        {ids.length === 0 ? (
          <span style={sx("color:var(--dim2)")}>인용된 조문이 없습니다.</span>
        ) : (
          <span style={sx("display:inline-flex;gap:6px;flex-wrap:wrap")}>
            {ids.map((id) => (
              <LawChip key={id} id={id} foot={footnotes[id]} />
            ))}
          </span>
        )}
      </Field>
    </div>
  );
}

function WarrantyPreview({
  warranty,
  footnotes,
}: {
  warranty: Record<string, unknown>;
  footnotes: Record<string, Footnote>;
}) {
  const statements = arr(warranty.statements).map(rec);
  const contracts = arr(warranty.contracts).map(rec);
  return (
    <div style={sx("display:flex;flex-direction:column;gap:10px")}>
      {statements.length === 0 && (
        <div style={sx("font:12px 'Pretendard';color:var(--dim2)")}>진술 항목이 없습니다.</div>
      )}
      {statements.map((s, i) => (
        <div
          key={`${str(s.rule_id) ?? i}-${num(s.rule_version) ?? 0}`}
          style={sx("border-left:2px solid var(--line2);padding-left:10px")}
        >
          <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
            <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>
              {str(s.label) ?? "(제목 없음)"}
            </span>
            <Mono size={10.5}>
              {str(s.rule_id) ?? "?"} v{num(s.rule_version) ?? "?"}
            </Mono>
            {/* 확신도는 원문 어휘 그대로 — 색으로 승격하지 않는다 (D87) */}
            <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--dim2)")}>
              confidence {str(s.confidence) ?? "미상"}
            </span>
            {s.requires_expert_review === true && (
              <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--orange-tx)")}>
                전문가 검토 필요
              </span>
            )}
          </div>
          <div style={sx("font:12.5px/1.65 'Pretendard';color:var(--ink2);margin-top:4px")}>
            {str(s.statement) ?? "(문안 없음)"}
          </div>
          {strings(s.law_refs).length > 0 && (
            <div style={sx("display:flex;gap:6px;flex-wrap:wrap;margin-top:5px")}>
              {strings(s.law_refs).map((id) => (
                <LawChip key={id} id={id} foot={footnotes[id]} />
              ))}
            </div>
          )}
        </div>
      ))}

      {contracts.length > 0 && (
        <div>
          <div
            style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim2);margin-bottom:6px")}
          >
            계약 근거
          </div>
          <div style={sx("display:flex;flex-direction:column;gap:6px")}>
            {contracts.map((c, i) => (
              <div
                key={str(c.contract_ref) ?? i}
                style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}
              >
                <LawChip id={str(c.contract_ref) ?? "?"} foot={{ citation: str(c.contract_ref), effectiveFrom: null, note: null }} />
                <HashFixedMark value={c.hash_fixed} note={str(c.note)} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * **D86 의 핵심 표기** — 해시로 고정되지 않은 근거임을 항목마다 밝힌다.
 * `true` 를 초록 체크로 그리지 않는 이유는 D87 이다. 값이 없으면 "미상"이지 "고정됨"이 아니다.
 */
function HashFixedMark({ value, note }: { value: unknown; note?: string | null }) {
  if (value === false) {
    return (
      <span
        title={note ?? undefined}
        style={sx(
          "font:600 10px 'JetBrains Mono',monospace;color:var(--orange-tx);" +
            "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);" +
            "border-radius:3px;padding:2px 6px"
        )}
      >
        해시로 고정되지 않은 근거
      </span>
    );
  }
  if (value === true) {
    return (
      <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--dim)")}>
        해시 고정됨
      </span>
    );
  }
  return (
    <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--error-tx)")}>
      ⚠ 해시 고정 여부 미상
    </span>
  );
}

function HashFixedNotice({ value, note }: { value: unknown; note: string | null }) {
  return (
    <div
      style={sx(
        "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:7px;" +
          "padding:10px 12px;margin-bottom:11px;display:flex;flex-direction:column;gap:5px"
      )}
    >
      <HashFixedMark value={value} note={note} />
      {note && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--saf-cite-tx)")}>{note}</div>
      )}
    </div>
  );
}

/**
 * **빠진 절을 반드시 렌더한다** (D65·D86).
 * 접거나 숨기면 "증빙 패키지가 완성됐다"는 인상이 생기고, 그게 곧 지어낸 사실이다.
 */
function MissingSections({ values }: { values: string[] }) {
  if (values.length === 0) {
    // 목록이 비어 있다는 것도 사실이다 — 조용히 사라지지 않게 한 줄을 남긴다
    return (
      <div style={sx("font:11.5px 'Pretendard';color:var(--dim2);margin-bottom:11px")}>
        백엔드가 보고한 누락 절이 없습니다 (<Mono size={11}>missing_sections: []</Mono>).
      </div>
    );
  }
  return (
    <div
      style={sx(
        "border:1px dashed var(--error-tx);border-radius:7px;padding:10px 12px;margin-bottom:11px"
      )}
    >
      <div style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--error-tx)")}>
        이 패키지에 없는 절 · {values.length}건
      </div>
      <ul style={sx("margin:6px 0 0;padding-left:18px;font:12px/1.7 'Pretendard';color:var(--ink2)")}>
        {values.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  );
}

const METRIC_ROWS: { key: string; label: string; unit?: string }[] = [
  { key: "mtbf_days", label: "MTBF", unit: "일" },
  { key: "mttr_hours", label: "MTTR", unit: "시간" },
  { key: "availability", label: "가용도" },
  { key: "planned_ratio", label: "예방보전 비율" },
  { key: "cumulative_repair_ratio", label: "누적 수리비 / 취득가" },
  { key: "n_repairs_signed", label: "서명된 수리 건수" },
  { key: "n_repairs_unsigned", label: "서명 안 된 수리 건수" },
];

function EvidencePackage({ evidence }: { evidence: Record<string, unknown> }) {
  const metrics = rec(evidence.metrics);
  const history = arr(evidence.maintenance_history).map(rec);
  const renewals = arr(evidence.critical_parts_renewal).map(rec);
  const excluded = strings(metrics.excluded);

  return (
    <div style={sx("display:flex;flex-direction:column;gap:11px")}>
      <div>
        <div style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim2);margin-bottom:6px")}>
          보전지표 · 창 {num(metrics.window_months) ?? "?"}개월 · 기준{" "}
          {str(metrics.mtbf_basis) ?? "미상"}
        </div>
        <div style={sx("display:flex;flex-direction:column;gap:4px")}>
          {METRIC_ROWS.map((m) => (
            <div key={m.key} style={sx("display:flex;gap:12px;align-items:baseline")}>
              <span
                style={sx(
                  "font:600 11px 'JetBrains Mono',monospace;color:var(--dim);width:160px;flex-shrink:0"
                )}
              >
                {m.label}
              </span>
              <span style={sx("font:12.5px 'Pretendard';color:var(--ink)")}>
                {num(metrics[m.key]) === null ? (
                  // ⛔ null 을 0 이나 '양호'로 바꾸지 않는다 — 산출 못 한 것과 좋은 것은 다르다
                  <span style={sx("color:var(--dim2)")}>산출 불가 (판단 근거 부족)</span>
                ) : (
                  `${num(metrics[m.key])}${m.unit ? ` ${m.unit}` : ""}`
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {excluded.length > 0 && (
        <div style={sx("font:11.5px/1.7 'Pretendard';color:var(--dim)")}>
          <b>집계에서 제외한 것</b>
          <ul style={sx("margin:3px 0 0;padding-left:18px")}>
            {excluded.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {str(metrics.disclaimer) && (
        // 매수자에게 나가는 고지 — 요약하거나 줄이지 않는다 (D65)
        <div
          style={sx(
            "border-left:2px solid var(--saf-cite-bd);padding-left:10px;" +
              "font:11.5px/1.7 'Pretendard';color:var(--saf-cite-tx)"
          )}
        >
          {str(metrics.disclaimer)}
        </div>
      )}

      <Field label="정비 이력">
        {history.length === 0
          ? "서명된 정비 이력이 없습니다."
          : `서명된 레코드 ${history.length}건 — ${history
              .map((h) => `${str(h.repair_id) ?? "?"}(${str(h.work_type) ?? "?"})`)
              .join(" · ")}`}
      </Field>
      <Field label="핵심부품 갱신">
        {renewals.length === 0
          ? "핵심부품 갱신 기록이 없습니다."
          : renewals
              .map((r) => `${str(r.repair_id) ?? "?"} · ${strings(r.parts).join(", ")}`)
              .join(" / ")}
      </Field>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={sx("display:flex;gap:12px;align-items:baseline")}>
      <span
        style={sx(
          "font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:92px;flex-shrink:0"
        )}
      >
        {label}
      </span>
      <span style={sx("font:12.5px/1.6 'Pretendard';color:var(--ink)")}>{children}</span>
    </div>
  );
}
