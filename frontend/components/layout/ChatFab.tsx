"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getPoQueue } from "@/lib/api";
import { roleFromPath } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * 챗 플로팅 버튼 — 정비사 콘솔(`/technician/*`) 어디서든 챗봇(`/technician`)으로
 * 돌아갈 수 있게 해주는 우하단 고정 버튼.
 *
 * 배지 숫자는 "안 읽음 메시지" 가 아니다 — SSE 대화는 저장하지 않으므로(D41) 그런
 * 개념 자체가 없다. 대신 "정비사의 다음 조치를 기다리는 draft 발주 수"(`/api/po?state=draft`
 * 의 실제 길이)로 정직하게 재정의한 값이다.
 *
 * `Shell` 은 `/technician`·`/manager` 공유 레이아웃이라 라우트 이동에도 리마운트되지
 * 않는다 — 따라서 이 컴포넌트의 `useEffect` 는 매니저로 세션을 시작해도 세션당
 * 딱 1회만 실행된다(폴링 없음 요건과 충돌하지 않는다).
 */
export function ChatFab() {
  const pathname = usePathname();
  const [draftCount, setDraftCount] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    getPoQueue("technician", "draft")
      .then((items) => {
        if (alive) setDraftCount(items.length);
      })
      .catch(() => {
        // 실패 시 숫자 0 으로 위장하지 않는다 — 배지를 숨긴다 (D87).
        if (alive) setDraftCount(null);
      });
    return () => {
      alive = false;
    };
  }, []); // Shell 마운트 시 1회만 — pathname 을 deps 에 넣지 않는다(폴링 없음)

  if (roleFromPath(pathname) !== "technician" || pathname === "/technician") return null;

  return (
    <Link
      href="/technician"
      aria-label="진단 챗봇 열기"
      style={sx(
        "position:fixed;right:24px;bottom:24px;z-index:30;width:56px;height:56px;" +
          "border-radius:50%;background:var(--blue);color:#fff;display:flex;" +
          "align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,0,0,.25);" +
          "text-decoration:none;font-size:24px"
      )}
    >
      💬
      {draftCount !== null && draftCount > 0 && (
        <span
          style={sx(
            "position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;padding:0 4px;" +
              "border-radius:9px;background:var(--orange);color:#fff;display:flex;" +
              "align-items:center;justify-content:center;font:700 10px 'JetBrains Mono',monospace"
          )}
        >
          {draftCount}
        </span>
      )}
    </Link>
  );
}
