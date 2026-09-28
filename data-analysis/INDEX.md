# `data-analysis/` — 실데이터 EDA · 전처리

**목적:** *"어떤 데이터를 얼마나 썼고, 어떤 컬럼을 새로 만들었는가"* 를 노트북으로 남긴다.
런타임(백엔드·MCP)은 이 디렉터리를 읽지 않는다 — 분석 전용이다.

> **원본을 복사하지 않는다.** `data/raw/` 는 읽기 전용이고 git 에도 없다
> (CLAUDE.md 절대규칙 5 · D60). 노트북은 `common.py` 의 경로 상수로 **제자리에서 읽고**,
> 산출물만 이 디렉터리 안으로 내보낸다. 그래서 `data-analysis/data/raw/` 는 **만들지 않았다.**

## 실행

```bash
uv sync --group analysis          # pandas·pyarrow·openpyxl·jupyter·nbstripout
uv run --group analysis jupyter lab
```

전체 재실행 (순서 중요 — `90`·`99` 는 앞 노트북의 산출물을 읽는다):

```bash
cd data-analysis/notebooks
for f in 01_* 02_* 03_* 05_* 06-1_* 90_* 99_*; do
  uv run --group analysis jupyter nbconvert --to notebook --execute --inplace "$f"
done
```

노트북 출력은 **커밋 시 자동 제거**된다 — `nbstripout` 이 git filter 로 걸려 있다
(`.gitattributes` 의 `*.ipynb filter=nbstripout`). 작업 중에는 출력이 그대로 남는다.

## 구조

```
common.py                  경로 상수 · profile() · top_values() · save_decisions() · save_processed()
notebooks/
  01_joonggomall_assets.ipynb        중진공 중고매물 CSV       16,011 × 23
  02_kseis_machinery.ipynb           조달청 기계설비 xlsx       2,201 × 12
  03_kseis_electrical.ipynb          조달청 전기·정보통신 xlsx  1,519 × 12
  04_iros_collateral_stats.ipynb     등기정보광장 통계 JSON       291 × 7
  05_law_articles.ipynb              법령 조문 JSON                8 × 15
  06-1_dacon_fan_sound.ipynb         DACON 팬소음 (미채택)     2,793 × 5
  07_error_codes.ipynb               에러코드 정의 JSON           65 × 11
  08_manual_chunks.ipynb             매뉴얼 RAG 청크 JSONL     1,035 × 7
  90_merge_and_features.ipynb        병합 · 파생 컬럼
  99_feature_mapping_report.ipynb    기능 매핑 → 보고서 생성
data/processed/            *.parquet  (git 제외 — 재생 가능)
reports/                   *_decisions.json · merge_decisions.json · preprocessing_report.md
```

번호 규칙 — `01~89` 데이터셋별 1개. **`NN-M` 접미사는 `90_merge` 에 참여하지 않는 독립 데이터셋**
(공통 join key 가 없는 것). `90` 병합·파생, `99` 기능 매핑 보고서.
`04` 는 IROS 통계였으나 `04_iros_collateral_stats.ipynb` 로 존재한다.

## 각 노트북 공통 섹션

1. 개요 (출처 URL · 수집일 · 원본 row/col)
2. 로드 + 기초 통계 — **컬럼 카탈로그**(dtype · null% · 고유값 · 예시값) + `head()`
3. EDA (분포 · 이상치 · 결측 패턴)
4. 전처리
5. `column_decisions` → `reports/{dataset}_decisions.json`
6. `data/processed/{dataset}.parquet`

## 현재 상태 — 10개 노트북 전부 실행 검증됨 (에러 0)

| 노트북 | 데이터 | 원본 | 사용 컬럼 | 기능 |
|---|---|---|---|---|
| `01_joonggomall_assets` | 중진공 자산거래중개장터 | 16,011 × 23 | 10 / 23 | 11, 12 |
| `02_kseis_machinery` | 조달청 기계설비 | 2,201 × 12 | 8 / 12 | 2, 11 |
| `03_kseis_electrical` | 조달청 전기·정보통신 | 1,519 × 12 | 8 / 12 | 2, 11 |
| `04_iros_collateral_stats` | 대법원 등기정보광장 4종 | 291 × 7 | 6 / 7 | 12 |
| `05_law_articles` | 법제처 법령 조문 | 8 × 15 | 12 / 15 | 7, 8, 9 |
| `06-1_dacon_fan_sound` | DACON 236036 (미채택) | 2,793 × 5 | 4 / 5 | — |
| `07_error_codes` | 에러코드 정의 | 65 × 11 | 9 / 11 | 1, 2, 4 |
| `08_manual_chunks` | 매뉴얼 RAG 청크 | 1,035 × 7 | 7 / 7 | 1, 5 |
| `90_merge_and_features` | 병합 | — | — | — |
| `99_feature_mapping_report` | 보고서 | — | — | — |

