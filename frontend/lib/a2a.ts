/**
 * A2A 이력(`GET /api/a2a/history`) 표시 규칙 (MQ-1605, D114).
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 tsc 로 이 파일을 검증한다.
 * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다.
 */

export type Tone = "ok" | "warn" | "error" | "unknown";

export interface SkillView {
  label: string;
}

const SKILL_VIEW: Record<string, SkillView> = {
  "request-withdrawal": { label: "FinAllQ · 출금요청" },
  "lookup-clause": { label: "InsuQ · 약관조회" },
  "assess-loan": { label: "FinAllQ · 담보대출 사전판정" },
};

/** 맵 밖 스킬명도 원문을 보존한다 (D87 — 지어내지 않는다). */
export function skillView(skill: string): SkillView {
  return SKILL_VIEW[skill] ?? { label: `미상(${skill})` };
}

/** `record_a2a_trace` 의 status 어휘(ok|timeout|unavailable|error) → 표시 톤. */
export function a2aStatusTone(status: string | null | undefined): Tone {
  if (status === "ok") return "ok";
  if (status === "timeout" || status === "unavailable" || status === "error") return "error";
  return "unknown";
}
