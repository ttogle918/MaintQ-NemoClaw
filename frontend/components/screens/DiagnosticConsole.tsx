"use client";

import { useEffect, useRef, useState } from "react";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatThread } from "@/components/chat/ChatThread";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { TracePanel } from "@/components/trace/TracePanel";
import { Avatar, Divider, Logo, SelectChip } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getEquipment } from "@/lib/api";
import { CHAT_BY_SCENARIO, type Scenario } from "@/lib/mock/scenarios";
import { TRACE_S1, TRACE_S3 } from "@/lib/mock/trace";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";
import type { TraceSession } from "@/lib/types";
import { useChatStream } from "./useChatStream";

const TRACE_BY_SCENARIO = { s1: TRACE_S1, s3: TRACE_S3 };

/** 세션 ID 가 아직 없는(mount 전) 순간의 자리표시 trace — 하이드레이션 안전용. */
const EMPTY_TRACE: TraceSession = {
  label: "SESSION",
  meta: "이번 턴 0회",
  accent: "blue",
  steps: [],
};

/** 재생 데모의 고정 프롬프트 (`_replay_s1` 은 입력 무관하게 하드코딩 이벤트를 낸다, D55). */
const REPLAY_PROMPT = "iG5A 인버터에 OHt 에러가 떴어";

/**
 * 다른 화면에서 넘어온 진입 상태 (`/technician?prefill=…&equipment=…`, MQ-711).
 * **채워 넣기만** 한다 — 자동 전송하지 않는다.
 */
export interface ConsoleEntry {
  /** 컴포저에 미리 채울 문장 */
  prefill?: string;
  /** 헤더 장비 선택기의 초기값. 목록에 없으면 선택을 비운다(지어내지 않는다) */
  equipmentId?: string;
}

type DiagnosticConsoleProps =
  | { mode: "mock"; scenario: Scenario; onRequestApproval?: (poId: string) => void }
  | {
      mode: "live";
      replay?: "s1";
      entry?: ConsoleEntry;
      onRequestApproval?: (poId: string) => void;
    };

/**
 * 화면 A — 진단 콘솔 (정비사).
 * 좌 채팅 · 우 실행 trace. trace 쪽이 이 제품의 주인공이라 시각적 무게를 뺏기지 않게 둔다.
 *
 * - `mode:"mock"` — 목업 대화(`?scenario=s1|s3`). error_codes 승인 전 S3 를 보여줄 유일한 그림.
 * - `mode:"live"` — 실 SSE 배선. `replay:"s1"` 이면 mount 시 재생 데모를 1회 자동 흘린다.
 */
export function DiagnosticConsole(props: DiagnosticConsoleProps) {
  if (props.mode === "live") {
    return (
      <LiveConsole
        replay={props.replay}
        entry={props.entry}
        onRequestApproval={props.onRequestApproval}
      />
    );
  }
  return <MockConsole scenario={props.scenario} onRequestApproval={props.onRequestApproval} />;
}

/* -------------------------------------------------------------------------- */
/* mock — 기존 화면 보존 (변경 없음)                                            */

