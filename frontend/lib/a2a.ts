/**
 * A2A 이력(`GET /api/a2a/history`) 표시 규칙 (MQ-1605, D114).
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 tsc 로 이 파일을 검증한다.
 * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다.
 */

/**
 * 맵에 **자기 키로** 있는가 — `x in MAP` 은 `toString` 같은 프로토타입 키에도 참이다.
 * (`Object.hasOwn` 은 ES2022 라 L1 의 `--target es2020` 단독 tsc 를 위해 쓰지 않는다.)
 */
function hasKey(map: Record<string, unknown>, key: unknown): key is string {
  return typeof key === "string" && Object.prototype.hasOwnProperty.call(map, key);
}

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
  return hasKey(SKILL_VIEW, skill) ? SKILL_VIEW[skill] : { label: `미상(${skill})` };
}

/**
 * `record_a2a_trace` 의 status 어휘 → 표시 톤.
 *
 * 어휘(2026-09-25 갱신, MQ-1911): `ok` | `timeout` | `unavailable` | `error` |
 * `policy_blocked`(D149 — 샌드박스 정책이 발신 전에 막았다. **재시도해도 풀리지 않는다**) |
 * `circuit_open`(D136 — 차단기가 열려 호출하지 않았다). 실패 5종은 전부 `error` 톤이다 —
 * `warn` 은 화면에서 오렌지로 칠해지는데 오렌지는 안전·긴급 전용이라 쓰지 않는다.
 * 모르는 값·`null`(진행 중)은 `unknown` — 초록으로 떨어지지 않는다 (D87).
 */
export function a2aStatusTone(status: string | null | undefined): Tone {
  if (status === "ok") return "ok";
  if (hasKey(FAILURE_LABEL, status)) return "error";
  return "unknown";
}

const FAILURE_LABEL: Record<string, string> = {
  timeout: "시간 초과",
  unavailable: "연결 불가",
  error: "오류",
  policy_blocked: "샌드박스 정책 차단",
  circuit_open: "차단기 열림",
};

/**
 * status → 한국어 라벨. 원 어휘는 화면이 옆에 따로 보여 준다(감사 용도 — 원문 보존).
 * `null` 은 tool_result 가 아직 없는 호출(「진행 중」), 모르는 값은 원문 그대로(`미상(x)`).
 */
export function a2aStatusLabel(status: string | null | undefined): string {
  if (status === null || status === undefined) return "(진행 중)";
  if (status === "ok") return "성공";
  return hasKey(FAILURE_LABEL, status) ? FAILURE_LABEL[status] : `미상(${status})`;
}
