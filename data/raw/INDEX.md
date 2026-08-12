# `data/raw/` — 원본 데이터 대장

**이 디렉터리는 읽기 전용이다** (CLAUDE.md 절대규칙 5 · D19). 원본을 고치지 않는다 —
가공물은 `data/extracted/` · `data/analysis/` 로 나간다.
`.claude/hooks/guard_writes.py` 가 쓰기를 **코드로 차단**하며, 예외는 원본이 아닌 문서
2개(`manifest.json` · 이 파일)뿐이다. `.gitignore` 도 같은 2개만 예외로 둔다
(원본은 저작권·용량 때문에 git 에 올리지 않는다).

> 매뉴얼 PDF 3종의 **버전·해시·페이지 오프셋**은 이 문서가 아니라 [`manifest.json`](manifest.json)
> 이 정본이다. 추출 파이프라인이 그 파일의 `sha256` 으로 버전 변경을 감지한다.
> 여기서는 **"어느 디렉터리에 무엇이 있고 어디에 쓰이는가"** 만 적는다.

최종 확인: 2026-08-12 (중복 IE5 파일 삭제 반영)

---

## 1. LS ELECTRIC 인버터 매뉴얼 (PDF 5개 · 36.1MB)

**프로젝트의 뿌리.** 에러코드 정의 · 점검 절차 · 안전 경고의 유일한 근거다.
인용은 전부 **PDF 물리 페이지** 기준(D26)이고 표시 변환만 오프셋을 적용한다(D32).

| 파일 | 기종 | 쓰임 | manifest |
|---|---|---|---|
| `iG5A_User_Manual_Standard_KR_210303.pdf` | iG5A | **주 원천** — `error_codes` 24건 · 안전 기준 p.4 | ✅ `ig5a-manual` |
| `iG5A_Troubleshooting_Rev1.0_150415.pdf` | iG5A | 보조 — 조치 절차 보강 | ✅ `ig5a-troubleshooting` |
| `S100_Manual_Korean_V4.2.pdf` | S100 | **주 원천** — `error_codes` 41건 · 안전 기준 p.2. ⚠ `print_page_offset = 16` | ✅ `s100-manual` |
| `IE5_User Manual(Standard)_Kor_V1.0_200526.pdf` | IE5 | ⬜ **미사용** — 기종 enum 이 `iG5A`·`S100` 2종 고정(D6·D13) | ❌ |
| `IE5_User Manual(Simple)_Kor_V1.0_200617.pdf` | IE5 | ⬜ 미사용 | ❌ |

- 산출물: `data/extracted/error_codes.json` (**65건** — iG5A 24 + S100 41, 2026-07-28 사람 승인) ·
  `data/extracted/manual_chunks.jsonl` (**1,035청크 · 56.8만자**)
- ⛔ 원본 재배포 금지. 저작권 LS ELECTRIC — 비상업적 학습·포트폴리오 목적

---

## 2. 조달청 시설공통자재 가격 (xlsx 2개 · 약 280KB)

| 파일 | 내용 |
|---|---|
| `시설공통자재(기계설비).xlsx` | 기계설비 신품 단가 |
| `시설공통자재(전기,정보통신).xlsx` | 전기·정보통신 신품 단가 |

