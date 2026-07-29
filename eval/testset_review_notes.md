# eval/testset_draft.json — 검수 근거 노트 (MQ-501)

> ⚠️ **경고**: 이 표의 `part_no` 는 검수 전(D12) 초안이다 — `related_parts` 검수 완료 전까지
> 이 testset 으로 낸 부품 특정 정확률을 실적으로 인용하지 말 것.
> **`eval/testset.json` 반영은 사람이 직접 수행**한다(`.claude/hooks/guard_writes.py` 가
> Claude 의 `eval/testset.json` 직접 반영을 exit 2 로 차단함 — Bash heredoc 등 우회 시도도
> 금지). 이 파일(`testset_draft.json`)을 검수 후 그대로든 수정 후든 사람이 직접
> `eval/testset.json` 으로 옮겨야 한다.

## 0. 데이터 원천 (실측 — 추측 없음)

- `data/extracted/error_codes.json` — `_status: "승인 완료 (2026-07-28)"`, 65건
  (iG5A 24 · S100 41). 아래 SQL은 시드 적재본(`data/maintq.db`, `--with-error-codes`)을
  대상으로 실행.
- `data/related_parts.seed.json` — 7건, 전부 `reviewed: false` (사람 검수 전, D12).
- `data/seed.py` — `EQUIPMENT` 상수 10대, `INVENTORY_FIXED`/`ALTERNATIVES` 케이스 맵.
- 실행: `uv run python -c "..."` 로 `data/maintq.db` 직접 SQL 조회 (아래 각 절 참조).

## 1. S1 (T01~T12) — 단일 매핑 4쌍 실측

`related_parts.seed.json` 7건 중 `iG5A OCT`(2부품 매핑, 모호)를 제외한 6개 (model,code)→part_no
매핑을 사용. 각 매핑을 서로 다른 equipment_id 조합으로 2회씩 반복 = 12문항.

```sql
SELECT model,code,related_parts,manual_page,severity FROM error_codes WHERE model=? AND code=?
```

| model | code | related_parts (DB 실측) | manual_page | severity |
|---|---|---|---|---|
| iG5A | OHT | `["FAN-IG5-01"]` | 202 | fault |
| iG5A | FAN | `["FAN-IG5-01"]` | 203 | fault |
| iG5A | GFT | `["MTR-CBL-IG5"]` | 204 | fault |
| S100 | OHT | `["FAN-S100-01"]` | 417 | fault |
| S100 | FAN | `["FAN-S100-01"]` | 417 | fault |
| S100 | OCT | `["MTR-CBL-S100"]` | 416 | fault |

(참고 — iG5A OCT는 시드에서 제외 대상: `["MTR-CBL-IG5", "MTR-3P-2K2"]` 2부품 매핑, 모호하므로
S1 문항에 사용하지 않음.)

`GET /api/equipment` 대신 `data/seed.py` `EQUIPMENT` 상수 + 실 DB `equipment` 테이블 조회로
확인한 장비 목록:

- iG5A: `INV-L1-01`(1번 조립라인 분전반) · `INV-L1-02`(1번 조립라인 컨베이어) ·
  `INV-L3-02`(3번 조립라인 배기팬) · `INV-L4-03`(4번 포장라인 집진기) — 4대
  (`INV-L3-01`은 S3 전용 시드 조합이라 S1 후보에서 제외)
- S100: `INV-L2-01`(2번 가공라인 주축) · `INV-L2-02`(2번 가공라인 절삭유 펌프) ·
  `INV-L3-03`(3번 조립라인 리프터) · `INV-L4-01`(4번 포장라인 컨베이어) ·
  `INV-L4-02`(4번 포장라인 랩핑기) — 5대

| id | model | code (display) | equipment_id | part_no 근거 |
|---|---|---|---|---|
| T01 | iG5A | OHT (`OHt`) | INV-L1-01 | related_parts OHT 매핑 → FAN-IG5-01, reviewed:false |
| T02 | iG5A | OHT (`OHt`) | INV-L1-02 | 상동 (다른 장비 반복) |
| T03 | iG5A | FAN (`FAn`) | INV-L3-02 | related_parts FAN 매핑 → FAN-IG5-01, reviewed:false |
| T04 | iG5A | FAN (`FAn`) | INV-L4-03 | 상동 (다른 장비 반복) |
| T05 | iG5A | GFT (`GFt`) | INV-L1-01 | related_parts GFT 매핑 → MTR-CBL-IG5, reviewed:false |
| T06 | iG5A | GFT (`GFt`) | INV-L3-02 | 상동 (다른 장비 반복) |
| T07 | S100 | OHT (`oht`) | INV-L2-01 | related_parts OHT 매핑 → FAN-S100-01, reviewed:false |
| T08 | S100 | OHT (`oht`) | INV-L3-03 | 상동 (다른 장비 반복) |
| T09 | S100 | FAN (`fan`) | INV-L2-02 | related_parts FAN 매핑 → FAN-S100-01, reviewed:false |
| T10 | S100 | FAN (`fan`) | INV-L4-01 | 상동 (다른 장비 반복) |
| T11 | S100 | OCT (`oct`) | INV-L4-02 | related_parts OCT 매핑 → MTR-CBL-S100, reviewed:false |
| T12 | S100 | OCT (`oct`) | INV-L2-01 | 상동 (다른 장비 반복) |

`safety_page`: iG5A 문항 = 4, S100 문항 = 2 (`SAFETY_BASELINE["pages"]` 승인값, 09_RUNTIME §1
S3 절 근거 페이지와 동일 상수 사용).

## 2. S2 (T13~T15) — 재고/단종/대체품 실측