function MockConsole({
  scenario,
  onRequestApproval,
}: {
  scenario: Scenario;
  onRequestApproval?: (poId: string) => void;
}) {
  return (
    <ConsoleShell
      header={
        <>
          <SelectChip>라인 · 1번 조립</SelectChip>
          <SelectChip>
            장비 · <Mono size={11}>LS iG5A</Mono>
          </SelectChip>
        </>
      }
      chat={<ChatThread items={CHAT_BY_SCENARIO[scenario]} onRequestApproval={onRequestApproval} />}
      composer={<ChatComposer />}
      trace={<TracePanel session={TRACE_BY_SCENARIO[scenario]} />}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* live — 실 SSE 배선                                                           */

type EquipmentItem = Awaited<ReturnType<typeof getEquipment>>[number];

function LiveConsole({
  replay,
  entry,
  onRequestApproval,
}: {
  replay?: "s1";
  entry?: ConsoleEntry;
  onRequestApproval?: (poId: string) => void;
}) {
  // `Date.now()` 를 초기 렌더에서 바로 쓰면 SSR 패스와 클라이언트 hydration 패스가
  // **서로 다른 시각**을 찍어 세션 ID 가 갈리고, TracePanel 의 "SESSION #…" 텍스트가
  // React hydration mismatch 를 낸다(실측 — 매 `/technician` 라이브 접속마다 재현).
  // 그래서 세션 ID 는 **mount 이후**(useEffect, 클라이언트 전용)에만 만든다 — 그 전까지
  // SSR·최초 클라이언트 렌더가 똑같이 `null` 을 그려 불일치가 생길 값 자체가 없다.
  const [sessionId, setSessionId] = useState<string | null>(null);
  useEffect(() => {
    // 로드마다 새 세션 (ASCII, D36). 재생도 매번 새 세션 — 같은 세션에 재생을 거듭 흘리면
    // seq 가 이어붙어 타임라인이 계속 자란다.
    setSessionId(`S-${Date.now().toString(36)}`);
  }, []);

  if (sessionId === null) {
    return (
      <ConsoleShell
        header={
          <SelectChip>
            장비 · <Mono size={11}>연결 중…</Mono>
          </SelectChip>
        }
        chat={<ChatThread items={[]} onRequestApproval={onRequestApproval} />}
        composer={<ChatComposer disabled />}
        trace={<TracePanel session={EMPTY_TRACE} />}
      />
    );
  }
  return (
    <LiveConsoleReady
      sessionId={sessionId}
      replay={replay}
      entry={entry}
      onRequestApproval={onRequestApproval}
    />
  );
}

function LiveConsoleReady({
  sessionId,
  replay,
  entry,
  onRequestApproval,
}: {
  sessionId: string;
  replay?: "s1";
  entry?: ConsoleEntry;
  onRequestApproval?: (poId: string) => void;
}) {
  const { state, send } = useChatStream(sessionId);

  const [equipment, setEquipment] = useState<EquipmentItem[]>([]);
  const [equipmentId, setEquipmentId] = useState<string | null>(entry?.equipmentId ?? null);
  const autoSentRef = useRef(false);

  // 장비 목록 로드. 실패해도 화면은 뜬다 — 그때는 equipment_id: null 로 보내고 에이전트가
  // 모델 확인 질문을 한다(06_REPO_API §2.1). 기본값을 지어내지 않는다 (D6·D13).
  //
  // 진입 파라미터로 받은 `equipmentId` 는 **목록에 있을 때만** 유지한다. 목록에 없는 값을
  // 들고 있으면 선택기는 빈칸을 보여 주는데 요청은 그 ID 로 나가서, 화면과 요청이 어긋난다.
  const entryEquipmentId = entry?.equipmentId;
  useEffect(() => {
    let alive = true;
    getEquipment()
      .then((items) => {
        if (!alive) return;
        setEquipment(items);
        if (entryEquipmentId && !items.some((i) => i.equipment_id === entryEquipmentId)) {
          setEquipmentId(null);
        }
      })
      .catch(() => {
        if (!alive) return;
        setEquipment([]);
        if (entryEquipmentId) setEquipmentId(null);
      });
    return () => {
      alive = false;
    };
  }, [entryEquipmentId]);

  // 재생 자동 send: mount 시 1회. StrictMode 이중 mount 가드(useRef) — POST 2회 방지.
  useEffect(() => {
    if (!replay || autoSentRef.current) return;
    autoSentRef.current = true;
    send(REPLAY_PROMPT, null, replay);
  }, [replay, send]);

  return (
    <ConsoleShell
      header={
        replay ? (
          <SelectChip>
            장비 · <Mono size={11}>재생 데모</Mono>
          </SelectChip>
        ) : (
          <EquipmentSelect
            equipment={equipment}
            value={equipmentId}
            onChange={setEquipmentId}
            disabled={state.streaming}
          />
        )
      }
      chat={
        <>
          {state.error && (
            <StatusBanner tone="error">
              백엔드 응답을 받지 못했습니다 — <Mono>{state.error}</Mono>
            </StatusBanner>
          )}
          <ChatThread items={state.items} onRequestApproval={onRequestApproval} />
        </>
      }
      composer={
        <ChatComposer
          onSend={(text) => send(text, equipmentId)}
          disabled={state.streaming}
          // 채워만 둔다 — 전송은 사용자가 누른다 (자동 전송 금지)
          initialText={entry?.prefill}
        />
      }
      trace={<TracePanel session={state.trace} />}
    />
  );
}

/**
 * 장비 선택기 — `GET /api/equipment` 결과로 채운다. 값이 없으면 placeholder 만 두고 null 을
 * 유지한다(기본값 지어내기 금지). 선택 전 send 는 equipment_id: null 로 나간다.
 */
function EquipmentSelect({
  equipment,
  value,
  onChange,
  disabled,
}: {
  equipment: EquipmentItem[];
  value: string | null;
  onChange: (id: string | null) => void;
  disabled?: boolean;
}) {
  return (
    <span
      style={sx(
        "border:1px solid var(--line2);border-radius:14px;padding:2px 6px 2px 11px;" +
          "font:12px 'Pretendard';color:var(--ink2);background:var(--raise);display:inline-flex;align-items:center;gap:4px"
      )}
    >
      장비 ·
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        aria-label="장비 선택"
        style={sx(
          "border:none;outline:none;background:transparent;font:12px 'JetBrains Mono';color:var(--ink);" +
            "cursor:pointer;max-width:220px" +
            (disabled ? ";opacity:.55;cursor:not-allowed" : "")
        )}
      >
        <option value="">장비 선택…</option>
        {equipment.map((eq) => (
          <option key={eq.equipment_id} value={eq.equipment_id}>
            {eq.equipment_id} · {eq.model}
          </option>
        ))}
      </select>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* 공통 셸 — mock·live 가 같은 프레임을 쓴다                                     */

function ConsoleShell({
  header,
  chat,
  composer,
  trace,
}: {
  header: React.ReactNode;
  chat: React.ReactNode;
  composer: React.ReactNode;
  trace: React.ReactNode;
}) {
  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          {header}
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            정비사 {ROLE_USER_NAME.technician}
          </span>
          <Avatar />
        </ConsoleHeader>

        <div style={sx("display:grid;grid-template-columns:1.25fr 1fr;min-height:580px")}>
          <div style={sx("display:flex;flex-direction:column;border-right:1px solid var(--line)")}>
            <div style={sx("flex:1;padding:16px;display:flex;flex-direction:column;gap:12px")}>
              {chat}
            </div>
            {composer}
          </div>

          {trace}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
