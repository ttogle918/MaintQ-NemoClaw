# 룰 카탈로그 — 법령 스냅샷 + 해석 룰

> `check_disposal_blockers`(S9)의 데이터·엔진 계층.
> **계층 1(법령 = 사실)과 계층 2(룰 = 해석)를 물리적으로 분리**한 것이 이 디렉토리의 전부다 (D60).
> 설계 배경: `docs/11_ASSET_LIFECYCLE.md`

```
data/rules/
├── laws/           계층 1 — 법령 스냅샷 (append-only, 수정 금지)
├── rules/          계층 2 — 해석 룰 (rule_version 관리)
├── engine.py       결정론적 판정기
├── fetch_laws.py   수집 · 개정 감지
└── test_rules.py   19개 테스트
```

## 실행

```bash
uv run python -m pytest data/rules/test_rules.py -q     # 19 passed
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

## ⚠️ 법령 원문은 아직 비어 있다

`laws/*.json`의 `text`는 전부 `null`, `fetch_status`는 `PENDING`이다. **의도한 것이다.**
조문 원문을 손으로 타이핑하면 그 순간 "출처 있는 사실"이 아니라 "누가 적은 텍스트"가 되어 계층 1의 존재 이유가 무너진다. 각 파일의 `verification_note`에 확인 사항을 적어뒀다.

**조문 번호와 제목도 검증 대상이다** — 개정으로 바뀌므로 수집 시 실제 응답과 대조해야 한다.

### 체크리스트

- [ ] law.go.kr OPEN API 이용 신청 → `LAW_API_KEY` 설정
- [ ] `fetch_from_api` 구현 (응답 스키마 확인 후)
- [ ] 6개 조문 수집 → `text`·`effective_from`·`text_hash` 채우기
- [ ] 조문 번호·제목 검증, 어긋나면 `law_ref_id` 정정
- [ ] 하위 법령 추가 — 안전검사 대상 기계 목록(시행령·고시), 사후관리 기간(시행령)
- [ ] `pending_revisions` 검토·서명 흐름 연결
- [ ] MCP 도구 `check_disposal_blockers`로 래핑 (`mcp_server/tools/`)

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
