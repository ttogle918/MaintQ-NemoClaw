"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { initialState, runChatTurn, type ChatStreamState } from "@/lib/chatStream";

/**
 * 화면 A 라이브 배선용 React 훅 (MQ-405).
 *
 * `lib/chatStream` 의 순수 리듀서·fetch 러너를 React 상태에 얹는다. 리듀싱·페어링·인용 조립은
 * 전부 `runChatTurn` 이 하고, 이 훅은 (1) 상태 보관 (2) AbortController 수명 관리 (3) 스트리밍
 * 중 중복 send 차단만 한다. **user 버블은 `runChatTurn`(seedTurn)이 이미 심으므로 여기서
 * 재삽입하지 않는다** (Stage 2 인계 사항). 소비자는 공개 4필드(items·trace·streaming·error)만
 * 읽는다 — `_ctx` 는 내부 필드다.
 *
 * ## 언마운트 abort 와 StrictMode 이중 mount (deferred abort)
 * 진행 중 스트림은 언마운트 시 abort 해야 한다(라우트 이동 시 콘솔 에러 0 · D42 취소 안전).
 * 그런데 dev StrictMode 는 mount→unmount→mount 를 **동기로** 흉내 낸다. 여기서 cleanup 이
 * 곧바로 abort 를 때리면, 방금 시작한(그리고 재생 데모라면 유일한) 턴이 끊긴 채 재-mount 에서
 * 가드에 막혀 다시 시작되지 못한다. 그래서 abort 를 `setTimeout(0)` 매크로태스크로 미루고,
 * 재-mount setup 이 같은 tick 안에 타이머를 취소한다 → 팬텀 언마운트는 abort 를 삼키고, 실제
 * 라우트 이탈만 abort 가 발화한다. (POST 중복은 아래 `streaming` 가드 + 소비자의 auto-send
 * useRef 가드로 막는다 — 팬텀 재-mount 때 첫 POST 가 살아 streaming 이라 두 번째가 차단된다.)
 */
export function useChatStream(sessionId: string): {
  state: ChatStreamState;
  send: (message: string, equipmentId: string | null, replay?: "s1") => void;
} {
  const [state, setState] = useState<ChatStreamState>(() => initialState(sessionId));

  const abortRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  const abortTimerRef = useRef<number | null>(null);

  useEffect(() => {
    // 재-mount setup: 팬텀 언마운트가 예약한 abort 타이머를 취소한다.
    if (abortTimerRef.current !== null) {
      window.clearTimeout(abortTimerRef.current);
      abortTimerRef.current = null;
    }
    return () => {
      // 언마운트 cleanup: abort 를 한 tick 미룬다. StrictMode 팬텀이면 위 setup 이 곧 취소한다.
      abortTimerRef.current = window.setTimeout(() => {
        abortRef.current?.abort();
      }, 0);
    };
  }, []);

  const send = useCallback(
    (message: string, equipmentId: string | null, replay?: "s1") => {
      if (streamingRef.current) return; // 스트리밍 중 send 무시
      streamingRef.current = true;
      const controller = new AbortController();
      abortRef.current = controller;
      void runChatTurn({
        sessionId,
        message,
        equipmentId,
        replay,
        signal: controller.signal,
        onState: setState,
      }).finally(() => {
        streamingRef.current = false;
      });
    },
    [sessionId]
  );

  return { state, send };
}