최종 산출물: **[`reports/preprocessing_report.md`](reports/preprocessing_report.md)**

비어 있는 기능 **3·6·10·13** 은 원천이 전부 `seed.py` 목업 DB 라 EDA 대상이 아니다.

> **`90` 은 자기 산출물을 다시 읽지 않는다** (`OWN_OUTPUTS` 로 제외). 두 번 돌려도
> `총 8개 · 23,923행` 으로 같다 — `assert len(sets) == 8` 로 잠가 뒀다.

## 이 노트북들이 실제로 잡아낸 것

원본 문서(`data/data_list.md`)와 **어긋난 것 5건**을 실행으로 확인했다. 전부 문서에 반영됨.

1. **`제조년월` 을 `to_datetime` 으로 파싱하면 81건이 조용히 사라진다** — `'2022'` 처럼 연도만
   있는 값 때문. 정규식으로 뽑아야 5,911건.
2. **"분석 가능 표본"은 단일 숫자가 아니다** — 가격 기준에 따라 5,475(≥1만) ~ 5,911(무관).
   `D72` 가 이미 `≥10,000 → 5,475` 로 고정했는데 `data_list.md` 만 옛 `5,396` 을 들고 있었다.
3. **카테고리 표기 변종이 6쌍** — 문서는 `'환경  설비'` 1쌍만 경고. 소수 변종에 **309행**이 묶여
   있어 원본 바이트 조인 시 조용히 빠진다.
4. **조달청 xlsx 는 설비 부품 카탈로그가 아니다** — 냉각팬·PCB·전원모듈·펌프·베어링 **전부 0건**.
   실제로 겹치는 건 케이블 958건과 전동기 21건뿐.
5. **IROS `tot` 의 단위가 서비스마다 다르다** (건 vs **원**). 모르고 합산하면 21조를 건수에 더한다.

### ✅ 확인된 것 (문제가 아니라 근거)

- **에러코드 65건 전부 인용 페이지에 청크가 있다** — 근거를 못 보여주는 코드 **0건**.
  기능 1의 신뢰도를 떠받치는 검사다. 단 페이지 단위 커버리지이지 내용 일치 검증은 아니다.
- **`(model, code)` 복합키가 필수인 이유** — 12종 코드가 두 기종에 겹친다(D6·D13).
  다만 갈리는 건 표기(12/12)·인용면(12/12)·심각도(**`HWT` 1건뿐**)이지 "다른 고장"은 아니다.
- **법령 조문 7건 해시 전건 무결** (`engine.text_hash` 기준).

### 검사기를 직접 짜다 틀렸던 것 (기록)

`05` 초안에서 `sha256(text)` 로 법령 해시를 검증했더니 **7건 전부 "불일치"** 가 나왔다.
실제로는 프로젝트가 **`"sha256:" + sha256(NFKC 정규화 + 공백 단일화)`** 를 쓴다
(`data/rules/engine.py`). **조문이 아니라 검사기가 틀린 것**이었고, 지금은
`engine.text_hash` 를 import 해서 쓴다 → **7건 전부 무결 확인**.

> 교훈: 무결성 검사는 **프로덕션과 같은 함수**로 해야 한다. 다시 구현하면 오탐이 난다.

`08` 초안에서는 `section` 컬럼을 *"섹션 제목이 아니라 본문 앞부분이라 못 쓴다"* 고 판정했다가
**뒤집었다.** 실측은 평균 **16.9자** · **90.8%가 절 번호로 시작**(`1.4 설치 위치 선정`) ·
60자 초과 **0건** 으로, **정상적인 섹션 제목이고 필터로 쓸 수 있다.**
`text.startswith(section)` 이 20.7% 라는 수치를 오해한 것이었는데, 그건 **각 절의 첫 청크에서
제목이 본문 맨 앞에 오는 게 당연**해서 나오는 값이다.

> 교훈: 고유값이 많다(346/1,035)는 것만으로 "오염됐다"고 판정하면 안 된다. **값 자체를 봐야 한다.**

관련 문서: [`data/data_list.md`](../data/data_list.md) (왜 가져왔나) ·
[`data/raw/INDEX.md`](../data/raw/INDEX.md) (디스크에 뭐가 있나) ·
[`docs/status/maintq-data-map.html`](../docs/status/maintq-data-map.html) (기능 ↔ 데이터)
