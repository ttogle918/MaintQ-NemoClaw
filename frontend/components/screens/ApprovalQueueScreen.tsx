"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { DecisionDetail } from "@/components/queue/DecisionDetail";
import { EmptyQueue } from "@/components/queue/EmptyQueue";
import { PoDetail } from "@/components/queue/PoDetail";
import { QueueList } from "@/components/queue/QueueList";
import { RepairDetail } from "@/components/queue/RepairDetail";
import { StatusLegend } from "@/components/queue/StatusLegend";
import { KindBadge, StateBadge } from "@/components/ui/Badge";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  approvePo,
  extractDetail,
  financeApprovePo,
  financeRejectPo,
  getApprovals,
  getDecision,
  getPo,
  getRepair,
  rejectPo,
  type ApiApproval,
  type ApiDecision,
  type ApiPo,
  type ApiRepair,
} from "@/lib/api";
import { toEvidenceEntries, toPoQueueEntry, toQueueEntry, toQuotes } from "@/lib/mappers";
import { EVIDENCE_PO_0117, PENDING, QUOTES_PO_0117, RECENT } from "@/lib/mock/queue";
import {
  getManagerIdentity,
  MANAGER_IDENTITIES,
  MANAGER_IDENTITY_CHANGE_EVENT,
} from "@/lib/role";
import { sx } from "@/lib/sx";
import type { QueueEntry } from "@/lib/types";

type Source = "loading" | "live" | "mock";

/**
 * 화면 B — 통합 승인 큐 (팀장).
 * 승인은 채팅 밖 전용 화면에서 한다 — 채팅에선 결재가 흘러가버린다 (D18).
 *
 * 목록은 `GET /api/approvals` (D85) 로 **발주서·처분서·수리 증빙을 한 큐**에 놓는다.
 * 상세는 `kind` 로 갈린다 — `po` → `PoDetail`(계약 무변경) · `disposal` → `DecisionDetail` ·
 * `repair` → `RepairDetail`(Sprint 10, MQ-1002).
 *
 * 백엔드가 꺼져 있으면 목업으로 떨어지되 **배너로 명시**한다.
 * 조용히 목업을 보여주면 데모에서 "동작한다"는 오해를 만든다.
 *
 * `focus="finance"`(신규, 계정 선택 화면이 재무담당을 보낼 때)는 같은 데이터·같은
 * 컴포넌트를 재사용하되 **일반 승인 대기 섹션을 숨기고 재무 승인 대기를 기본 선택**한다 —
 * 재무담당이 이 화면에 들어오면 자기 일(재무 승인)이 바로 보이게 하려는 것뿐이지,
 * 데이터 자체를 다르게 조회하지 않는다(권한은 여전히 백엔드 department 체크가 진짜로 막는다,
 * D119 — 이 prop 은 UI 편의고 보안 경계가 아니다).
 */
