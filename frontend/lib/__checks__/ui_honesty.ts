/**
 * L1 — UI 정직성 순수 함수 단언 (D87).
 *
 * 프론트에 테스트 러너가 없다(실측: `tsc --noEmit`·`next build` 뿐). 러너를 새로 들이지 않고
 * **이미 회귀에 있는 `tsc`** 로 컴파일해 `node` 로 돌린다 — 신규 의존성 0.
 * 이게 가능한 이유는 `lib/ownership.ts` 가 리액트를 쓰지 않고 `@/` 별칭도 쓰지 않기 때문이다.
 * 그 두 제약 자체는 `spikes/ui_honesty_contract.py` 가 별도로 단언한다.
 *
 * 실행(스파이크가 대신 한다):
 *   cd frontend
 *   npx tsc lib/__checks__/ui_honesty.ts --outDir <tmp> --module commonjs --target es2020 --skipLibCheck
 *   node <tmp>/__checks__/ui_honesty.js
 *
 * 출력 규약: 한 줄에 `L1-<n>|PASS|<detail>` — 스파이크가 이 형식을 파싱해 표에 싣는다.
 *
 * ⛔ 기대값을 검증 대상에서 파생시키지 않는다. 카테고리 9종·"확인됨" 같은 값은 여기에
 *   **독립적으로 하드코딩**한다 — `ownership.ts` 의 상수를 그대로 참조해 비교하면
 *   상수를 망가뜨려도 검사가 함께 망가져 공허하게 통과한다(Sprint 6 에서 실제로 났던 실패).
 */
import {
  auditRows,
  CATEGORIES,
  ITEM_VIEW,
  itemView,
  summarize,
  toRows,
  VERDICT_VIEW,
  verdictView,
  type Row,
  type Tone,
} from "../ownership";
import { estimateNotice, isHoldVerdict, showMetric, showTrend } from "../maintValue";
import { stateView } from "../queueState";
import { deadlineStateView } from "../deadlines";
import { gradeView } from "../riskGrade";
import { groupStatusView, onboardingBadgeView, rowStateView, safetyStateView } from "../onboarding";
import { a2aStatusLabel, a2aStatusTone } from "../a2a";

/* -------------------------------------------------------------------------- */
/* 러너                                                                        */

let failed = 0;
let n = 0;

function check(name: string, ok: boolean, detail: string): void {
  n += 1;
  if (!ok) failed += 1;
  console.log(`L1-${n}|${ok ? "PASS" : "FAIL"}|${name}|${detail.replace(/\s+/g, " ")}`);
}

/* -------------------------------------------------------------------------- */
/* 독립 오라클 — 검증 대상에서 파생시키지 않은 기대값                          */

const EXPECTED_CATEGORIES = [
  "물리적 상태",
  "가동 이력",
  "정비 이력",
  "기술적 진부화",
  "권리관계",
  "법정 요건",
  "재무·회계",
  "시장·가격",
  "이전 비용",
];

/** 실 응답을 축약한 픽스처. **3번째 카테고리를 일부러 0건**으로 둔다(뮤턴트 ⓒ 탐지용). */
function fixture(): {
  status: string;
  verdict: string;
  categories: { category: string; items: { item: string; state: string; evidence: string | null; limit: string | null }[] }[];
} {
  return {
    status: "ok",
    verdict: "PARTIAL",
    categories: EXPECTED_CATEGORIES.map((c, i) => ({
      category: c,
      items:
        i === 2
          ? []
          : [
              {
                item: `${c} 확인 항목`,
                state: "UNVERIFIED",
                evidence: null,
                limit: "원천 없음 — 저장소에 해당 테이블이 없다",
              },
              {
                item: `${c} 기록 항목`,
                state: "VERIFIED",
                evidence: "사내 기록 조회 결과",
                limit: null,
              },
            ],
    })),
  };
}

function row(over: Partial<Row>): Row {
  return {
    category: "권리관계",
    item: "샘플",
    state: "VERIFIED",
    badge: "확인됨",
    tone: "ok",
    evidence: "근거",
    limit: null,
    empty: false,
    ...over,
  };
}

/** 9카테고리를 채운 정상 행 묶음 — 카테고리 수 불변식과 다른 불변식을 섞지 않기 위한 것. */
function nineRows(extra: Row[] = []): Row[] {
  return [...EXPECTED_CATEGORIES.map((c) => row({ category: c })), ...extra];
}

