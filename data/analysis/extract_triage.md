# 추출 품질 triage — before 스냅샷 (MQ-902)

**생성**: 2026-08-14 · **자동 생성 파일** — 손으로 고치지 말고 `uv run python data/extract_triage.py` 를 다시 돌릴 것.

입력: `data/extracted/error_codes.json` (sha256 `2033f896c621ed7e…`, generated_at 2026-08-05) — **읽기 전용**. 이 스크립트는 정본을 쓰지 않는다 (D99).

이 문서는 MQ-905·907 이 파서를 고치기 **전**의 상태다. 개선을 주장하려면 이 숫자와 대조해야 한다.

## 0. 경고

- 🔴 ANCHOR_CONFLICT — 조치문 추출에 성공한 코드가 있는데 코드 토큰이 0인 페이지: ig5a-manual p.202(SOURCE_MISSING), ig5a-manual p.204(RE_OCR_CANDIDATE). 이 페이지들에서 토큰 축은 눈이 멀었다(추출은 코드 토큰이 아니라 한글 명칭으로 조인한다). 그중 SOURCE_MISSING 라벨이 붙은 ig5a-manual p.202(SOURCE_MISSING) 은 근거가 없는 라벨이므로 '소스를 바꿔야 풀린다'로 읽지 마세요.

## 1. 항목 축 — 필드 결측 (65건 전수)

| model | codes | actions 결측 | causes 결측 | 브리핑 기대 (건/조치/원인) |
|---|---|---|---|---|
| S100 | 41 | 26 | 0 | 41 / 26 / 0 |
| iG5A | 24 | 11 | 0 | 24 / 11 / 0 |

- 합계 **65건** · `_unparsed` **0** · `_pending_review` **0**
- 기대값과 실측이 일치한다.

## 2. 페이지 축 — 판정

판정 규칙 (양성 축이 가른다): `missing>0 & tokens==0 → SOURCE_MISSING` · `missing>0 & tokens>0 → CELL_SPLIT` · `missing==0 & 신호 발화 → RE_OCR_CANDIDATE` · 그 밖 `OK`.

| manual_id | page(물리) | label | codes | with_actions | missing | code_tokens ★ | field_missing | length_outlier | table_collapse |
|---|---|---|---|---|---|---|---|---|---|
| ig5a-manual | p.202 | **SOURCE_MISSING** | 9 | 6 | 3 | 0 | 0.333 | 0.034 | 0.022 |
| ig5a-manual | p.203 | **CELL_SPLIT** | 11 | 3 | 8 | 4 | 0.727 | 0.074 | 0.032 |
| ig5a-manual | p.204 | **RE_OCR_CANDIDATE** | 4 | 4 | 0 | 0 | 0.000 | 0.105 | 0.000 |
| s100-manual | p.416 | **CELL_SPLIT** | 11 | 9 | 2 | 5 | 0.182 | 0.054 | 0.000 |
| s100-manual | p.417 | **CELL_SPLIT** | 10 | 4 | 6 | 6 | 0.600 | 0.029 | 0.000 |
| s100-manual | p.418 | **CELL_SPLIT** | 10 | 0 | 10 | 1 | 1.000 | 0.062 | 0.025 |
| s100-manual | p.419 | **CELL_SPLIT** | 10 | 2 | 8 | 3 | 0.800 | 0.000 | 0.238 |

### 두 축 실측 한 줄 요약

```
ig5a-manual p.202: missing 3 / code_tokens 0 -> SOURCE_MISSING
ig5a-manual p.203: missing 8 / code_tokens 4 -> CELL_SPLIT
ig5a-manual p.204: missing 0 / code_tokens 0 -> RE_OCR_CANDIDATE
s100-manual p.416: missing 2 / code_tokens 5 -> CELL_SPLIT
s100-manual p.417: missing 6 / code_tokens 6 -> CELL_SPLIT
s100-manual p.418: missing 10 / code_tokens 1 -> CELL_SPLIT
s100-manual p.419: missing 8 / code_tokens 3 -> CELL_SPLIT
```

### 페이지별 실측 상세

- `ig5a-manual p.202` **SOURCE_MISSING** — codes 9 / with_actions 6 / missing 3 / code_tokens 0 (키패드표기 포함 0) / cells 29 / rows 17 ⚠ anchor_conflict: 조치문 추출에 성공한 코드가 있는데 코드 토큰 0 — 이 페이지에서 토큰 축은 눈이 멀었다 (따라서 이 SOURCE_MISSING 은 근거 없는 라벨이다)
- `ig5a-manual p.203` **CELL_SPLIT** — codes 11 / with_actions 3 / missing 8 / code_tokens 4=EST,NTC (키패드표기 포함 4) / cells 27 / rows 16
- `ig5a-manual p.204` **RE_OCR_CANDIDATE** — codes 4 / with_actions 4 / missing 0 / code_tokens 0 (키패드표기 포함 0) / cells 19 / rows 10 ⚠ anchor_conflict: 조치문 추출에 성공한 코드가 있는데 코드 토큰 0 — 이 페이지에서 토큰 축은 눈이 멀었다 · 결측 0 — 조판 신호만 발화한 **점검 후보**이며 알려진 결함이 아니다
- `s100-manual p.416` **CELL_SPLIT** — codes 11 / with_actions 9 / missing 2 / code_tokens 5=GFT,OC2,OCT,OVT (키패드표기 포함 16) / cells 37 / rows 25
- `s100-manual p.417` **CELL_SPLIT** — codes 10 / with_actions 4 / missing 6 / code_tokens 6=BX,NTC,PID (키패드표기 포함 18) / cells 34 / rows 23
- `s100-manual p.418` **CELL_SPLIT** — codes 10 / with_actions 0 / missing 10 / code_tokens 1=HOLD (키패드표기 포함 14) / cells 32 / rows 25
- `s100-manual p.419` **CELL_SPLIT** — codes 10 / with_actions 2 / missing 8 / code_tokens 3=FAN,IOL,PID (키패드표기 포함 16) / cells 23 / rows 23