export function ApprovalQueueScreen({
  selectedId,
  focus = "all",
}: {
  selectedId?: string;
  focus?: "all" | "finance";
}) {
  const [source, setSource] = useState<Source>("loading");
  const [pending, setPending] = useState<ApiApproval[]>([]);
  /** 재무 승인 대기(po kind 로 한정) — "최근 처리" 4건 슬라이스와는 역할이 다르다 (Sprint 17) */
  const [financePending, setFinancePending] = useState<ApiApproval[]>([]);
  const [recent, setRecent] = useState<ApiApproval[]>([]);
  /** 선택된 항목 (라이브). 큐 목록 밖의 딥링크도 여기 들어온다 */
  const [selected, setSelected] = useState<QueueEntry | null>(null);
  /** 발주 상세 — `kind === "po"` 일 때만 채워진다 */
  const [detail, setDetail] = useState<ApiPo | null>(null);
  /** 처분 상세 — `kind === "disposal"` 일 때만 채워진다 (MQ-709b) */
  const [decision, setDecision] = useState<ApiDecision | null>(null);
  /** 수리 증빙 상세 — `kind === "repair"` 일 때만 채워진다 (MQ-1002) */
  const [repair, setRepair] = useState<ApiRepair | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  /**
   * 현재 매니저 신원(헤더 라벨·`isFinanceApprover` 계산에 씀). 렌더 중 직접
   * `getManagerIdentity()`를 부르지 않는다 — SSR 은 `window` 부재로 항상 배열 0번째를
   * 내는데, hydration 중인 클라이언트 첫 렌더는 즉시 localStorage 를 읽어 값이 달라질 수
   * 있어(예: 이전에 재무담당을 선택해 둔 상태) hydration mismatch 로 전체 트리가 클라이언트
   * 재렌더로 강등된다(실측: 2026-08-24 QA). SSR-안전 기본값(배열 0번째)으로 초기화하고,
   * 마운트 후 `useEffect`에서 실제 값으로 동기화 — `ManagerIdentitySwitch`(형제 컴포넌트,
   * AppBar)가 전환 시 쏘는 이벤트도 같은 effect 가 구독해 반영한다(전환 직후 새로고침
   * 없이도 반영되게 하는 수정, 같은 QA에서 함께 발견됨).
   */
  const [managerIdentity, setManagerIdentityState] = useState(MANAGER_IDENTITIES[0]);
  const [missing, setMissing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // 종결 어휘가 종류마다 다르다 — 발주는 `approved`, 처분은 `signed` 다.
      // 한 어휘로 정규화하지 않기로 한 계약(D85)의 대가로 조회가 한 번 더 필요하다.
      // ⛔ 여기서 `approved` 를 처분에도 쓰지 말 것 — 서명은 다른 사건이다.
      // ⛔ D119(Sprint 17) 이후 po 의 `approved` 는 더 이상 종결이 아니다(재무 승인 대기) —
      // "최근 처리" 목록에 넣지 않는다. `financePending` 섹션이 이미 그 항목을 보여준다.
      const [p, financeApproved, signed, rejected] = await Promise.all([
        getApprovals("manager", "pending"),
        getApprovals("manager", "approved", "po"), // 재무 승인 대기 (po kind 로 한정)
        getApprovals("manager", "signed"),
        getApprovals("manager", "rejected"),
      ]);
      const done = [...signed, ...rejected].slice(0, 4);
      setPending(p);
      setFinancePending(financeApproved);
      setRecent(done);

      const found = selectedId
        ? [...p, ...financeApproved, ...done].find((i) => i.id === selectedId)
        : null;

      if (selectedId && !found) {
        // 큐 4목록 밖의 발주(예: 아직 `draft`) 딥링크. `/api/po` 로 직접 확인한다 —
        // 여기서 그냥 첫 항목으로 미끄러지면 **다른 발주의 헤더 위에 이 발주의 근거**가
        // 렌더된다(승인 화면에서 가장 위험한 오표시다).
        try {
          const direct = await getPo("manager", selectedId);
          setSelected(toPoQueueEntry(direct));
          setDetail(direct);
          setDecision(null);
          setRepair(null);
          setMissing(null);
          setSource("live");
          return;
        } catch {
          // 이 ID 의 발주가 없는 것이다 — 수리 증빙일 수 있으니 이어서 확인한다.
          // `po` 뿐 아니라 `repair` 도 큐 4목록 밖 상태(`draft`)로 존재할 수 있어 같은 위험이 있다.
        }
        try {
          const directRepair = await getRepair("manager", selectedId);
          setSelected(toRepairQueueEntry(directRepair));
          setDetail(null);
          setDecision(null);
          setRepair(directRepair);
          setMissing(null);
          setSource("live");
          return;
        } catch {
          // 백엔드는 살아 있는데 그 ID 가 없는 것이다 — "목업 모드"라고 말하면 거짓말이다
          setMissing(`요청한 항목을 큐에서 찾을 수 없습니다 — ${selectedId}`);
        }
      }

      // focus="finance"면 기본 선택도 재무 승인 대기 첫 건이다 — 그래야 들어오자마자
      // 자기가 처리할 항목이 바로 열린다. `found`(딥링크)가 있으면 그게 항상 우선이다.
      const primaryList = focus === "finance" ? financeApproved : p;
      const target = found ?? primaryList[0] ?? null;
      setSelected(target ? toQueueEntry(target) : null);
      // 종류별 상세는 각자의 경로에서 온다 — `/api/approvals` 는 목록 전용이다 (D85)
      setDetail(target?.kind === "po" ? await getPo("manager", target.id) : null);
      setDecision(
        target?.kind === "disposal" ? await getDecision("manager", target.id) : null
      );
      setRepair(target?.kind === "repair" ? await getRepair("manager", target.id) : null);
      if (found || !selectedId) setMissing(null);
      setSource("live");
    } catch {
      setSource("mock");
    }
  }, [selectedId, focus]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const syncIdentity = () => setManagerIdentityState(getManagerIdentity());
    syncIdentity(); // 마운트 직후(= hydration 완료 후) 실제 localStorage 값으로 1회 동기화
    window.addEventListener(MANAGER_IDENTITY_CHANGE_EVENT, syncIdentity);
    return () => window.removeEventListener(MANAGER_IDENTITY_CHANGE_EVENT, syncIdentity);
  }, []);

  async function decide(action: "approve" | "reject", reason?: string) {
    if (!detail) return;
    try {
      const updated =
        action === "approve"
          ? await approvePo(detail.po_id)
          : await rejectPo(detail.po_id, reason ?? "");
      setNotice(
        `${updated.po_id} ${action === "approve" ? "승인" : "반려"} 완료 — ${updated.state}`
      );
      await load();
    } catch (e) {
      // 403(권한)·409(순서)·422(사유 누락)를 구분해 보여준다 — 이게 D38 의 요점
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    }
  }

  async function decideFinance(action: "approve" | "reject", reason?: string) {
    if (!detail) return;
    try {
      const updated =
        action === "approve"
          ? await financeApprovePo(detail.po_id)
          : await financeRejectPo(detail.po_id, reason ?? "");
      setNotice(
        `${updated.po_id} 재무 ${action === "approve" ? "승인" : "반려"} 완료 — ${updated.state}`
      );
      await load();
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    }
  }

  const live = source === "live";
  const pendingEntries = live ? pending.map(toQueueEntry) : PENDING;
  const financePendingEntries = live ? financePending.map(toQueueEntry) : [];
  const recentEntries = live ? recent.map(toQueueEntry) : RECENT;
  const chosen = live
    ? selected
    : (pendingEntries.find((e) => e.id === selectedId) ?? pendingEntries[0] ?? null);
  const headerLabel = focus === "finance" ? "재무 승인 대기" : "승인 대기";
  const headerCount = focus === "finance" ? financePendingEntries.length : pendingEntries.length;

  return (
    <ScreenStack>
      {source === "mock" && (
        <StatusBanner tone="warn">
          ⚠ 백엔드에 연결하지 못했습니다 — <b>목업 데이터</b>를 표시 중입니다. 승인·반려는 저장되지
          않습니다. (<code>uv run uvicorn backend.main:app --port 8000</code>)
        </StatusBanner>
      )}
      {missing && <StatusBanner tone="warn">⚠ {missing}</StatusBanner>}
      {notice && <StatusBanner tone="info">{notice}</StatusBanner>}

      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>
            {headerLabel} <span style={sx("color:var(--orange-tx)")}>({headerCount})</span>
          </span>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            {managerIdentity.label}
          </span>
          <Avatar />
        </ConsoleHeader>

        {chosen ? (
          <div style={sx("display:grid;grid-template-columns:280px 1fr;min-height:560px")}>
            <QueueList
              pending={pendingEntries}
              financePending={financePendingEntries}
              recent={recentEntries}
              selectedId={chosen.id}
              showPending={focus !== "finance"}
            />
            {chosen.kind === "po" ? (
              <PoDetail
                entry={chosen}
                evidence={live && detail ? toEvidenceEntries(detail) : EVIDENCE_PO_0117}
                quotes={live && detail ? toQuotes(detail) : QUOTES_PO_0117}
                documentsPreview={live && detail ? detail.documents_preview : undefined}
                onApprove={live ? () => void decide("approve") : undefined}
                onReject={live ? (reason) => void decide("reject", reason) : undefined}
                isFinanceApprover={managerIdentity.department === "finance"}
                onFinanceApprove={live ? () => void decideFinance("approve") : undefined}
                onFinanceReject={live ? (reason) => void decideFinance("reject", reason) : undefined}
              />
            ) : chosen.kind === "disposal" && live && decision ? (
              <DecisionDetail
                decision={decision}
                onUpdated={(updated) => {
                  setDecision(updated);
                  setNotice(`${updated.decision_id} — 상태 ${updated.state}`);
                  // 목록 재조회. 선택은 큐의 기존 규칙을 따른다(발주 승인 뒤와 같은 동작) —
                  // 서명한 건을 계속 보려면 `/manager/decision/{id}` 딥링크가 그 자리다.
                  void load();
                }}
                onReload={() => void load()}
              />
            ) : chosen.kind === "repair" && live && repair ? (
              <RepairDetail
                repairId={repair.repair_id}
                onUpdated={(updated) => {
                  setRepair(updated);
                  setNotice(`${updated.repair_id} — 상태 ${updated.state}`);
                  void load();
                }}
              />
            ) : (
              <PendingImplementationDetail entry={chosen} />
            )}
          </div>
        ) : (
          <EmptyQueue />
        )}
      </ConsoleFrame>

      <StatusLegend />
    </ScreenStack>
  );
}

