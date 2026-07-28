"use client";

import { useState } from "react";
import { sx } from "@/lib/sx";
import type { TraceSession } from "@/lib/types";
import { TraceStep } from "./TraceStep";

const TABS = ["실행 로그", "근거 문서", "발주 이력"] as const;

/**
 * 이 프로젝트의 시그니처 화면 — 에이전트가 어떤 도구를 왜 호출했는지 타임라인.
 * 데이터 소스는 SSE tool_call·tool_result 이며 traces 테이블에도 영속된다 (D21·A5).
 */
export function TracePanel({ session }: { session: TraceSession }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("실행 로그");

  return (
    <div style={sx("display:flex;flex-direction:column;background:var(--panel)")}>
      <TraceTabs active={tab} onSelect={setTab} />
      <TraceSessionHeader session={session} />
      <div style={sx("padding:16px;display:flex;flex-direction:column")}>
        {session.steps.map((step, i) => (
          <TraceStep key={step.tool + i} step={step} connector={i < session.steps.length - 1} />
        ))}
      </div>
    </div>
  );
}

function TraceTabs({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (t: (typeof TABS)[number]) => void;
}) {
  return (
    <div style={sx("display:flex;border-bottom:1px solid var(--line)")}>
      {TABS.map((t) => (
        <button
          key={t}
          onClick={() => onSelect(t)}
          style={sx(
            "padding:11px 15px;background:transparent;border:none;cursor:pointer;font-family:'Pretendard';font-size:12px;" +
              (t === active
                ? "font-weight:700;color:var(--ink);border-bottom:2px solid var(--blue-br)"
                : "font-weight:500;color:var(--dim3)")
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

function TraceSessionHeader({ session }: { session: TraceSession }) {
  const accent = session.accent === "orange" ? "var(--orange-tx2)" : "var(--blue-tx2)";
  return (
    <div
      style={sx(
        "padding:15px 16px 10px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--step-line)"
      )}
    >
      <span
        style={sx(
          `font:600 10px 'JetBrains Mono',monospace;letter-spacing:.08em;color:${accent}`
        )}
      >
        {session.label}
      </span>
      {session.replay && (
        // 재생 세션 표식 (D55 — 표식은 읽기만 한다). 회색(--dim2 계열) 고정:
        // 오렌지는 안전·긴급 전용, 파랑은 정상 실행이라 어느 쪽도 빌리지 않는다.
        <span
          style={sx(
            "font:600 9px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2);" +
              "border:1px solid var(--dim3);border-radius:3px;padding:1px 6px;flex-shrink:0"
          )}
        >
          재생 데이터
        </span>
      )}
      <div style={sx("flex:1")} />
      <span style={sx("font:10px 'JetBrains Mono',monospace;color:var(--dim2)")}>
        {session.meta}
      </span>
    </div>
  );
}
