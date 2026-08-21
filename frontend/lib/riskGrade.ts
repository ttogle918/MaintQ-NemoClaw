/**
 * 건물 위험등급(`GET /api/buildings/{id}/risk-grade`·`GET /api/assets/{id}/risk-grade`)
 * 표시 규칙 (MQ-1202, S18).
 *
 * `data/risk_grade.py::risk_grade` 가 주는 `current_grade` 는 `null`(3속성 중 하나라도
 * 미확인 — 등급 산출 보류) 일 수 있다. **`null` 을 `LOW`(또는 어떤 정상 등급)로 접지 않는다**
 * (D62 — 모름과 없음의 구분). "위험이 낮다"와 "산출하지 않았다"는 다른 사실이다.
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 `tsc` 로 이 파일을 검증한다.
 * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다 — `paths` 설정 없이 단독 컴파일돼야 한다.
 */

export type Tone = "ok" | "warn" | "error" | "unknown";

export interface GradeView {
  label: string;
  tone: Tone;
}

// 총 맵 1곳 — 맵 밖 값은 unknown + 원문 보존 (D87)
const GRADE_VIEW: Record<string, GradeView> = {
  LOW: { label: "낮음", tone: "ok" },
  MEDIUM: { label: "보통", tone: "warn" },
  HIGH: { label: "높음", tone: "error" },
};

/**
 * `current_grade` → 표시. `null`(미산출)은 전용 `unknown` 톤 + "미산출"을 반환하며 **절대
 * `LOW`/`ok` 로 오분류되지 않는다** — 가장 중요한 회귀 포인트(D62). 맵 밖 문자열도 같은
 * `unknown` 톤 + 원문 보존이다.
 */
export function gradeView(grade: string | null): GradeView {
  if (grade === null) return { label: "미산출", tone: "unknown" };
  const known = GRADE_VIEW[grade];
  if (known) return known;
  return { label: `미상(${grade})`, tone: "unknown" };
}
