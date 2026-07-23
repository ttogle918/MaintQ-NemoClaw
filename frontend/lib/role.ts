/**
 * 역할은 라우트가 결정한다 (`/technician`, `/manager`).
 *
 * 클라이언트 상태 토글로 역할을 바꾸면 "정비사 approve → 403" 을 시연할 수 없다.
 * 라우트별로 X-Role 을 고정해야 권한 경계가 실제로 드러난다.
 */
export type Role = "technician" | "manager";

export const ROLE_HOME: Record<Role, string> = {
  technician: "/technician",
  manager: "/manager",
};

export const ROLE_LABEL: Record<Role, string> = {
  technician: "정비사 · 진단 콘솔",
  manager: "보전팀장 · 승인 큐",
};

export const ROLE_ICON: Record<Role, string> = {
  technician: "🔧",
  manager: "🗂",
};

/** 목업 신원 — 백엔드가 X-User 헤더에서 requested_by/decided_by 를 주입한다 (D23). */
export const ROLE_USER: Record<Role, string> = {
  technician: "김OO",
  manager: "박OO",
};

export function roleFromPath(pathname: string): Role {
  return pathname.startsWith("/manager") ? "manager" : "technician";
}