- 라벨 분포: SOURCE_MISSING 1 · CELL_SPLIT 5 · RE_OCR_CANDIDATE 1 · OK 0 · UNSCANNED 0 (스캔 7페이지)

### 계획 기대 라벨과의 대조 — 다르면 실측을 적는다

Sprint 9 §6 MQ-902 DoD 는 *iG5A 조치 결측 = `SOURCE_MISSING` · S100 결측 페이지 = `CELL_SPLIT`* 을 기대했다. 실측은 다음과 같다 (결측 **코드 수**를 라벨별로 갈라 센 것):

- `ig5a-manual` 결측 11건 → CELL_SPLIT 8건 · SOURCE_MISSING 3건
- `s100-manual` 결측 26건 → CELL_SPLIT 26건
- `s100-manual`: 기대 라벨 `CELL_SPLIT` — 결측 26건 중 26건 일치 → **기대대로**
- `ig5a-manual`: 기대 라벨 `SOURCE_MISSING` — 결측 11건 중 3건 일치 → **기대와 다름**
- iG5A 불일치의 원인은 라벨 규칙이 아니라 **양성 축의 적용 범위**다. iG5A 추출은 코드 토큰이 아니라 **한글 명칭**으로 조인하므로 표준본 본문에 코드 토큰이 거의 없다(§0 ANCHOR_CONFLICT). 즉 iG5A 에서 `code_tokens` 는 *소스 유무*를 재는 축이 아니다.
- iG5A 의 *소스를 바꾸면 풀리는가* 는 §3 보충 소스 탐침이 **독립적으로** 답한다. 그 결과를 라벨보다 우선해 읽을 것.

- 양성 축 합계: 코드 토큰 19건 ig5a-manual 4 · s100-manual 15

## 3. 보충 소스 탐침 (참고 — 라벨에 반영하지 않음)

- `ig5a-troubleshooting` 물리 p.20~29 · 텍스트 6683자 스캔
- '조치' 머리글이 나타난 페이지: [22, 23, 24, 25, 26, 27, 28, 29] (양성 축 — 비어 있으면 이 탐침 자체가 눈이 먼 것)
- iG5A 조치 결측 코드 11건 중 **명칭이 이 문서에 실재하는 것 10건**: ['COL', 'COM', 'EEP', 'ERR', 'ETB', 'FLTL', 'HWT', 'NTC', 'OLT', 'RERR']
- 명칭 미발견: ['EST']

## 4. 재-OCR 비용 추정 (산술만)

- 대상 `RE_OCR_CANDIDATE` **1페이지** × 45원 = **45원**
- 제외: SOURCE_MISSING 1페이지 · CELL_SPLIT 5페이지 · OK 0페이지 — SOURCE_MISSING 은 소스 교체, CELL_SPLIT 은 파서 수정 대상이라 재-OCR 로 풀리지 않는다.
- 산술 추정치다. 실제 구매·집행은 사람 승인 사안이며 이 모듈은 호출하지 않는다.

## 5. 이 계측기의 한계

- 코드 토큰 축은 **정규식이 실패하면 조용히 0** 이 된다. 그래서 두 번째 양성 축(`with_actions` = 같은 페이지에서 조치문 추출에 성공한 코드 수)을 함께 싣고, 둘이 모순하면 `anchor_conflict` 로 표시한다. 모순 표시가 붙은 줄의 `SOURCE_MISSING` 은 **근거가 없는 라벨**이다.
- 신호 문턱: 셀 길이 |z| ≥ 2.0 인 셀 비율 ≥ 0.1 · 행당 유효 셀 수 감소율 ≥ 0.35. 임의 문턱이며 판정을 뒤집을 힘은 없다(결측이 있는 페이지는 두 축이 먼저 라벨을 정한다).
- 문자 깨짐 계열 신호는 **의도적으로 넣지 않았다** — P31 실측에서 코퍼스 전체 0건이었고 한국어 나열 구분자를 고립 자모로 오탐한 전례가 있다.
- 페이지는 전부 PDF 물리 페이지다 (D26). 인쇄 페이지 환산은 하지 않는다 (D32).

