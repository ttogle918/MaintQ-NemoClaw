"use client";

import { useEffect, useState } from "react";
import { getA2aHistory, type ApiA2aHistoryItem } from "@/lib/api";
import { a2aStatusTone, skillView, type Tone } from "@/lib/a2a";
import { sx } from "@/lib/sx";
import { CardHead, CardShell } from "./CardShell";

/**
 * 채팅 실시간 A2A 파트너 도구 결과 카드 (MQ-1607, D113·D114).
 *
 * SSE `tool_result` 는 상관관계 키(`chainId`)만 흘리고, 구조화된 원문(약관 근거·대출
 * 판정)은 여기서 `GET /api/a2a/history` 를 별도로 열어 채운다 — `lib/chatStream.ts`
 * 의 `a2a_result` 아이템은 얇은(thin) 상태 그대로다.
 *
 * ⛔ `status`·`verdict` 문자열을 직접 비교해 색을 정하지 않는다 — 톤은 전부
 *   `a2aStatusTone`/`skillView`(`lib/a2a.ts`) 경유로만 정한다 (D87).
 * ⛔ InsuQ/FinAllQ 응답을 추측·요약해서 지어내지 않는다 — 있는 필드만 그대로 보여준다 (D9).
 */

type A2aSkill = "search_insurance_clause" | "assess_equipment_loan";

/** MCP 도구명 → A2A 스킬 슬러그(`lib/a2a.ts::skillView` 키). 라벨은 여기서 새로 짓지
 *  않고 `skillView` 를 그대로 통과시킨다. */
const TOOL_SKILL: Record<A2aSkill, string> = {
  search_insurance_clause: "lookup-clause",
  assess_equipment_loan: "assess-loan",
};

/** `status !== "ok"` 이거나 `chainId` 가 없어 이력 fetch 자체를 하지 않는 경로의 고정
 *  문구(스펙 원문 그대로) — `assess_equipment_loan` 은 오늘 이게 기본 경로다(status.html
 *  실측). 이건 MaintQ 결함이 아니라 파트너 쪽 상태라 톤도 `unknown`(중립)을 쓴다. */
const UNAVAILABLE_TEXT: Record<A2aSkill, string> = {
  search_insurance_clause: "InsuQ 로부터 확답을 받지 못했습니다",
  assess_equipment_loan: "FinAllQ 사전판정을 지금은 확인할 수 없습니다 — 파트너 연동 준비 중",
};

const LOADING_TEXT: Record<A2aSkill, string> = {
  search_insurance_clause: "InsuQ 응답 확인 중…",
  assess_equipment_loan: "FinAllQ 응답 확인 중…",
};

/** `assess-loan` 응답에서 "지어내지 않고 나열"할 때 제외할 알려진 메타 키. */
const LOAN_META_KEYS = new Set(["status", "request_chain_id", "task_id"]);

const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--blue-tx)",
  warn: "var(--orange-tx)",
  error: "var(--error-tx)",
  unknown: "var(--dim)",
};

type FetchState =
  | { status: "loading" }
  | { status: "ok"; item: ApiA2aHistoryItem | null }
  | { status: "error"; message: string };

export function A2aResultCard({
  skill,
  chainId,
  status,
}: {
  skill: A2aSkill;
  chainId: string | null;
  status: string;
}) {
  const shouldFetch = status === "ok" && chainId !== null;
  const [fetchState, setFetchState] = useState<FetchState>({ status: "loading" });

  useEffect(() => {
    if (!shouldFetch || !chainId) return;
    let alive = true;
    setFetchState({ status: "loading" });
    getA2aHistory("technician", { chainId })
      .then((res) => {
        if (!alive) return;
        setFetchState({ status: "ok", item: res.items[0] ?? null });
      })
      .catch(() => {
        if (!alive) return;
        setFetchState({
          status: "error",
          message: "상세를 불러오지 못했습니다 — 백엔드에 연결하지 못했습니다",
        });
      });
    return () => {
      alive = false;
    };
    // chainId 가 바뀌는 경우는 실제로 없다(아이템 생성 시점에 고정) — skill/shouldFetch 도
    // 마찬가지. 명시적으로 의존성에 둬서 재조회 조건을 숨기지 않는다.
  }, [shouldFetch, chainId]);

  // 이력 fetch 를 아예 하지 않는 경로 — 스킬별 고정 문구, 중립 톤.
  if (!shouldFetch) {
    return (
      <Shell title={skillView(TOOL_SKILL[skill]).label} tone="unknown">
        <Line color="var(--ink2)">{UNAVAILABLE_TEXT[skill]}</Line>
      </Shell>
    );
  }

  if (fetchState.status === "loading") {
    return (
      <Shell title={skillView(TOOL_SKILL[skill]).label} tone="unknown">
        <Line color="var(--dim)">{LOADING_TEXT[skill]}</Line>
      </Shell>
    );
  }

  if (fetchState.status === "error") {
    return (
      <Shell title={skillView(TOOL_SKILL[skill]).label} tone="error">
        <Line color="var(--error-tx)">{fetchState.message}</Line>
      </Shell>
    );
  }

  const item = fetchState.item;
  if (!item) {
    return (
      <Shell title={skillView(TOOL_SKILL[skill]).label} tone="unknown">
        <Line color="var(--ink2)">상세를 불러오지 못했습니다</Line>
      </Shell>
    );
  }

  return (
    <Shell title={skillView(item.skill).label} tone={a2aStatusTone(item.status)}>
      {item.skill === "lookup-clause" ? (
        <LookupClauseBody response={item.response} />
      ) : item.skill === "assess-loan" ? (
        <AssessLoanBody response={item.response} />
      ) : (
        <Line color="var(--ink2)">{item.status ?? "(상태 없음)"}</Line>
      )}
    </Shell>
  );
}

