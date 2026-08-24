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

/**
 * 목업 신원 — 백엔드가 X-User 헤더에서 requested_by/decided_by 를 주입한다 (D23).
 *
 * ⚠️ 헤더에 실리는 건 **ASCII 사용자 ID** 다 (D36). 한글 표시명을 그대로 넣으면
 * HTTP 헤더 값이 ASCII 범위라 fetch 가 UnicodeEncodeError 로 거부한다 (SP3 에서 확인).
 * DB 에도 ID 가 저장되고, 화면 표시명은 아래 매핑으로 렌더한다.
 */
export const ROLE_USER_ID: Record<Role, string> = {
  technician: "tech-01",
  manager: "mgr-01",
};

/** 화면 표시용 이름. 절대 헤더에 넣지 말 것. */
export const ROLE_USER_NAME: Record<Role, string> = {
  technician: "김OO",
  manager: "박OO",
};

export function roleFromPath(pathname: string): Role {
  return pathname.startsWith("/manager") ? "manager" : "technician";
}

/**
 * 팀장 화면 안에서 실제로 액션을 부리는 신원 — 정비팀장(발주 승인)과 재무담당(재무승인,
 * Sprint 17)이 같은 `/manager` 라우트를 공유한다 (D52 — 시뮬레이션 신원, 실제 인증 아님).
 * `getManagerIdentity()` 기본값은 `MANAGER_IDENTITIES[0]`(정비팀장) — 배열 순서를 바꾸면
 * 기존 회귀(프론트 라우트 개수 등)가 흔들린다.
 */
export interface ManagerIdentity {
  userId: string;
  displayName: string;
  department: "maintenance" | "finance";
  label: string;
}

export const MANAGER_IDENTITIES: ManagerIdentity[] = [
  { userId: "mgr-01", displayName: "박OO", department: "maintenance", label: "정비팀장 · 박OO" },
  { userId: "mgr-02", displayName: "최OO", department: "finance", label: "재무담당 · 최OO" },
];

const MANAGER_IDENTITY_KEY = "maintq_manager_identity";

/** SSR 안전 — `window` 없으면 기본값(정비팀장). */
export function getManagerIdentity(): ManagerIdentity {
  if (typeof window === "undefined") return MANAGER_IDENTITIES[0];
  const stored = window.localStorage.getItem(MANAGER_IDENTITY_KEY);
  return MANAGER_IDENTITIES.find((m) => m.userId === stored) ?? MANAGER_IDENTITIES[0];
}

export function setManagerIdentity(userId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MANAGER_IDENTITY_KEY, userId);
}