/**
 * 상세를 그릴 수 없는 자리.
 *
 * MQ-1002 이후로는 상세 화면이 아예 없는 종류가 없다(`po`·`disposal`·`repair` 모두 상세를
 * 갖는다) — 남는 경우는 백엔드에 연결되지 않아 `GET /api/decisions/{id}`·`GET /api/repairs/{id}`
 * 를 못 읽었을 때뿐이다. **숨기지 않고 "없다"고 말한다.** 큐에서 항목을 지우면 승인 대기
 * 건수가 거짓이 되고, 빈 화면을 주면 사용자는 로딩 실패로 읽는다.
 *
 * ⛔ 판정(`verdict`)을 여기서 해석하지 않는다 — 값이 있으면 원문 그대로 보여줄 뿐이다.
 *   "BLOCKED 는 이런 뜻입니다" 같은 요약은 `DecisionDetail` 의 해소 경로 목록이 할 일이다.
 */
function PendingImplementationDetail({ entry }: { entry: QueueEntry }) {
  const when =
    entry.kind === "disposal"
      ? "처분 상세는 백엔드(GET /api/decisions/{id})에서 옵니다 — 지금은 그 응답을 읽지 못했습니다."
      : entry.kind === "repair"
        ? "수리 증빙 상세는 백엔드(GET /api/repairs/{id})에서 옵니다 — 지금은 그 응답을 읽지 못했습니다."
        : "이 종류의 상세 화면은 다음 스프린트에서 붙습니다.";

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px;gap:12px")}>
      <div style={sx("display:flex;align-items:center;gap:9px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{entry.id}</Mono> {entry.title}
        </span>
        <KindBadge kind={entry.kind} size={10} />
        <StateBadge kind={entry.kind} state={entry.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {entry.meta}
        </span>
      </div>

      {/* verdict 가 null 이면 이 영역은 아예 만들지 않는다 — 발주에는 판정이 없다 */}
      {entry.verdict && (
        <div
          style={sx(
            "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:7px;" +
              "padding:10px 12px;font:12px/1.6 'Pretendard';color:var(--saf-cite-tx)"
          )}
        >
          판정 <Mono size={12}>{entry.verdict}</Mono>
          {entry.requiresOverride === true &&
            " — 우회(override) 없이는 서명할 수 없습니다. 사유와 서명자가 기록됩니다."}
        </div>
      )}

      <div
        style={sx(
          "border:1px dashed var(--line2);border-radius:7px;padding:14px 16px;" +
            "font:12.5px/1.7 'Pretendard';color:var(--dim)"
        )}
      >
        <b style={sx("color:var(--ink2)")}>상세 화면이 아직 없습니다.</b>
        <br />
        {when} 지금 보이는 것은 큐 항목이 실어 온 값 그대로이며, 여기서 서명·반려할 수 없습니다.
      </div>
    </div>
  );
}

/**
 * `GET /api/repairs/{id}` 상세 → 큐 한 줄.
 *
 * `toPoQueueEntry` 와 같은 이유로 존재한다 — 큐 4목록(pending·approved/signed·rejected) 밖의
 * 수리 증빙(예: 아직 `draft`)을 딥링크로 열었을 때 헤더 자리를 채우는 최소 표기다.
 * `RepairDetail` 이 `repairId` 로 상세를 다시 조회하므로, 여기서는 `chosen.kind === "repair"`
 * 판별과 배지 표시에 필요한 값만 채운다 — `urgency`·`verdict`·`requiresOverride` 는 수리
 * 증빙에 없는 개념이라 `null` 그대로 둔다(D62 — 없는 사실을 채우지 않는다).
 */
function toRepairQueueEntry(r: ApiRepair): QueueEntry {
  return {
    kind: "repair",
    id: r.repair_id,
    title: `${r.equipment_id}${r.work_type ? ` · ${r.work_type}` : ""}`,
    urgency: null,
    state: r.state,
    meta: r.requested_by_name || r.performed_by_name || "",
    // 이 엔트리는 큐 4목록 밖(예: `draft`) 딥링크의 헤더 표기용일 뿐, `QueueList` 로 렌더되지
    // 않는다 — 그래서 `detailHref` 를 채우지 않는다. 목록에 실제로 뜨는 pending/recent 엔트리의
    // 링크는 `toQueueEntry`(mappers.ts)가 만들고, 전용 라우트 자체는 이제 존재한다
    // (`/manager/repair/{id}`, Sprint 10 — `queueState.detailHref` 참고).
    detailHref: null,
    verdict: null,
    requiresOverride: null,
  };
}
