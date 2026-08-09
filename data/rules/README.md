# 룰 카탈로그 — 법령 스냅샷 + 해석 룰

> `check_disposal_blockers`(S9)의 데이터·엔진 계층.
> **계층 1(법령 = 사실)과 계층 2(룰 = 해석)를 물리적으로 분리**한 것이 이 디렉토리의 전부다 (D60).
> 설계 배경: `docs/11_ASSET_LIFECYCLE.md`

```
data/rules/
├── laws/               계층 1 — 법령 스냅샷 7건 (append-only, 수정 금지)
├── rules/              계층 2 — 해석 룰 (rule_version 관리)
├── pending_revisions/  개정 감지분 (자동 반영 금지 — 사람 검토·서명 대기). 최초 감지 시 생성
├── engine.py           결정론적 판정기
├── fetch_laws.py       수집(미구현) · 적용 · 개정 감지
└── test_rules.py       19개 테스트
```

## 실행

```bash
# ⚠ pytest 는 dev 의존성에 없다 (--with 로 임시 설치). `uv run python -m pytest` 는 실패한다.
uv run --with pytest python -m pytest data/rules/test_rules.py -q   # 19 passed
uv run python spikes/law_fetch_contract.py                          # apply_fetch 계약 (네트워크 미사용)
```

```python
from data.rules.engine import check_disposal_blockers

result = check_disposal_blockers({
    "equipment_id": "INV-L3-01",
    "tax_credit_applied": True,
    "acquired_at": "2025-03-01",
    "disposal_date": "2026-08-10",
    "months_since_acquisition": 17,
    "has_lien": True, "lien_creditor": "XX은행", "lien_consent_ref": None,
    # … 각 룰의 required_facts 참조
})
# → verdict: "BLOCKED", blockers: [TAX-CREDIT-2Y, LIEN-CONSENT]
```

---

## 엔진이 강제하는 불변식

프롬프트가 아니라 **코드 구조**로 강제한다 — D10이 도구에 UPDATE 권한을 주지 않은 것과 같은 방식.

1. **근거 없는 룰은 로드 거부** — `law_refs`·`contract_refs`가 모두 비면 `RuleIntegrityError` (D61)
2. **미등록 법령 참조 거부** — `laws/`에 없는 ID를 참조하면 로드 실패
3. **경계 구간은 단정 금지** — `boundary.review_band` 안이면 `HOLD` (D62)
4. **사실 부족 ≠ 조건 미해당** — `INSUFFICIENT_FACTS`를 `CLEAR`와 구분 (D62)
5. **시점 조회 시 조용한 최신본 금지** — `get_law_as_of`는 없으면 예외 (D50과 같은 논리)
6. **고려하지 않은 것 명시** — 모든 결과에 `not_considered`, `disclaimer` (D65)

4번이 가장 중요하다. **"조건에 해당하지 않는다"와 "알 수 없다"는 다르다.**

---

## 룰 5종

| rule_id | 유형 | 근거 유형 | 판정 대상 |
|---|---|---|---|
| `TAX-CREDIT-2Y` | BLOCKING | LAW | 사후관리 기간 내 처분 → 추징 |
| `LIEN-CONSENT` | BLOCKING | **CONTRACT** | 채권자 동의 없는 담보물 처분 |
| `INSURANCE-NOTIFY` | PRECONDITION | LAW | 부보 목적물 변동 통지 |
| `VAT-INVOICE` | PRECONDITION | LAW | 매각 시 세금계산서 (폐기는 제외) |
| `SAFETY-INSPECTION` | PRECONDITION | LAW | 이전 후 재검사 |

**`LIEN-CONSENT`가 CONTRACT인 이유:** 법령이 담보물 처분을 금지하는 게 아니라 여신거래약관이 기한이익 상실 사유로 정하는 구조다. 근거의 성격이 섞여 있다는 걸 `source_type`으로 드러냈다.

---

## ⚠️ 법령 원문은 손으로 채우지 않는다

`laws/*.json`의 `text`는 **API 로 받은 것만** 들어간다. 등록 직후에는 `text: null` · `fetch_status: PENDING` 이며 **그 상태로 두는 것이 의도**다.
조문 원문을 손으로 타이핑하면 그 순간 "출처 있는 사실"이 아니라 "누가 적은 텍스트"가 되어 계층 1의 존재 이유가 무너진다. 각 파일의 `verification_note`에 확인 사항을 적어뒀다.

> **현재값 (Sprint 7 MQ-701 실수집 이후)** — 7건 중 **6건 `FETCHED` · 1건 `PENDING`**.
> `PENDING` 은 `KR-CITA-ENF-31` 하나이며 등록 제목(`즉시상각의제`)이 API 값(`즉시상각의 의제`)과
> 달라 `apply_fetch` 가 중단했다 — **사람 승인 대기**. 실측 기록: `../analysis/law_fetch.md`

**조문 번호와 제목도 검증 대상이다** — 개정으로 바뀌므로 수집 시 실제 응답과 대조해야 한다.
이 대조는 문서상의 당부가 아니라 `apply_fetch` 가 코드로 강제한다 (불일치 → 파일 미수정 + `LawMismatchError`).

### 수집 파이프라인 — 지금 어디까지 되나

`fetch_laws.py` 는 **수집기와 적용기를 분리**한다. 인증값이 필요한 건 수집기뿐이라
적용기는 키 없이도 합성 픽스처로 검증돼 있다 (`spikes/law_fetch_contract.py`, **28건 · 네트워크 미사용**).

