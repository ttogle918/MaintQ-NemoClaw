---
name: maintq-diagnose
description: 인버터 에러코드 진단부터 재고 확인·공급사 견적·발주 초안까지 MaintQ MCP 도구(maintq__*)로 순서대로 처리한다. 정비사가 iG5A·S100·IE5·HV600 인버터의 에러코드("OHt 떴어", "OCt 또 떴어", "HV600 GF 떴어")나 부품 교체("제어보드 교체해야 해")를 말할 때 사용. 매뉴얼에 없는 코드(온보딩 승격 전 HV600 코드 포함)는 추측하지 않고 A/S 로 넘긴다.
license: Apache-2.0
compatibility: "MaintQ MCP 서버(core 프로필, 7종)가 연결된 에이전트. OpenClaw(NemoClaw) 에서 검증"
metadata:
  author: "MaintQ"
  tags:
    - maintenance
    - manufacturing
    - diagnosis
    - mcp
  domain: industrial-maintenance
allowed-tools:
  - maintq__lookup_error_code
  - maintq__rag_search_manual
  - maintq__get_error_history
  - maintq__search_inventory
  - maintq__find_alternative_parts
  - maintq__get_supplier_quotes
  - maintq__create_po_draft
---

# MaintQ 설비 진단 → 발주 초안

## 목적

정비사의 고장 신고를 **매뉴얼 근거가 있는 진단**으로 바꾸고, 필요한 부품을 **발주 초안**까지 연결한다.
판단의 근거는 도구 결과뿐이다. 발주의 확정·승인은 사람이 MaintQ 승인 큐에서 한다 — 이 스킬은
초안을 만드는 데서 멈춘다.

절대 규칙·안전 확정 문구는 워크스페이스의 AGENTS.md 에 있다. 이 스킬은 **흐름**만 정한다.

## 시작 전

- **기종**이 iG5A / S100 / IE5 / HV600 중 무엇인지 확인한다. 말하지 않았으면 도구 호출 전에 묻는다.
- **HV600 은 온보딩 기종이다** — 사람이 승격한 코드만 정의가 나온다. `not_found` 면 **흐름 D** 로 간다
  (승격 전이라는 이유로 다른 기종·일반 지식에서 뜻을 빌려 오지 않는다). 안전 문구는 AGENTS.md
  「온보딩 승인 기종」 절에 승인분이 있을 때만 쓴다 — iG5A·S100 확정 문구로 대신하지 않는다.
- `code` 에는 표시부 코드 토큰만 넣는다("fan 에러" → `fan`). 대소문자는 사용자가 쓴 그대로.

## 흐름 — 분기를 먼저 판정한다

### A. 에러코드가 있다 (S1 · S3 · S4)

1. `maintq__lookup_error_code(model, code)` — **에러코드를 물을 때마다 새로 호출한다.** 같은 대화에서
   앞서 답한 코드라도 이전 결과를 재사용하지 않는다(사람이 그 사이 승격했을 수 있다 — D146).
   - `not_found` → **흐름 D** 로. 비슷한 코드를 추측하지 않는다.
   - `error` + `catalog_not_loaded` → "카탈로그 미적재 — 관리자 문의" 로 종료. 미지 코드로 다루지 않는다.
2. `maintq__get_error_history(...)` — `repeated: true` 면 **흐름 C** 로.
3. `maintq__rag_search_manual(query, model)` — 점검·조치 절차의 근거 페이지를 얻는다. **생략 금지**.
4. `related_parts` 의 **첫 품번**을 `maintq__search_inventory(part_no=...)` 로 조회한다.
   - `qty == 0` 또는 `discontinued` → **흐름 B** 로.
5. `maintq__get_supplier_quotes(...)` — 공급사가 둘 이상이면 리드타임·단가·MOQ 를 표로 비교한다.
6. 답변: 진단(정의·원인) → 절차 요약(근거 페이지) → **안전 확정 문구** → 재고 → 견적 비교 →
   "공급사와 수량을 골라 주세요". **이 턴에서는 발주하지 않는다.**
7. 다음 턴에 사용자가 고르면 `maintq__create_po_draft(...)` → "초안이 생성됐고 승인 큐에서
   사람이 확정한다" 고 알린다. `moq_not_met` 이면 수량을 올리지 말고 되묻는다.

### B. 재고 없음·단종 (S2)

에러코드 없이 "제어보드 교체해야 해" 로 들어와도 이 흐름이다 — 에러코드를 되묻지 않는다.

1. `maintq__search_inventory(part_name, model)` (코드가 없을 때) → `qty == 0`·단종 확인
2. `maintq__rag_search_manual` 로 교체 근거를 확보한다 (안전 문구를 붙이려면 필요하다)
3. `maintq__find_alternative_parts(...)` — **`compat_confirmed: true` 만** 제안한다
   - `empty` → 긴급 견적·담당자 에스컬레이션을 안내하고 끝낸다
4. 원부품 vs 대체품 견적 비교 → 사용자 선택 → 다음 턴에 초안

### C. 반복 고장 (S3)

`repeated: true` 면 리셋·부품 교체 권유를 멈춘다.

1. `maintq__rag_search_manual` 로 근본원인 점검 절차(출력측 지락·절연·부하)를 찾는다
2. **안전 확정 문구**와 함께 근거 있는 항목만으로 점검 체크리스트를 낸다
3. **발주 보류** — 원인이 확정되기 전에는 `maintq__create_po_draft` 를 호출하지 않는다

### D. 미지 코드 (S4)

1. "해당 기종 매뉴얼에서 확인되지 않는 코드입니다" 라고 그대로 알린다
2. 표시부 재확인 요청(오독 가능성) · 제조사 A/S 안내 · 필요하면 문의 메일 초안
3. **원인·조치를 만들어 내지 않는다** — 이 흐름의 성공 기준은 환각 0건이다

## 하지 않는 것

- `maintq__create_po_draft` 는 유일한 쓰기 도구이며 **초안 INSERT 만** 한다 — 상태 전이는 사람 전용 API 다

- 같은 대화에서 이미 답한 에러코드라도 `maintq__lookup_error_code` 를 건너뛰고 이전 결과("앞서 설명드린
  것처럼")로 답하지 않는다 — 코드를 물을 때마다 새로 조회한다(온보딩 승격으로 결과가 바뀔 수 있다, D146)
- 품번·단가·재고 수치·요청자 신원을 지어내지 않는다
- 발주를 "완료했다"·"승인됐다" 고 말하지 않는다 (초안뿐이다)
- 승인된 안전 문구가 없는 기종(IE5 · 안전 문구 승인 전 HV600 — AGENTS.md 확인)에 위험 작업 절차를 안내하지 않는다
- 도구 결과에 없는 매뉴얼 페이지를 적지 않는다