/* -------------------------------------------------------------------------- */
/* L1-1 — ITEM_VIEW 는 total 이고, 미확인은 절대 "ok" 가 아니다                 */

{
  const keys = Object.keys(ITEM_VIEW).sort();
  const v = ITEM_VIEW.VERIFIED;
  const u = ITEM_VIEW.UNVERIFIED;
  check(
    "ITEM_VIEW total(2키) · UNVERIFIED.tone !== 'ok'",
    keys.join(",") === "UNVERIFIED,VERIFIED" &&
      v.tone === "ok" &&
      u.tone !== "ok" &&
      u.tone === "warn",
    `keys=[${keys.join(",")}] VERIFIED=${v.tone} UNVERIFIED=${u.tone}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-2 — 맵 안 값의 배지·톤                                                   */

{
  const v = itemView("VERIFIED");
  const u = itemView("UNVERIFIED");
  check(
    "itemView 맵 안 값 — VERIFIED='확인됨'/ok · UNVERIFIED='미확인'/warn",
    v.badge === "확인됨" && v.tone === "ok" && u.badge === "미확인" && u.tone === "warn",
    `VERIFIED={${v.badge},${v.tone}} UNVERIFIED={${u.badge},${u.tone}}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-3 — 맵 밖 값은 어떤 경우에도 "ok" 로 떨어지지 않는다                      */

{
  const unknowns = ["PENDING", "verified", "ok", "", "UNKNOWN", "확인됨"];
  const bad: string[] = [];
  // ★ "ok 가 아니다" 로는 부족하다 — **정상 경고(`UNVERIFIED`=warn)와도 달라야** 한다.
  //   "확인 못 했다"와 "이 값이 뭔지 모른다"는 다른 사실이고, 후자는 계약이 어긋났다는 신호다.
  //   `frontend/README §설계 계약`: 모르는 어휘는 오렌지를 빌리지 않고 전용 톤을 쓴다.
  const normalWarn = ITEM_VIEW.UNVERIFIED.tone;
  for (const s of unknowns) {
    const view = itemView(s);
    if (view.tone === "ok") bad.push(`${s || "(빈문자열)"}→tone=ok (초록 누수)`);
    if (view.tone === normalWarn) bad.push(`${s || "(빈문자열)"}→tone=${view.tone} (정상 경고와 동일)`);
    if (view.tone !== "unknown") bad.push(`${s || "(빈문자열)"}→tone=${view.tone} (전용 톤 아님)`);
    if (!view.badge.includes(s) || !view.badge.startsWith("미확인")) {
      bad.push(`${s || "(빈문자열)"}→badge=${view.badge}`);
    }
  }
  check(
    "itemView 맵 밖 값 6종 — 전용 unknown 톤 + 원문 보존 (초록·정상경고 어느 쪽도 아니다)",
    bad.length === 0,
    bad.length ? bad.join(" / ") : `검사 ${unknowns.length}종 · 예: itemView("PENDING")=${itemView("PENDING").badge} tone=${itemView("PENDING").tone}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-4 — PARTIAL 배너 문구 · 미지 판정 폴백                                    */

{
  const p = VERDICT_VIEW.PARTIAL;
  const unknown = verdictView("MOSTLY_VERIFIED");
  const okCase = VERDICT_VIEW.VERIFIED;
  const unknownTone: string = unknown.tone;
  const partialTone: string = p.tone;
  check(
    "VERDICT_VIEW.PARTIAL — warn + '안전하다는 뜻이 아닙니다' · 미지 판정은 전용 unknown 톤 + 원문",
    p.tone === "warn" &&
      p.headline.includes("안전하다는 뜻이 아닙니다") &&
      okCase.tone === "ok" &&
      // 미지 판정은 `PARTIAL`(정상 경고)과 **같은 톤이면 안 된다** — L1-3 과 같은 이유.
      // 톤을 `string` 으로 넓혀 비교한다: 리터럴끼리 두면 tsc 가 "겹치지 않는 비교"로 막아
      // 단언이 사라지고, 나중에 두 값이 같아져도 아무도 모르게 된다.
      unknownTone === "unknown" &&
      unknownTone !== partialTone &&
      unknown.headline.includes("MOSTLY_VERIFIED"),
    `PARTIAL=${p.tone}:"${p.headline}" · 미지=${unknown.tone}:"${unknown.headline}"`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-5 — 카테고리 9종·순서 고정 (하드코딩 오라클과 대조)                       */

{
  const actual = [...CATEGORIES];
  check(
    "CATEGORIES — 하드코딩 9종과 개수·순서 동일 (04 §9)",
    actual.length === 9 && actual.join("|") === EXPECTED_CATEGORIES.join("|"),
    `${actual.length}종 [${actual.slice(0, 3).join(", ")}…]`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-6 — toRows 는 항목 0건 카테고리도 남긴다 (뮤턴트 ⓒ)                       */

{
  const rows = toRows(fixture());
  const cats: string[] = [];
  for (const r of rows) if (!cats.includes(r.category)) cats.push(r.category);
  const emptyOnes = rows.filter((r) => r.empty);
  const missing = EXPECTED_CATEGORIES.filter((c) => !cats.includes(c));
  check(
    "toRows — 항목 0건 카테고리도 행을 남긴다 (9카테고리 전부 · 순서 유지)",
    cats.length === 9 &&
      missing.length === 0 &&
      cats.join("|") === EXPECTED_CATEGORIES.join("|") &&
      emptyOnes.length === 1 &&
      emptyOnes[0].category === EXPECTED_CATEGORIES[2] &&
      (emptyOnes[0].limit ?? "").length > 0 &&
      emptyOnes[0].tone !== "ok",
    `카테고리 ${cats.length}종 · 빠짐 ${missing.length}건 · 0건 카테고리 행 ${emptyOnes.length}건` +
      ` (${emptyOnes.length ? `${emptyOnes[0].category}/tone=${emptyOnes[0].tone}` : "없음"})`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-7 — 미지 state 는 초록이 안 된다 · 요약에 퍼센트가 없다                    */

{
  const dirty = fixture();
  dirty.categories[0].items.push({
    item: "백엔드가 새 어휘를 보냈다",
    state: "PARTIALLY_VERIFIED",
    evidence: null,
    limit: null,
  });
  dirty.categories[0].items.push({
    item: "state 키 자체가 없다",
    state: undefined as unknown as string,
    evidence: null,
    limit: null,
  });
  const rows = toRows(dirty);
  const strange = rows.filter((r) => r.state !== "VERIFIED" && r.state !== "UNVERIFIED");
  const greenLeak = strange.filter((r) => r.tone === "ok");
  const s = summarize(rows);
  const okText = s.text === `${s.verified}/${s.total} 확인됨`;
  check(
    "미지 state 는 tone='ok' 가 되지 않는다 · summarize 는 'N/M 확인됨' (퍼센트·진행바 없음)",
    strange.length === 2 &&
      greenLeak.length === 0 &&
      okText &&
      !s.text.includes("%") &&
      s.total > s.verified,
    `미지 state ${strange.length}건 · 초록 누수 ${greenLeak.length}건 · summary="${s.text}"`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-8 — auditRows 가 불변식 4종을 **실제로** 잡는다                           */

{
  const clean = auditRows(toRows(fixture()));

  const cases: { label: string; rows: Row[]; want: string }[] = [
    {
      label: "미확인인데 tone=ok",
      rows: nineRows().map((r, i) =>
        i === 0 ? { ...r, state: "UNVERIFIED", tone: "ok" as Tone, limit: "사유", evidence: null } : r
      ),
      want: "[tone]",
    },
    {
      label: "UNVERIFIED 인데 limit 없음",
      rows: nineRows().map((r, i) =>
        i === 0 ? { ...r, state: "UNVERIFIED", tone: "warn" as Tone, limit: null, evidence: null } : r
      ),
      want: "[limit]",
    },
    {
      label: "VERIFIED 인데 evidence 없음",
      rows: nineRows().map((r, i) => (i === 0 ? { ...r, evidence: null } : r)),
      want: "[evidence]",
    },
    {
      label: "카테고리 8종",
      rows: nineRows().slice(0, 8),
      want: "[categories]",
    },
  ];

  const missed = cases.filter((c) => !auditRows(c.rows).some((v) => v.startsWith(c.want)));
  check(
    "auditRows — 정상 입력은 위반 0건 · 불변식 4종 위반을 각각 잡는다",
    clean.length === 0 && missed.length === 0,
    `정상 위반 ${clean.length}건${clean.length ? ` (${clean[0]})` : ""} · ` +
      `못 잡은 뮤턴트 ${missed.length}건${missed.length ? ` (${missed.map((m) => m.label).join(", ")})` : ""}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-9 — 큐 상태 라벨도 같은 원칙 (lib/queueState.ts · MQ-709a 산출, 읽기만)    */

{
  const probes: [string, string][] = [
    ["po", "archived"],
    ["disposal", "approved"],
    // Sprint 10(MQ-1002)이 STATE_LABEL.repair 를 채우기 전까지는 "repair/pending"이 맵 밖이었다.
    // 이제 repair 도 draft·pending·signed·rejected 4종을 알므로, 그 4종 밖의 상태로 같은 축(known
    // kind·unknown state)을 계속 검사한다 — po/archived 와 같은 형태.
    ["repair", "archived"],
    ["unknown_kind", "signed"],
    ["po", ""],
  ];
  const bad: string[] = [];
  for (const [kind, state] of probes) {
    const v = stateView(kind, state);
    if (v.tone === "ok") bad.push(`${kind}/${state}→ok`);
    if (v.known) bad.push(`${kind}/${state}→known=true`);
    if (v.text !== state) bad.push(`${kind}/${state}→text=${v.text}`);
  }
  // Sprint 17(D119, MQ-1712) — po/approved 는 이제 "재무승인대기"(tone: info) 로 바뀌었다.
  // 대조군(맵 안의 값이 정상적으로 tone='ok' 로 떨어지는지 확인하는 축)은 새 상태 머신에서
  // 실제로 "확정 완료"를 뜻하는 finance_approved 로 옮긴다.
  const known = stateView("po", "finance_approved");
  check(
    "stateView — 맵 밖 (kind,state) 5종이 tone='ok' 로 떨어지지 않는다 (known=false + 원문)",
    bad.length === 0 && known.tone === "ok" && known.known,
    bad.length
      ? bad.join(" / ")
      : `검사 ${probes.length}종 전부 warn/known=false · 대조군 po/finance_approved=${known.tone}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-10 — showMetric(null) 은 "0"·""·"양호" 어느 것도 아니다 (D62, MQ-917 / lib/maintValue.ts) */

{
  const noVal = showMetric(null, "일");
  const bad = ["0", "", "양호"];
  check(
    "showMetric(null) — '0'·''·'양호' 어느 것도 반환하지 않는다 (D62)",
    !bad.includes(noVal.text) && noVal.kind === "insufficient",
    `text="${noVal.text}" kind=${noVal.kind}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-11 — showTrend("insufficient_data") 는 kind:'insufficient' (미산출과 구분)             */

{
  const t = showTrend("insufficient_data");
  const notNull = showTrend(null);
  check(
    "showTrend('insufficient_data') — kind='insufficient' · null(미산출)과는 다른 kind",
    t.kind === "insufficient" && t.text !== "" && t.text !== "안정" && notNull.kind !== t.kind,
    `insufficient_data→text="${t.text}" kind=${t.kind} · null→kind=${notNull.kind}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-12 — isHoldVerdict('HOLD')===true 이고 에러/타 판정 문자열로 오분류되지 않는다          */

{
  const held = isHoldVerdict("HOLD");
  const others = ["ERROR", "UNKNOWN", "", "REPAIR_RECOMMENDED", "ROOT_CAUSE_FIRST"];
  const bad = others.filter((s) => isHoldVerdict(s) === true);
  check(
    "isHoldVerdict('HOLD')===true · 에러/타 판정 문자열은 HOLD 로 오분류되지 않는다",
    held === true && bad.length === 0,
    `HOLD=${held} · 오분류 ${bad.length}건${bad.length ? ` (${bad.join(",")})` : ""}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-13 — estimateNotice 는 목업 잔가 입력에 반드시 문자열을 반환한다(고지 누락 불가, D65·D74) */

{
  const withSource = estimateNotice({ source: "법정 기준내용연수 기반 목업 잔가곡선(D74)" });
  const withoutSource = estimateNotice({});
  check(
    "estimateNotice — source 있으면 반드시 문자열(고지 누락 불가) · source 없으면 지어내지 않는다",
    typeof withSource === "string" &&
      withSource.length > 0 &&
      withSource.includes("추정치") &&
      withoutSource === null,
    `source 있음="${withSource}" · source 없음=${withoutSource === null ? "null(정상)" : String(withoutSource)}`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-14 — deadlineStateView 맵 밖 값은 unknown + 원문, OVERDUE ≠ IN_REVIEW_BAND 톤 (MQ-1202) */

{
  const upcoming = deadlineStateView("UPCOMING");
  const reviewBand = deadlineStateView("IN_REVIEW_BAND");
  const overdue = deadlineStateView("OVERDUE");
  const unknowns = ["EXPIRED", "PENDING", "", "upcoming"];
  const bad: string[] = [];
  for (const s of unknowns) {
    const v = deadlineStateView(s);
    if (v.tone === "ok") bad.push(`${s || "(빈문자열)"}→tone=ok (초록 누수)`);
    if (v.tone !== "unknown") bad.push(`${s || "(빈문자열)"}→tone=${v.tone} (전용 톤 아님)`);
    if (!v.label.includes(s)) bad.push(`${s || "(빈문자열)"}→label=${v.label} (원문 미보존)`);
  }
  // 톤을 string 으로 넓혀 비교한다(L1-4 와 같은 이유) — 리터럴끼리 두면 tsc 가 "겹치지 않는
  // 비교"로 막아 단언이 사라지고, 나중에 두 값이 같아져도 아무도 모르게 된다.
  const overdueTone: string = overdue.tone;
  const reviewBandTone: string = reviewBand.tone;
  check(
    "deadlineStateView — 맵 밖 값 4종은 unknown+원문 · OVERDUE(error) ≠ IN_REVIEW_BAND(warn) 톤",
    bad.length === 0 &&
      upcoming.tone === "warn" &&
      reviewBand.tone === "warn" &&
      overdue.tone === "error" &&
      overdueTone !== reviewBandTone,
    bad.length
      ? bad.join(" / ")
      : `UPCOMING=${upcoming.tone} IN_REVIEW_BAND=${reviewBand.tone} OVERDUE=${overdue.tone} · 맵 밖 ${unknowns.length}종 전부 unknown+원문`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-15 — gradeView(null) 은 LOW/ok 로 오분류되지 않는다 · 맵 밖 값도 unknown+원문 (D62, MQ-1202) */

{
  const nullGrade = gradeView(null);
  const low = gradeView("LOW");
  const unknowns = ["low", "CRITICAL", "", "unknown"];
  const bad: string[] = [];
  if (nullGrade.tone === "ok") bad.push("null→tone=ok (초록 누수)");
  if (nullGrade.tone === low.tone) bad.push(`null→tone=${nullGrade.tone} (LOW 와 동일 톤)`);
  if (nullGrade.label === low.label) bad.push(`null→label=${nullGrade.label} (LOW 라벨과 동일)`);
  for (const s of unknowns) {
    const v = gradeView(s);
    if (v.tone === "ok") bad.push(`${s || "(빈문자열)"}→tone=ok (초록 누수)`);
    if (v.tone !== "unknown") bad.push(`${s || "(빈문자열)"}→tone=${v.tone} (전용 톤 아님)`);
    if (!v.label.includes(s)) bad.push(`${s || "(빈문자열)"}→label=${v.label} (원문 미보존)`);
  }
  check(
    "gradeView(null) — LOW/ok 로 오분류되지 않는다(D62) · 맵 밖 값 4종은 unknown+원문",
    bad.length === 0 && nullGrade.tone === "unknown" && low.tone === "ok",
    bad.length
      ? bad.join(" / ")
      : `null→{${nullGrade.label},${nullGrade.tone}} LOW→{${low.label},${low.tone}} · 맵 밖 ${unknowns.length}종 전부 unknown+원문`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-16 — 온보딩: 모르는 상태(프로토타입 키 포함)는 ok 로 떨어지지 않는다 (D87·D145, MQ-1911) */

{
  // 프로토타입 키를 일부러 섞는다 — `x in MAP` 으로 판정하면 이 키들이 「아는 값」으로 새어
  // 라벨 대신 함수가 튀어나온다(리뷰 지적, MQ-1911). 기대값은 여기 독립 하드코딩.
  const unknowns = ["toString", "constructor", "__proto__", "hasOwnProperty", "READY", "promoted", ""];
  const bad: string[] = [];
  const views: [string, (s: string) => { label: string; tone: string; known: boolean } | null][] = [
    ["onboardingBadgeView", onboardingBadgeView],
    ["rowStateView", rowStateView],
    ["safetyStateView", safetyStateView],
  ];
  for (const [name, fn] of views) {
    for (const s of unknowns) {
      const v = fn(s);
      const tag = `${name}(${s || "(빈문자열)"})`;
      if (v === null) {
        bad.push(`${tag}→null (뱃지가 사라짐)`);
        continue;
      }
      if (v.tone === "ok") bad.push(`${tag}→tone=ok (초록 누수)`);
      if (v.tone !== "unknown") bad.push(`${tag}→tone=${String(v.tone)} (전용 톤 아님)`);
      if (v.known !== false) bad.push(`${tag}→known=${String(v.known)}`);
      if (typeof v.label !== "string" || !v.label.includes(s)) bad.push(`${tag}→label=${String(v.label)} (원문 미보존)`);
    }
  }
  // groupStatusView — 행 상태에 모르는 값(프로토타입 키 포함)이 섞이면 ok 도 「대기」도 아니다
  for (const s of unknowns) {
    const g = groupStatusView({
      promoted: false,
      rows: [{ state: s, norms: [{ confidence: "high", flags: [] }], source_flags: [] }],
    });
    const tag = `groupStatusView(row.state=${s || "(빈문자열)"})`;
    if (g.tone === "ok") bad.push(`${tag}→tone=ok (초록 누수)`);
    if (g.tone !== "unknown" || g.key !== "unknown") bad.push(`${tag}→{${g.key},${g.tone}} (unknown 아님)`);
  }
  // 양성 축 — 사람이 확정한 사실만 ok 다. AI 초안(high 정규화만 있는 staged 그룹)은 ok 가 아니다.
  const ready = onboardingBadgeView("ready");
  const promoted = groupStatusView({ promoted: true, rows: [] });
  const draft = groupStatusView({
    promoted: false,
    rows: [{ state: "staged", norms: [{ confidence: "high", flags: [] }], source_flags: [] }],
  });
  const none = onboardingBadgeView("none");
  if (ready?.tone !== "ok") bad.push(`ready→${ready?.tone} (양성 앵커 ok 아님)`);
  if (promoted.tone !== "ok") bad.push(`promoted→${promoted.tone} (양성 앵커 ok 아님)`);
  if (draft.tone === "ok") bad.push("AI 초안(staged·high)→tone=ok (사람 확정과 구분 안 됨, D145)");
  if (none !== null) bad.push(`none→${JSON.stringify(none)} (기존 기종에 뱃지가 붙음)`);
  check(
    "온보딩 뷰 — 미지 값·프로토타입 키 7종 × 4함수는 unknown+원문 · ready/승격만 ok · AI 초안은 ok 아님",
    bad.length === 0,
    bad.length
      ? bad.join(" / ")
      : `미지 ${unknowns.length}종 × 4함수 전부 unknown · ready=${ready?.tone} promoted=${promoted.tone} draft=${draft.tone} none=null`
  );
}

/* -------------------------------------------------------------------------- */
/* L1-17 — A2A status: 프로토타입 키는 실패(error)로도 성공(ok)으로도 분류되지 않는다 (D87, MQ-1911) */

{
  const unknowns = ["toString", "constructor", "__proto__", "valueOf", "OK", ""];
  const bad: string[] = [];
  for (const s of unknowns) {
    const t = a2aStatusTone(s);
    const l = a2aStatusLabel(s);
    if (t !== "unknown") bad.push(`${s || "(빈문자열)"}→tone=${t}`);
    if (typeof l !== "string" || !l.includes(`미상(${s})`)) bad.push(`${s || "(빈문자열)"}→label=${String(l)} (원문 미보존)`);
  }
  const ok = a2aStatusTone("ok");
  const blocked = a2aStatusTone("policy_blocked");
  if (ok !== "ok") bad.push(`ok→${ok} (양성 앵커)`);
  if (blocked !== "error") bad.push(`policy_blocked→${blocked} (양성 앵커)`);
  check(
    "a2aStatusTone/Label — 프로토타입 키 포함 미지 값 6종은 unknown+미상(원문) · ok/policy_blocked 앵커",
    bad.length === 0,
    bad.length ? bad.join(" / ") : `미지 ${unknowns.length}종 전부 unknown · ok=${ok} policy_blocked=${blocked}`
  );
}

/* -------------------------------------------------------------------------- */

console.log(`L1-SUMMARY|${failed === 0 ? "PASS" : "FAIL"}|총 ${n}건 · 실패 ${failed}건`);
if (failed > 0) process.exit(1);