| 단계 | 함수 | 상태 |
|---|---|---|
| ① OPEN API 이용 신청 → `LAW_API_OC` 설정 | — | ✅ **완료** — 발급·실호출 검증까지 끝났다. ⛔ 값은 저장소 어디에도 적지 않는다 |
| ② 실호출·응답 파싱 | `fetch_from_api` | ✅ **완료 (Sprint 7 · MQ-701)** — `MST` 조회 + `JO` 6자리 + `조문내용/항/호/목` 평탄화 |
| ③ 조문번호·제목 대조 → 파일 기입 → 해시 | `apply_fetch` | ✅ **완료** (`FILLED`/`UNCHANGED`/`REVISION_PENDING`) |
| ④ 개정 감지 → `pending_revisions` | `check_revisions` | ✅ 완료 — 실행 시 6 `UNCHANGED` + 1 `NOT_FETCHED`(멱등) |
| ⑤ `pending_revisions` 검토·서명 흐름 | — | ⛔ 미착수 (Sprint 7, 계층 3) |

> ②의 파라미터는 **전부 실호출로 확정한 값**이다 — `display=100`(기본 20 이면 `상법` exact match 가
> 페이지 밖으로 밀린다) · `search=1`(2 는 본문 검색이라 법령명 exact 0건) · `JO` **6자리**
> (`24` 나 `002400000` 은 HTTP 200 인데 조문이 **0건**으로 온다). 추측한 URL 파라미터를
> 코드에 박으면 "구현돼 있는데 안 되는" 상태가 되므로, 이 4종은 회귀 ⓕ-2 가 잠근다.

### 남은 체크리스트

- [ ] **`KR-CITA-ENF-31` 등록 제목 정정 승인 (사람)** — `즉시상각의제` vs API `즉시상각의 의제`(공백 1칸).
      정체성 대조 실패로 `apply_fetch` 가 **파일을 손대기 전에** 중단했고 `fetch_status` 는 `PENDING` 이다.
      자동 정정하지 않는 것이 D75 — 조용히 덮어쓰면 다른 조문을 같은 조문으로 읽는 경로가 열린다
- [x] law.go.kr OPEN API 이용 신청 → `LAW_API_OC` 설정
      — 값은 API 키가 아니라 **신청 이메일 ID 앞부분**. 비어 있으면 응답이
      `{"result":"필수입력요소 검증에 실패하였습니다"}` 로 온다 (200 이라 조용히 넘어가기 쉽다)
- [x] `fetch_from_api` 구현 (MST 조회 → `JO` 형식 실호출 확인 → 응답 스키마 확정)
- [x] 6개 조문 수집 → `text`·`effective_from`·`text_hash` 채우기 (`apply_fetch` 경유)
- [x] 조문 번호·제목 검증 결과 반영 — 6건 일치, 1건 불일치는 위 항목으로 이관
- [ ] 하위 법령 추가 — 안전검사 대상 기계 목록(시행령·고시), 사후관리 기간(시행령)
- [ ] `pending_revisions` 검토·서명 흐름 연결
- [ ] MCP 도구 `check_disposal_blockers`로 래핑 (`mcp_server/tools/`)

### 완료된 것

- [x] `apply_fetch` — 3분기(`FILLED`/`UNCHANGED`/`REVISION_PENDING`) + 불일치 시 중단
- [x] 자동 덮어쓰기 차단 — 이미 `FETCHED` 인데 해시가 다르면 파일을 건드리지 않고
      `pending_revisions/{law_ref_id}.{timestamp}.json` 에 누적. `force=True` 로 반영할 때도
      직전 스냅샷을 먼저 남긴다 (D60)
- [x] 조문번호·제목 대조를 **누락에도** 적용 — 응답에 `article`·`title` 이 없거나 비어 있으면
      `LawMismatchError`. "확인할 값이 없다"를 "확인했고 문제없다"로 처리하지 않는다
- [x] `text_hash` 는 `engine.text_hash` 재사용 (NFKC + 공백 축약 후 sha256) — 재구현 없음

> **Sprint 7 서명 큐가 읽을 대상: `requires_signature == true` 인 기록만** (`applied` 값으로 재판단하지 말 것).
> `applied` 는 `null`(반영 시도 없음) → `"intent"`(파일 기입 직전, **성공 미확인**) → `"confirmed"`(기입 성공 확인)
> 3상태이고, `confirmed` 만 `requires_signature:false` 다. `intent` 로 멈춘 기록은
> **기입 도중 중단된 것**이므로 사람이 `laws/*.json` 실제 내용과 대조해야 한다.

### 룰을 추가할 때

1. `rules/NEW-RULE.json` 작성 (`law_refs` 또는 `contract_refs` 필수)
2. 참조 조문이 `laws/`에 없으면 먼저 추가
3. `test_rules.py`의 `COVERED`에 ID 추가
4. 트리거 케이스 + 미해당 케이스 최소 2개 테스트

`COVERED`에 안 넣으면 `test_every_rule_is_covered`가 실패한다 — **정의된 룰 = 테스트된 룰**을 강제하는 구조다.

---

## 한계

- 룰은 **통상 사례 기준 목업**이다. 실제 세무·법무 판단을 대체하지 않는다.
- 경계를 어디로 잡을지 **자체가 해석**이다. `boundary.note`에 근거를 남길 것.
- `requires_expert_review: true`인 룰은 UI에서 전문가 확인 안내를 함께 표시할 것.
