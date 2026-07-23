"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { TracePanel } from "@/components/trace/TracePanel";
import { Button } from "@/components/ui/Button";
import { Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getTrace, type ApiTrace } from "@/lib/api";
import { sx } from "@/lib/sx";
import { toTraceSession } from "@/lib/trace";

/**
 * `/manager/trace/{sessionId}` — 발주 근거 카드의 "실행 로그 전체 보기" 착지점.
 *
 * 화면 B 의 팀장은 대화를 읽지 않는다 (D18). 그래서 근거 카드가 판단의 기본이고,
 * 이 페이지는 "그 근거가 어떤 도구 호출에서 나왔는지"를 확인하고 싶을 때만 들어온다 —
 * 즉 감사(audit) 화면이다. 타임라인 렌더는 화면 A 와 같은 `TracePanel` 을 쓴다 (D21).
 *
 * **역할은 라우트가 결정한다** (frontend/README) — `/manager/*` 이므로 `X-Role: manager`
 * 로 고정 호출한다. 화면에서 역할을 토글하지 않는다.
 *
 * 상태 4종을 모두 그린다. 특히 **`count === 0` 은 에러가 아니다** — 백엔드는 없는 세션에도
 * 200 + `count:0` 을 준다 (D43). 이걸 에러로 취급하면 "아직 도구를 안 부른 세션"과
 * "서버가 죽음"이 같은 화면이 된다.
 */
type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; trace: ApiTrace };

export default function TracePage({ params }: { params: { sessionId: string } }) {
  const sessionId = decodeURIComponent(params.sessionId);
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", trace: await getTrace("manager", sessionId) });
    } catch (e) {
      // 조회 실패를 "빈 세션"으로 뭉개지 않는다 — 데모에서 백엔드가 꺼진 걸 모르게 된다
      setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>실행 로그</span>
          <span style={sx("color:var(--dim2)")}>
            <Mono size={11}>{sessionId}</Mono>
          </span>
          <Spacer />
          <Link href="/manager" style={sx("font:12px 'Pretendard';color:var(--blue-br)")}>
            ← 승인 큐
          </Link>
        </ConsoleHeader>

        {state.kind === "loading" && <Notice>실행 로그를 불러오는 중…</Notice>}

        {state.kind === "error" && (
          <div style={sx("padding:22px 20px;display:flex;flex-direction:column;gap:12px")}>
            <StatusBanner tone="error">
              ⚠ 실행 로그를 불러오지 못했습니다 — {state.message}
            </StatusBanner>
            <div>
              <Button variant="outline" size="sm" onClick={() => void load()}>
                다시 시도
              </Button>
            </div>
          </div>
        )}

        {state.kind === "ready" && state.trace.count === 0 && (
          <Notice>
            이 세션에는 기록된 도구 호출이 없습니다.
            <br />
            <span style={sx("color:var(--dim2)")}>
              아직 진단이 시작되지 않았거나, 세션 ID(<Mono>{sessionId}</Mono>)가 다를 수 있습니다.
            </span>
          </Notice>
        )}

        {state.kind === "ready" && state.trace.count > 0 && (
          <TracePanel session={toTraceSession(state.trace)} />
        )}
      </ConsoleFrame>
    </ScreenStack>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "padding:44px 20px;text-align:center;font:13px/1.7 'Pretendard';color:var(--dim);background:var(--panel)"
      )}
    >
      {children}
    </div>
  );
}