```sql
SELECT part_no,name,discontinued FROM parts WHERE part_no=?;
SELECT part_no,qty,safety_stock FROM inventory WHERE part_no=?;
SELECT part_no,alt_part_no,compat_confirmed FROM part_alternatives WHERE part_no=?;
```

| part_no | discontinued | qty | safety_stock | 확정 대체품 |
|---|---|---|---|---|
| PCB-S100-CTRL | 1 | 0 | 1 | PCB-S100-CTRL-R2 (compat_confirmed=1) |
| PCB-S100-CTRL-R2 | 0 | 4 | 2 | — (대체품 없음, 그 자체가 최종 대체품) |
| PWR-S100-MOD | 0 | 0 | 2 | 없음 (0건) — 에스컬레이션 대상 |

| id | 입력 요지 | equipment_id | part_no 근거 |
|---|---|---|---|
| T13 | S100 제어보드 교체 | INV-L2-01 | PCB-S100-CTRL(재고0·단종) → part_alternatives 확정 대체품 PCB-S100-CTRL-R2 |
| T14 | 상동, 다른 장비/문구 | INV-L3-03 | 상동 |
| T15 | S100 전원모듈 교체 | INV-L4-01 | PWR-S100-MOD(재고0·대체품0건) — search_inventory 결과 그대로가 특정 대상(대체 불가, 에스컬레이션) |

주의: T13/T14가 같은 부품(PCB-S100-CTRL-R2)을 기대하는 것은 의도(시드가 보장하는 결정론적
S2 케이스가 이것뿐 — sprint-5.md "엣지 케이스" 절 명시).

## 3. S3 (T16~T18) — 30일 내 3회 반복 유일 조합 실측

```sql
SELECT equipment_id, code, count(*) c FROM error_history
WHERE occurred_at >= datetime('now','-30 day')
GROUP BY equipment_id, code HAVING c >= 3;
```

결과: `[('INV-L3-01', 'OCT', 3)]` — **1행만** 존재. 30일 내 3회 이상 반복하는 (equipment, code)
조합은 `INV-L3-01`+`OCT` 가 유일함을 실측 확인. T16~T18은 이 조합을 문구만 바꿔 3회 사용.
`part_no`는 스키마대로 전부 `null`(근본원인 미확정 — 발주 보류, D35·A8). `expect_hold: true`
는 S3 문항에만 적용(전 문항 유일).

## 4. S4 (T19~T20) — 후보 코드 부재 확인 로그

**실행 스크립트 (실측)**:

```python
import json
d = json.load(open('data/extracted/error_codes.json', encoding='utf-8'))
codes = sorted(set((e['model'], e['code']) for e in d['entries']))
print(len(codes))                                    # 65
print(('iG5A', 'XY9') in codes)                       # False
print(('S100', 'QQ1') in codes)                       # False
all_igsa = {c for m, c in codes if m == 'iG5A'}
all_s100 = {c for m, c in codes if m == 'S100'}
print('XY9' in all_igsa)                              # False
print('QQ1' in all_s100)                              # False
```

**실행 결과 (2026-07-29 실측)**:

```
_status: 승인 완료 (2026-07-28) — ② 4건 이미지 재확인 + ③ 2건 결정 반영. data/analysis/ig5a_code_mapping.md 참조
counts: {'iG5A': 24, 'S100': 41}
65
('iG5A','XY9') in codes: False
('S100','QQ1') in codes: False
XY9 in any iG5A codes: False
QQ1 in any S100 codes: False
```

전체 65건 (model, code) 목록을 직접 나열해 대조(별도 스크립트 출력, iG5A 24건·S100 41건 —
`OL`/`OC` 계열 등 표기 유사 코드 포함 전수 확인) — `XY9`(iG5A), `QQ1`(S100) 둘 다 어느 목록에도
없음을 확인. 충돌 없어 대체 후보 불필요.

| id | model | 후보 코드 | equipment_id | 부재 확인 |
|---|---|---|---|---|
| T19 | iG5A | XY9 | INV-L1-01 | 위 로그 참조 — iG5A 24건 목록에 없음 |
| T20 | S100 | QQ1 | INV-L2-02 | 위 로그 참조 — S100 41건 목록에 없음 |

`safety_required: false`(S4는 위험 절차 안내가 아니라 A/S 안내), `expect_not_found: true`,
`part_no: null`. `safety_page`는 스키마 지침("전부 채운다")에 따라 model 기준값(iG5A=4/S100=2)을
그대로 채웠으나 `safety_required=false`라 `eval/score.py`의 `_judge_safety`는 이 문항을
분모에서 제외한다(`applicable=False`) — 즉 이 필드는 참조되지 않는다.

## 5. role 필드 설계

20문항 전부 `"technician"`으로 통일. `POST /api/chat`은 role을 게이트하지 않음
(`backend/deps.py`·`backend/routers/chat.py` 확인 — `require()` 호출은
`backend/routers/po.py:55,62,69` 승인 워크플로우에만 존재). 403 지표는 문항 루프 밖
별도 고정 점검(`eval/run_eval.py`의 `check_permission_403`, PO-0117 승인 시도)이 담당한다.

## 6. DoD 셀프체크 (실행 로그)

```
$ python -c "import json; d=json.load(open('eval/testset_draft.json',encoding='utf-8')); \
  assert len(d)==20; \
  assert sum(1 for x in d if x['expected']['branch']=='s3_root_cause')==3; \
  assert all(x['expected']['part_no'] is None for x in d if x['expected']['branch'] in ('s3_root_cause','s4_not_found'))"
(exit 0, 통과 — 아래 "종료 보고" 섹션 참조 실행 로그 첨부)
```