출처 [KSEIS](https://www.kseis.co.kr) · 쓰임 **신품 단가 기준선**(잔가*율*의 분모, 부품 단가 현실화)

---

## 3. `external/` — 공공데이터 (CSV 1개 · 3.3MB)

| 파일 | 규모 |
|---|---|
| `중소벤처기업진흥공단_자산거래중개장터 매물정보_20251231.csv` | **16,011행 · 23열** · 인코딩 **cp949** · 연 1회 갱신 · [data.go.kr](https://www.data.go.kr/data/15112833/fileData.do) |

- ⚠ **잔가율 값의 원천으로는 반증됐다 (D74).** 경과연수-가격 상관이 사실상 0 —
  호가는 연차가 아니라 기계 규격이 지배한다. 지금은 **"왜 실데이터를 못 쓰는가"의 한계 실증**
  으로만 인용된다(`data/analysis/residual_curve.md §4`)
- ⚠ **`확인불가` 함정**: 제조년월 "결측률"은 0% 지만 결측 대신 `확인불가` **문자열**이 채워져 있다.
  16,011 을 분모로 쓰면 전부 틀어진다 — 유효 표본은 **연도+가격 교집합 5,396건(33.7%)**
- 부수 소득: 이 CSV 분석이 **D68**(대상이 인버터가 아니라 호스트 설비여야 한다)을 낳았다

---

## 4. `DACON 236036 월간 데이콘 기계 고장 진단 AI 경진대회/` — 팬 소음 (**14.3GB**)

출처: [dacon.io/competitions/official/236036/data](https://dacon.io/competitions/official/236036/data)

| 항목 | 실측 |
|---|---|
| `train/` | **1,279개** `.wav` · 6.5GB |
| `test/` | **1,514개** `.wav` · 7.8GB |
| wav 형식 | **8채널 · 16,000Hz · 32bit IEEE float · 10.0초** · 개당 5.1MB |
| `train.csv` | `SAMPLE_ID, SAMPLE_PATH, FAN_TYPE, LABEL` — FAN_TYPE 0:639 / 2:640 |
| `test.csv` | `SAMPLE_ID, SAMPLE_PATH, FAN_TYPE` — FAN_TYPE 0:779 / 2:735 (**LABEL 열 없음**) |
| `sample_submission.csv` | `SAMPLE_ID, LABEL` — 제출 양식(전부 0 placeholder) |

> 8채널 16kHz 는 마이크 어레이 녹음 형식이다. 파일이 32bit float 라 파이썬 표준 `wave`
> 모듈로는 못 읽는다(`unknown format: 3`) — `soundfile`/`librosa` 가 필요하다.

### ⚠ 실측이 드러낸 두 가지 (쓰기 전에 반드시 알 것)

1. **`train.csv` 의 `LABEL` 은 1,279행 전부 `0`(정상)이다.**
   지도학습 분류가 아니라 **비지도 이상탐지**(정상만 학습 → 이상 판정) 과제다.
2. **라벨된 고장 샘플이 0건이다.** `test.csv` 에는 `LABEL` 열이 없고 정답은 공개되지 않는다.
   → **"실제 고장 사례"를 얻을 목적으로도 쓸 수 없다.** 시드 데이터 보강에도 부적합하다.

### 지금 MaintQ 에 쓰지 않는 이유

- **진단 경로에 오디오가 들어갈 자리가 없다.** MaintQ 는 `에러코드 텍스트 → lookup / RAG` 이고(D1),
  MCP 도구 15종 어디에도 오디오 입력이 없다(`04_MCP_TOOLS`)
- **대상 설비가 다르다.** 이 데이터는 **팬(fan)** 소리이고 MaintQ 의 대상은 인버터(iG5A·S100)와
  호스트 설비다. `model` 은 enum 2종 고정(D6·D13)
- **위 ②** — 고장 라벨이 없어 "고장 데이터"로도 못 쓴다
- 14.3GB 는 git 에 못 올리고, 멜스펙트로그램 등 **특징 추출 파이프라인이 별도로 필요**하다

**언젠가 붙는다면 어디인가**: 백로그 **P10(예지보전 연계)**. 다만 현재 P10 의 입력은
`error_history`(D29)라, 음향을 넣으려면 **입력 축을 하나 더 만드는 별도 설계**가 선행된다.
⛔ 지금 범위(완료 기준 5지표 · S1~S4 · 처분/취득)와는 무관하다 — **07_BACKLOG 로 보낸다.**

---

## 5. 정리 대상 (사람 판단)

| 항목 | 조치 |
|---|---|
| IE5 매뉴얼 2종 | 기종 enum 밖이라 미사용. 보관 / 삭제 판단 필요 |
| DACON 14.3GB | 당장 안 쓴다면 외부 저장소로 옮길지 판단 필요(작업 디스크 점유) |