function Shell({
  title,
  tone,
  children,
}: {
  title: string;
  tone: Tone;
  children: React.ReactNode;
}) {
  return (
    <CardShell>
      <CardHead title={title} right={<ToneDot tone={tone} />} />
      <div style={sx("padding:12px 13px;display:flex;flex-direction:column;gap:8px")}>
        {children}
      </div>
    </CardShell>
  );
}

/** 상태 점 — 색은 `a2aStatusTone`/`skillView` 가 이미 정한 `Tone` 값만 옮긴다 (D87). */
function ToneDot({ tone }: { tone: Tone }) {
  return (
    <span
      title={tone}
      style={sx(`width:8px;height:8px;border-radius:50%;background:${TONE_COLOR[tone]}`)}
    />
  );
}

function Line({ color, children }: { color: string; children: React.ReactNode }) {
  return <span style={sx(`font:12px/1.5 'Pretendard';color:${color}`)}>{children}</span>;
}

/** `lookup-clause` 응답 — `answer`(문단)·`verdict`(원문 그대로 텍스트, InsuQ 어휘라 색으로
 *  판단하지 않는다)·`evidence`(문자열 목록). 없는 필드는 지어내지 않고 생략한다. */
function LookupClauseBody({ response }: { response: Record<string, unknown> | null }) {
  const answer = typeof response?.answer === "string" ? response.answer : null;
  const verdict = typeof response?.verdict === "string" ? response.verdict : null;
  const evidence = Array.isArray(response?.evidence)
    ? response!.evidence.filter((e): e is string => typeof e === "string")
    : null;

  if (!answer && !verdict && (!evidence || evidence.length === 0)) {
    return <Line color="var(--ink2)">InsuQ 응답 형식이 아직 확인되지 않았습니다</Line>;
  }

  return (
    <>
      {verdict && (
        <span
          style={sx(
            "align-self:flex-start;font:700 11px 'JetBrains Mono',monospace;color:var(--ink2);" +
              "border:1px solid var(--line2);border-radius:3px;padding:2px 6px"
          )}
        >
          {verdict}
        </span>
      )}
      {answer && (
        <p style={sx("margin:0;font:12px/1.6 'Pretendard';color:var(--ink)")}>{answer}</p>
      )}
      {evidence && evidence.length > 0 && (
        <ul style={sx("margin:0;padding-left:16px;font:11px/1.6 'Pretendard';color:var(--dim)")}>
          {evidence.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </>
  );
}

/** `assess-loan` 응답 — 알려진 메타 키(`status`·`request_chain_id`·`task_id`) 제외한
 *  나머지를 `label: value` 로 나열한다. 구조를 모르므로 지어내지 않고 있는 값만 쓴다 (D76). */
function AssessLoanBody({ response }: { response: Record<string, unknown> | null }) {
  const entries = response ? Object.entries(response).filter(([k]) => !LOAN_META_KEYS.has(k)) : [];

  if (entries.length === 0) {
    return <Line color="var(--ink2)">FinAllQ 응답 형식이 아직 확인되지 않았습니다</Line>;
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:4px")}>
      {entries.map(([label, value]) => (
        <div key={label} style={sx("display:flex;justify-content:space-between;gap:8px")}>
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{label}</span>
          <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--ink2)")}>
            {formatValue(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}
