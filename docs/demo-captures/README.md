# MaintQ 내부 기능 GIF 캡처

데모 영상 준비를 위해 브라우저 자동화로 실제 화면 동작을 캡처한 GIF 모음. A2A(FinAllQ·InsuQ
연동) 캡처는 `A2A_Q/docs/presentation/`에 별도로 있음 — 여기는 MaintQ 자체 기능만.

모든 캡처는 시드 데이터 그대로, 실제 API 응답으로 찍었다(연출 없음).

## 목록

| GIF | 기능 | 화면 | 보여주는 것 |
|---|---|---|---|
| `assets/unknown-error-code.gif` | 미지 에러코드 처리 | 정비사·진단 콘솔 | 카탈로그에 없는 에러코드를 물으면 유사 코드를 추측하지 않고 "모른다"로 답함(S4, 환각률 0% 목표) |
| `assets/alternative-parts.gif` | 대체 부품 추천 | 정비사·진단 콘솔 | 재고 없는 부품에 대해 `part_alternatives` 테이블 기반 대체품 제시 |
| `assets/repeat-failure-hold.gif` | 반복 고장 감지 → 발주 보류 | 정비사·진단 콘솔 | 안전 경고(매뉴얼 근거)부터 `get_error_history`가 30일 3회 반복을 감지해 근본원인 확인 전까지 발주를 HOLD하는 전체 흐름 |
| `assets/disposal-precheck.gif` | 처분 사전판정 | 자산 상세 → 처분 사전판정 | 처분일 미입력 시 INSUFFICIENT_FACTS로 정직하게 답하고, 입력 후 CLEAR 판정 + 근거 조문·"고려하지 않은 것" 고지까지 |
| `assets/disposal-evidence-bundle.gif` | 처분 근거 번들 조회 | 자산 상세 → 근거 번들 조회 | `bundle_hash`로 laws·rules·evaluated·contracts·facts 5개 항목을 고정하고, 룰별 TRIGGERED/CLEAR/INSUFFICIENT_FACTS 판정 근거를 모두 노출 |
| `assets/deadline-risk-grade.gif` | 법정 기한 추적 · 건물 위험등급 | 보전팀장 콘솔 (F5·F6) | 기한 범위(180~730일)를 넓혀가며 임박 항목을 찾고, 건물별 위험등급 산출식과 "자동 반영 안 됨" 고지 확인 |
| `assets/expenditure-classification.gif` | 지출 성격 분류 | 재무담당 콘솔 | 핵심부품 원상복구 경계 사례에서 자본적지출/수익적지출을 단정하지 않고 "판단 유보 — 전문가 검토 필요"로 정직하게 응답 |

## 캡처 방법

Claude Code + claude-in-chrome 브라우저 자동화로 실제 로컬 서버(`localhost:3003`)를 조작하며
`gif_creator`로 녹화. 세부 조작 순서·주의사항은 `docs/sessions/2026-08-24_시나리오1.md` 참고
(A2A 시나리오 리허설 노트지만 공통 함정 — 날짜 입력 필드, 드롭다운 키보드 이슈 등 — 이 겹친다).
