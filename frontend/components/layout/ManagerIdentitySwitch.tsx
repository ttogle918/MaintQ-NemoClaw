"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { sx } from "@/lib/sx";
import {
  getManagerIdentity,
  MANAGER_IDENTITIES,
  roleFromPath,
  setManagerIdentity,
} from "@/lib/role";

/**
 * 재무부 신원 전환 (Sprint 17, D119) — `/manager` 화면 안에서 정비팀장/재무담당을
 * 전환하는 세그먼트 버튼. technician 라우트에서는 렌더하지 않는다.
 *
 * **시뮬레이션 신원 전환일 뿐이다** (D52) — 실제 로그인 시스템이 아니고,
 * 클릭 시 `localStorage` 값만 바뀐다. 화면에 이미 그려진 데이터는 이 컴포넌트가
 * 갱신하지 않는다 — "현재 선택됨" 표시만 책임진다.
 */
export function ManagerIdentitySwitch() {
  const pathname = usePathname();
  // SSR-안전 초기값(항상 배열 0번째) — `getManagerIdentity()`를 초기화 함수로 바로 쓰면
  // 서버 렌더(HTML)는 `window` 부재로 0번째를 내는데 클라이언트 첫 렌더는 즉시
  // localStorage 를 읽어 값이 다를 수 있어(예: 이전에 재무담당을 선택해 둔 상태)
  // hydration mismatch 로 전체 트리가 클라이언트 재렌더로 강등된다(실측: 2026-08-24 QA).
  // 마운트 후 `useEffect`에서 실제 값으로 동기화한다 — 그 시점은 이미 hydration이 끝난
  // 뒤라 안전하다.
  const [selected, setSelected] = useState(MANAGER_IDENTITIES[0].userId);

  useEffect(() => {
    setSelected(getManagerIdentity().userId);
  }, []);

  if (roleFromPath(pathname) !== "manager") return null;

  return (
    <div
      style={sx(
        "display:flex;gap:5px;background:var(--sw);border:1px solid var(--sw-line);border-radius:10px;padding:4px"
      )}
    >
      {MANAGER_IDENTITIES.map((identity) => {
        const on = identity.userId === selected;
        return (
          <button
            key={identity.userId}
            type="button"
            onClick={() => {
              setManagerIdentity(identity.userId);
              setSelected(identity.userId);
            }}
            style={sx(
              "display:inline-flex;align-items:center;gap:7px;border:0;border-radius:7px;padding:8px 14px;" +
                "font:600 12.5px 'Pretendard';cursor:pointer;transition:all .15s;white-space:nowrap;" +
                (on ? "background:var(--blue);color:#fff;" : "background:transparent;color:var(--dim);")
            )}
          >
            {identity.label}
          </button>
        );
      })}
    </div>
  );
}
