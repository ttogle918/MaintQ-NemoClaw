---
name: scenario-smoke
description: S1~S4 시나리오 스모크 테스트를 순서대로 실행한다. 사용자가 /scenario-smoke를 호출하거나, 데모 전 전체 파이프라인 동작 확인이 필요할 때 사용.
---

# 시나리오 스모크 테스트 (S1~S4)

`docs/02_SCENARIOS.md`의 4개 시나리오를 콘솔 레벨로 순서대로 실행하고 통과/실패를 보고한다.

## 입력 (고정 문장)

| # | 입력 | 통과 조건 (도구 시퀀스 + 결과) |
|---|---|---|
| S1 | "iG5A 인버터에 OHt 에러 떴어" (equipment: INV-L1-01) | lookup→rag→inventory→quotes→po_draft, draft 생성, 인용 페이지 존재 |
| S2 | "S100 인버터 제어보드 교체해야 해" | inventory(qty=0)→alternatives→비교 제시, confirmed=false 부품 미제안 |
| S3 | "3번 라인 인버터 또 OCt 떴어" (equipment: INV-L3-01) | history repeated=true→근본원인 모드, SAFETY 블록 존재, po_draft 미호출 |
| S4 | "XY9 에러가 떴는데" | lookup not_found→원인/조치 생성 없음, A/S 안내 존재 |

## 판정 방법

- trace 로그의 tool_call 시퀀스를 기대 시퀀스와 비교 (순서 포함)
- 응답 텍스트는 키워드 검사: S3의 "SAFETY"/"주의", S4의 "확인되지 않" 등
- 4개 중 하나라도 실패하면 실패한 시나리오의 전체 trace를 첨부해 보고

## 주의

- 이 테스트는 seed-db 스킬로 DB가 케이스 맵대로 시드된 상태를 전제 — 실행 전 DB 존재 확인, 없으면 seed-db 먼저
- S3에서 po_draft가 호출되면 실패 (발주 보류가 정답)
