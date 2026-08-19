# Sprint 13 — `actions` 부재 주장 교차검증 + 외부 응답 원본 보관 (P31 · P28 ⓐ)

> 🔴 **번호 정정 (2026-08-19)**: 이 계획은 원래 Elice 도입 결정에 **D104** 를 예약했으나,
> 같은 브랜치에서 병행한 **LLM 응답 카세트 작업이 D104 를 먼저 등재**했다(커밋 `51f63ad`).
> 그래서 이 문서의 Elice 결정 번호를 **D105** 로 전부 옮겼다. ⚠ MQ-1307 착수 시
> `docs/10_DECISIONS.md` 의 **실제 마지막 번호를 다시 확인**할 것 — 병행 작업이 또 선점할 수 있다.

**상태**: 확정 (PM 계획 → tool-builder 평가 → 실측 검증 반영) · **평가 결론 Y(수정 필요) 전건 반영 완료** · **작성일**: 2026-08-19
**설계 근거**: [`docs/superpowers/specs/2026-08-19-actions-absence-verification-and-external-store-design.md`](../superpowers/specs/2026-08-19-actions-absence-verification-and-external-store-design.md) (사용자 승인 완료)

---

## 0. 착수 전 확정 사실 (실측)

### 0-1. 🔴 스펙 §3-1 "git 추적" 은 현재 `.gitignore` 와 충돌한다 — 설계의 구멍

`.gitignore:2` 가 `data/raw/*` 로 디렉터리째 제외하고 예외는 `manifest.json`·`INDEX.md` 둘뿐이다. 실측:

```
data/raw/external/elice/test_p1.json    제외됨      ← 스펙은 이걸 추적하라고 한다
data/raw/S100_Manual_Korean_V4.2.pdf    제외됨      ← 유지돼야 한다
data/raw/manifest.json                  추적가능
```

또 **CLAUDE.md 절대규칙 5** 가 *"`data/raw/`는 읽기 전용 — git에도 올리지 않음"* 이다.

→ **설계를 바꾸지 않고 진행하되**, `.gitignore` negation(MQ-1302) + **절대규칙 5 예외 명문화**(MQ-1311)가 **명시적 태스크로 필요**하다. `data/raw/*` 가 디렉터리를 통째로 제외하면 git 이 하위로 내려가지 않으므로 `!data/raw/external/` 로 **디렉터리를 먼저 되살려야** 하위 negation 이 동작한다. D103 본문에 *"절대규칙 5 의 예외를 이 결정이 만든다"* 를 명시한다.

### 0-2. 의존성 — PM 초안의 판단을 정정했다

| 항목 | PM 초안 | **실측 정정** | 채택 |
|---|---|---|---|
| HTTP | `requests` 없음 → `httpx` 이식 | ✅ 맞다. `httpx>=0.28.1` 이 **직접 선언**돼 있고 `fetch_laws._get_json` 이 지연 import 선례 | **`httpx`** |
| PDF 분할 | `pypdfium2` 없음 → `uv run --with pypdf` | ❌ **틀렸다.** `pypdfium2` 는 **설치돼 있다** — 출처는 `pdfplumber -> pypdfium2>=5.9.0`. 반대로 `pypdf` 는 **설치돼 있지 않다** | **`pypdfium2` 를 `pyproject.toml` 에 직접 선언** |

`pypdfium2` 는 지금 *선언된 직접 의존성(pdfplumber)이 보증하는 전이 의존성*이다. 동작은 하지만 pdfplumber 가 의존성을 바꾸면 조용히 깨지므로 **직접 선언으로 승격**한다. 이식 코드는 InsuQ 원본 그대로 쓸 수 있어 변경면이 오히려 줄어든다. (`requests` 도 `google-genai -> requests` 로 들어와 있으나 `httpx` 가 있으므로 쓰지 않는다.)

### 0-3. 범위 판단 — 백로그 승격이 아닌 이유

P28 ⓐ·P31 은 `07_BACKLOG.md` 항목이다. `/sprint` 스킬의 가드(*"백로그 항목을 태스크로 승격 금지"*)는 **P1~P20(v2 기능 목록)** 을 가리키며, P28·P31 은 그 범위 밖의 **인프라·데이터 품질** 항목이다. 근거 셋: ⓐ 2026-08-19 **사용자 승인 완료 스펙**이 있다 ⓑ 같은 세션에 P30 을 같은 방식으로 완료한 선례가 있다 ⓒ `actions` 결측은 `lookup_error_code` 출력 품질 = **S1·S3·S4 관통 데이터 축**이다.

⚠ 단 **P28 ⓐ 계열 2태스크(MQ-1301·1305)는 S1~S4 직접 복무가 아니라 인프라 규약**이며 직접 소비자는 확장 범위 S10(처분 증빙)이다 — 숨기지 않고 명세에 적었다.

---

## 1. 스테이지 계획 (5단 — 스펙 §9 초안 4단에서 재배치)

### 재배치 근거 둘

1. **§9 Stage 1 은 병렬이 불가능하다.** `fetch_laws` 소급은 보관 모듈이 먼저 있어야 하고, 스파이크는 그 둘의 결과를 검사한다. 한 스테이지에 넣으면 병렬 에이전트가 서로를 기다린다.
2. **지출 스테이지를 마지막으로 뺀다.** `/stage` 는 번호 순서로 돈다. 지출 스테이지가 중간이면 승인이 안 났을 때 뒤 스테이지가 통째로 멈춘다. 지출을 **Stage 5** 로 보내고 **Stage 3 에서 대조 엔진을 캐시 0건 dry-run 으로 완주**시키면, 승인이 영영 안 나도 스프린트는 Stage 4 에서 정직하게 닫힌다(전건 `INCONCLUSIVE` + `NOT_READ` 경고).

§9 와의 대응: §9-1 → Stage 1+2(1305) · §9-2 → Stage 2+3 · §9-3 → **Stage 5** · §9-4 → Stage 4.

### Stage 1 — 보관 규약 기반 (네트워크 0 · 지출 0)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1301 | 외부 응답 원본 보관 모듈 신설 (P28 ⓐ 규약 구현체) | `data/external/store.py` | — |
| MQ-1302 | `data/raw/external/` git 추적 경계 확정 | `.gitignore` · `data/raw/external/README.md` | — |
| MQ-1303 | **D103** 등재 | `docs/10_DECISIONS.md` | — |
| MQ-1304 | ① triage **현 스냅샷 검증** (재실행 아님 — 2026-08-19 산출본이 이미 최신) | (검증만, 산출물 무변경) | — |

### Stage 2 — 보관 모듈의 소비자 2종 (네트워크 0 · 지출 0)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1305 | `fetch_laws._fetch_with_meta` 의 버려지던 `payload` 소급 보관 | `data/rules/fetch_laws.py` | MQ-1301 |
| MQ-1306 | Elice DocVision 클라이언트 이식 (지출 가드 포함) + `pypdfium2` 선언 | `data/external/elice_docvision.py` · `pyproject.toml` | MQ-1301 · MQ-1302 |
| MQ-1307 | **D105** 등재 | `docs/10_DECISIONS.md` | MQ-1303 (같은 파일) |
| MQ-1308 | Elice 지출 가드 pytest 이식 (13건) — **Stage 3 → 2 이동** | `data/external/test_elice_docvision.py` | MQ-1306 (스테이지 내 순차) |

⚠ **MQ-1308 을 여기로 옮긴 이유**: 지출 가드 테스트가 구현보다 늦으면 **Stage 2 종료 시점에 레포에 검증 안 된 유료 클라이언트가 남는다.** 스펙 §4 의 규율과 어긋난다. 파일 충돌은 0이라 같은 스테이지에서 순차로 처리하면 된다.

### Stage 3 — 대조 엔진 + 회귀 신설 (네트워크 0 · 지출 0 · **dry-run 산출**)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1309 | ③ 3자 대조 엔진 + 검수 패키지 렌더러 (캐시 0건에서도 완주) | `data/verify_actions_absence.py` · `data/analysis/actions_absence_verification.md` · `data/extracted/actions_absence_verification.json` | MQ-1304 · MQ-1306 |
| MQ-1310 | 신규 스파이크 `external_store_contract` (30→31) | `spikes/external_store_contract.py` | MQ-1301 · MQ-1305 · MQ-1306 · **MQ-1309** |

⚠ **MQ-1310 선행에 MQ-1309 를 추가했다** — 검사 ⓛ(판독 계획 산술)·ⓜ(판정 매트릭스 오라클)이 **MQ-1309 의 모듈을 임포트해야** 성립한다. Stage 3 은 **2페이즈**(MQ-1309 → MQ-1310)로 돈다.

### Stage 4 — 회귀 · 기준선 · 문서 마감 (지출 0) — **Stage 5 에 의존하지 않는다**

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1311 | 회귀 전수 재실행 + 기준선 갱신 + **절대규칙 5 예외 명문화** | `CLAUDE.md` | Stage 3 전건 |
| MQ-1312 | 백로그 P28·P31 상태 갱신 + 문서 정합 (⛔ `CLAUDE.md` 안 만짐) | `docs/07_BACKLOG.md` · `docs/README.md` · 스펙 문서 주석 | Stage 3 전건 |

### Stage 5 — 🔴 사람 승인 후 실판독 (지출 **1,530원**) — 순차

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1313 | Elice 실판독 34페이지 + 캐시 커밋 | `data/raw/external/elice/*.json` | 🔴 승인 · MQ-1309 |
| MQ-1314 | 대조 재실행 → 검수 패키지 확정 + 결과 반영 | `data/analysis/*` · `data/extracted/*` · `TODO_직접할일.md` · `docs/07_BACKLOG.md` | MQ-1313 |

---

## 2. 파일 충돌 매트릭스

| 파일 | 태스크 | 스테이지 | 판정 |
|---|---|---|---|
| `data/external/store.py` | MQ-1301 | 1 | 단독 |
| `.gitignore` · `data/raw/external/README.md` | MQ-1302 | 1 | 단독 |
| `docs/10_DECISIONS.md` | MQ-1303 / MQ-1307 | **1 / 2** | ⚠ 분리 필수 |
| `extract_triage.md` · `extract_triage.json` | MQ-1304 | 1 | 단독 |
| `data/rules/fetch_laws.py` | MQ-1305 | 2 | 단독 |
| `data/external/elice_docvision.py` · `pyproject.toml` · **`uv.lock`** | MQ-1306 | 2 | 단독 (MQ-1308 은 읽기만) |
| `data/external/test_elice_docvision.py` | MQ-1308 | **2** | 단독 |
| `data/verify_actions_absence.py` | MQ-1309 | 3 | 단독 |
| `actions_absence_verification.md` · `.json` | MQ-1309 / MQ-1314 | **3 / 5** | ⚠ 분리 — 3 은 dry-run, 5 가 확정본 |
| `spikes/external_store_contract.py` | MQ-1310 | 3 | 단독 |
| `CLAUDE.md` | **MQ-1311 단독** | 4 | ⚠ MQ-1312 에서 제외 |
| **D 범위 표기 5파일** — `CLAUDE.md:12` · 루트 `README.md:122` · `docs/README.md:17` · `.claude/agents/reviewer.md:3` · `docs/status/maintq-status.html:805` | **MQ-1311 단독** | 4 | 🔴 **초안 정정.** `D1~D102` 문자열은 `10_DECISIONS.md` 에 **없다**(실측). MQ-1303·1307 이 이 갱신을 맡으면 Stage 1·2 가 `CLAUDE.md`·`docs/README.md` 를 건드려 Stage 4 단독 소유가 깨진다 → **MQ-1311 한 곳으로 집중** |
| `docs/06_REPO_API.md` | MQ-1312 | 4 | repo tree 의 `spikes 29종`(이미 낡음 → 31) · `data/` 하위 신규 · `.gitignore` 설명줄 갱신 |
| `docs/07_BACKLOG.md` | MQ-1312 / MQ-1314 | **4 / 5** | ⚠ 분리 |
| `data/raw/external/elice/*.json` | MQ-1313 | 5 | 단독 |
| `TODO_직접할일.md` | MQ-1314 | 5 | 단독 |
| `.claude/hooks/guard_writes.py` | **Stage 1 사후 추가**(사용자 승인) | 1 | `data/raw/external/README.md` 쓰기 예외 1건. **캐시 JSON 은 계속 차단** — `store.py` 가 파이썬 `os.replace` 로 쓰므로 PreToolUse 훅을 타지 않아 파이프라인은 안 막히고 손편집만 막힌다 |

**같은 스테이지에서 같은 파일을 쓰는 태스크 0건.**

---

## 3. 사람 게이트

| 게이트 | 위치 | 막는 것 | **막지 않는 것** |
|---|---|---|---|
| 🔴 Elice 실호출 1,530원 | Stage 5 진입 | MQ-1313 · MQ-1314 | **MQ-1301~1312 전부.** 대조 엔진은 캐시 0건에서 전건 `INCONCLUSIVE` + `NOT_READ` 로 완주하고, Stage 4 는 판독 결과에 의존하지 않는다 |
| D99 재승인 (정본 병합) | Stage 5 **이후** | 없음 — 이번 스프린트에 정본 쓰기 태스크가 **0개** | 전부. `RECOVERABLE` 은 **다음 스프린트** 사안 |
| (기존) 안전문구·A2A·API 키 | — | 없음 | 이 스프린트는 에이전트 루프·평가·DB 를 건드리지 않는다. ⛔ **재시드 금지** |

---

## 4. 회귀 영향 예측

| 항목 | 현재 | 예상 | 근거 |
|---|---|---|---|
| spikes 스위트 | **30** | **31** | `external_store_contract` 신설 |
| spikes 총 건수 | **872** | **887 ± 3** (러너 출력이 기준) | 신규 15건 설계. `law_fetch_contract 28` 은 네트워크 경로를 안 봐서 MQ-1305 로 불변 |
| pytest | **46** | **59** | Elice 지출 가드 13건. ⚠ **회귀 커맨드가 바뀐다** — 2파일 합산 |
| seed 자가검증 | 35 | **35 (불변)** | DB 미개봉 |
| 프론트 라우트 · `ui_honesty_contract` | 18 · 253 | **불변** | 프론트 무변경 → `next build` 재실행 불필요 |

---

## 5. 태스크별 상세 구현 명세

> PM 산출 명세를 그대로 따른다. 분량 관계로 이 문서에는 **계약면(인터페이스·판정식·DoD)** 만 싣고,
> 엣지 케이스 표 전문은 `/stage` 실행 시 tool-builder 에게 이 문서 + 설계 스펙을 함께 전달한다.

### 공통 규약

- **임포트 형식 고정**: `sys.path.insert(0, str(REPO_ROOT))` 후 `from data.external.store import …`. ⛔ `data/external` 을 path 에 넣고 `import store` 하는 형식을 **섞지 말 것** — `spikes/law_fetch_contract.py:33~34` 가 *"별개 모듈 객체가 되어 동일성 검사가 무의미해진다"* 는 같은 함정을 기록해 뒀다. `__init__.py` 는 두지 않는다(암시적 네임스페이스, `extract_triage.py:135` 선례)
- **네트워크는 `elice_docvision._submit_and_wait` 와 `fetch_laws._get_json` 두 함수 밖으로 나가지 않는다**
- 신규 파일 상단 독스트링에 **무엇을 지키는 모듈인지**(지출 가드·자격증명 제약·D 번호)를 적는다

### MQ-1301 — `data/external/store.py`

```python
STORE_ROOT: Final[Path]                  # <repo>/data/raw/external
SCHEMA: Final[str] = "maintq.external.v1"
SOURCES: Final[frozenset[str]] = frozenset({"elice", "law"})
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
ALLOWED_META: Final[dict[str, frozenset[str]]] = {
    "law":   frozenset({"law_ref_id", "article"}),
    "elice": frozenset({"source_pdf", "page", "doc_slug", "manual_id", "price_won"}),
}
class ExternalStoreError(RuntimeError): ...
def store_path(source, key) -> Path
def store_response(source, key, body, *, meta=None, retrieved_at=None) -> Path
def load_response(source, key) -> dict | None
def body_of(envelope) -> Any
def iter_stored(source=None) -> Iterator[Path]
def content_key(prefix, body) -> str      # f"{prefix}.{sha256(canonical)[:12]}"
```

저장 봉투: `{"_store": {schema, source, key, retrieved_at}, "_meta": {...}, "body": {...}}`

핵심 규칙 6개: ① source·key 검증(경로 이탈 차단) ② **메타 allowlist**(denylist 아님 — 요청 파라미터를 넣을 자리가 구조적으로 없다) ③ 환경 자격증명 값 스캔(⛔ 예외 메시지에 값 미포함) ④ `retrieved_at` UTC 기본(D39) ⑤ **내용 주소 멱등** — 동일 내용 재저장은 무동작, 상이 내용은 거부(append-only, D60) ⑥ tmp + `os.replace` 원자적 기입

🔴 **평가 반영 3건**
- **`STORE_ROOT` 파생 모듈 상수 금지.** `ELICE_DIR = STORE_ROOT/"elice"` 처럼 로드 시점에 파생시키면 MQ-1308 의 `monkeypatch.setattr(store,"STORE_ROOT",tmp_path)` 가 **무효**가 되고, 테스트가 실 캐시를 보다 캐시 미스 → **구매 경로로 갈 수 있다**. `store_path()` 는 **호출 시점에** `STORE_ROOT` 를 읽는다
- **멱등 비교 대상 확정**: `body`(+`_meta`)의 canonical JSON 만 비교하고 **`_store.retrieved_at` 은 제외**한다. 봉투 전체를 비교하면 재저장이 매번 "상이 → 거부"가 된다
- **자격증명 스캔 문턱**: 스캔 대상 변수명을 상수 목록으로 두고 **8자 미만은 스킵**한다. `LAW_API_OC` 는 이메일 ID 앞부분(4~8자)이라 짧은 값이 본문에 우연히 걸리면 `fetch_laws` 저장이 조용히 죽는다 — MQ-1305 가 예외를 삼키므로 **아무도 모른다**. 스킵 여부를 리포트에 실측 인쇄

**DoD**: `store_path('elice','x_p1')` → `data\raw\external\elice\x_p1.json` · `httpx`/`requests`/`urllib` import **0건** · `ruff check` 통과 · **파생 모듈 상수 0개**(뮤턴트 실증: 파생 상수를 심으면 MQ-1308 ⑦이 FAIL)
**결정**: D103(신설) · D60 · D39 · D62

### MQ-1302 — git 추적 경계

`.gitignore` 끝에 추가 (⚠ **순서가 계약이다** — `data/raw/*` 뒤에 와야 하고 디렉터리를 먼저 되살려야 한다):

```gitignore
# ── 외부 API 응답 원본 (D103) — 매뉴얼 PDF 와 달리 **추적한다**.
#    DB 를 지워도 근거가 남아야 하고, 원본은 파일이 정본이다 (D60).
#    ⚠ 마지막 두 줄이 급소다 — 없으면 캐시 디렉터리의 **단일 페이지 PDF 조각까지 추적**돼
#      매뉴얼 페이지가 커밋된다 (절대규칙 5 위반). 실측으로 확인했다.
!data/raw/external/
data/raw/external/*
!data/raw/external/README.md
!data/raw/external/*/
data/raw/external/*/*
!data/raw/external/*/*.json
```

응답 **JSON 만** 추적. 기존 `중소벤처기업진흥공단_…csv`(배포 데이터, 응답 아님)는 계속 제외되며 README 에 이유를 적는다.

🔴 **초안 패턴은 실측에서 탈락했다.** `!data/raw/external/**/*.json` 대신 `!data/raw/external/*/` 가 하위 **전체**를 되살려 `_tmp_s100_p412.pdf` 가 **추적가능**으로 나왔다. 두 패턴을 실제 `git check-ignore` 로 대조한 결과:

| 대상 | 초안 | **채택본** |
|---|---|---|
| `elice/s100_p412.json` | 추적가능 ✅ | 추적가능 ✅ |
| `elice/_tmp_s100_p412.pdf` | **추적가능 🔴** | **제외 ✅** |
| `data/raw/S100_Manual_….pdf` | 제외 ✅ | 제외 ✅ |
| `external/중소벤처…csv` | 제외 ✅ | 제외 ✅ |

**추가 방어**: Elice 클라이언트의 단일 페이지 임시 PDF 는 `tempfile.mkdtemp()` 로 **store 밖에** 쓴다 (MQ-1306).

**DoD** (4건 전부): JSON → rc=1 · **`_tmp_*.pdf` → rc=0** · 매뉴얼 PDF → rc=0 · 기존 CSV → rc=0
**결정**: D103 · D60 · ⚠ **절대규칙 5 예외 생성**(문구 정정은 MQ-1311)

### MQ-1303 / MQ-1307 — D103 · D105 등재

**D103**: 외부 응답 원본을 `data/raw/external/<source>/` 에 JSON 으로 **git 추적** 보관. **요청 파라미터·헤더 미저장.** 저장은 `store.py` **한 곳** 경유. 대안 ⓐ미추적(P28 자체 원칙 위반) ⓑDB(재시드 소실) ⓒ파일+DB(소비자 0, YAGNI). **반드시 포함**: 2026-08-13 평문 유출 → `git filter-repo` **커밋 10개** 재작성 이력 · **allowlist 로 구조 강제** · **절대규칙 5 의 예외를 여기서 만든다**

**D105**: Elice 를 **독립 2차 판독기**로 도입, **정답지로 취급하지 않는다.** 지출은 `allow_purchase` + 캐시 우선으로 게이트, 정본 반영은 D99 경유. 대안 ⓐ미도입 ⓑ정답지 삼아 자동병합(InsuQ 실측 오탈자가 반증 · **절대규칙 3** 위반 직결) ⓒ파서 우선수정(스펙 §1 비목표). **반드시 포함**: 판독 범위를 triage 권고보다 **33p 넓힌 것은 Claude 의 판단** · **회수 건수를 성공 지표로 삼지 않는다** · `CONFIRMED_ABSENT` 는 **양성 축이 살아 있을 때만** 낼 수 있다(P30)

**공통 DoD**: `docs/10_DECISIONS.md` 에 **각 1행 추가만.** 🔴 **D 범위 표기 갱신은 이 태스크가 하지 않는다** — `D1~D102` 문자열은 `10_DECISIONS.md` 에 **없고** 다른 5개 파일에 있다(실측). 갱신은 **MQ-1311** 소관이다. 여기서 건드리면 Stage 1·2 가 `CLAUDE.md`·`docs/README.md` 를 만져 충돌 매트릭스가 깨진다

### MQ-1304 — triage 재실행

⛔ `data/extract_triage.py` **수정 금지**. `INPUT_DRIFT`(기대 26/11 vs 실측 25/9)는 **정상** — `EXPECTED` 상수는 2026-08-14 before 스냅샷이라 **고치면 개선을 잴 기준이 사라진다**. `ANCHOR_CONFLICT` 2건도 정상이며 스펙 §8 대로 **그 라벨을 근거로 쓰지 않는다**.

**DoD**: 라벨 분포 `SOURCE_MISSING 1 · CELL_SPLIT 5 · RE_OCR_CANDIDATE 1`(스캔 7p) 유지 · 결측 `S100 25 / iG5A 9` · `error_codes.json` sha256 실행 전후 **동일**
**결정**: D99 · D26 · D65

### MQ-1305 — `fetch_laws` payload 소급

`_fetch_with_meta` 의 `payload = _get_json(...)` **직후**, `parse_article_response` **앞**에 `_store_payload(law_ref_id, article, payload)`.

- key = `content_key(law_ref_id, payload)` → 내용 주소라 같은 응답 재수집 시 파일이 안 늘고, 개정되면 새 파일이 는다
- meta = `{"law_ref_id", "article"}` **정확히 2개**. ⛔ `params`·`mst`·`jo`·헤더·`OC` 미전달
- 예외는 **삼킨다** — 경고 후 `None`, **수집은 계속된다**(스펙 §3-3 "기존 동작 불변"). ⛔ 메시지에 본문·인증값 미포함

🔴 **이 태스크는 `law_fetch_contract` 28건을 통째로 죽일 수 있다 — 지뢰 2종(실측 확인)**

1. **`spikes/law_fetch_contract.py:35` 는 30개 스파이크 중 유일하게 ROOT 를 `sys.path` 에 넣지 않는다** — `sys.path.insert(0, ROOT/"data"/"rules")` 뿐이다. 그 경로에서 `import data.external.store` → `ModuleNotFoundError: No module named 'data'`. **`fetch_laws.py` 최상단 임포트면 28건 전부 사망한다.**
   → `_store_payload` **안에서 지연 import + ROOT 부트스트랩**(`_get_json` 의 `import httpx  # noqa: PLC0415` 와 동형)
2. **같은 스파이크 ⓓ-2 는 `fetch_laws.py` 소스에 `hashlib`·`sha256(`·`unicodedata`·`NFKC` 가 없어야 PASS** 한다 — 부분문자열 스캔이라 `content_key` 를 인라인하거나 **주석에 "sha256" 이라 적기만 해도 FAIL**.
   → 해시는 반드시 `store.content_key()` 안에만 둔다

**DoD**: `uv run python spikes/law_fetch_contract.py` → **28건 PASS**(명시 항목) · **`fetch_laws.py` 본문에 `hashlib`·`sha256(`·`unicodedata`·`NFKC` 0건(주석 포함)** · `_store_payload` 본문에 `params`·`headers` 식별자 **0건** · `apply_fetch` 입력 계약 불변 · ⛔ 네트워크 실행은 DoD 에 넣지 않는다
**결정**: D103 · D60 · D75 · D30 성격

### MQ-1306 — Elice 클라이언트 이식

이식 원본과 **동일 시그니처 유지**(테스트가 이 계약에 묶인다). 원본 대비 바뀌는 것 **3가지**:

1. `requests` → **`httpx`**
2. `cache_dir` 파라미터 제거 → **`store` 모듈이 위치를 소유**
3. `_elements_of` 가 **봉투/생응답 둘 다** 수용 (`payload.get("body", payload)`)

⚠ **`pypdfium2` 는 원본 그대로 쓴다**(PM 초안의 `pypdf` 전환은 기각 — §0-2). 대신 `pyproject.toml` 에 **직접 선언**을 추가한다.

**핵심 순서 (지출 가드가 이 순서에 의존한다)**: ① 캐시 확인 **먼저**(있으면 `allow_purchase` 무관하게 네트워크 0) ② 미허용이면 `EliceError("캐시에 없다…")` ③ URL 정규화 + **`ELICE_API_KEY` 부재 시 지출 전 예외** ④ 단일 페이지 분할 제출 → 폴링 ⑤ store 기록

🔴 **초안의 자기모순 해소**: *"원본과 동일 시그니처 유지"* 와 *"`cache_dir` 제거"* 가 동시에 적혀 있었다. 원본 13건 중 최소 6건이 `cache_dir=`·`cache_path(tmp_path,…)` 를 쓰고 원본 슬러그 `"sf실손2607"` 은 `KEY_RE`(ASCII only)에 **걸린다** → "1:1 이식"은 성립하지 않는다.
**확정**: `extract_page(source_pdf, page, *, doc_slug, allow_purchase=False)` (**`cache_dir` 제거**). 슬러그는 manifest `id`(`s100-manual`·`ig5a-manual`·`ig5a-troubleshooting`). MQ-1308 문구도 *"13건 **의도** 1:1 보존, 캐시 위치 계약 변경분만 수정"* 으로 정정.
**추가**: 단일 페이지 임시 PDF 는 `tempfile.mkdtemp()` 로 **store 밖에** 쓴다 (MQ-1302 tmp PDF 방어와 짝).

**DoD**: `PRICE_PER_PAGE_WON == 45` · **캐시 확인 코드가 `_submit_and_wait` 호출보다 앞**(문자열 인덱스로 실증) · `requests` import 0건 · **네트워크 0회** · `uv.lock` 갱신 포함
**결정**: D105 · D103 · D9 성격 · D26

### MQ-1308 — 지출 가드 pytest 13건

원본 1:1 이식. 서두 문구 계승: *"최우선 목적은 '기능이 되는가'가 아니라 **'실수로 돈이 나가지 않는가'**"*.
1~5 URL 정규화(모델 ID 거부 포함) · 6 **캐시 미스+미허용 → 네트워크 없이 예외** · 7 **캐시 히트 시 네트워크 미접촉**(`_submit_and_wait` 를 폭파 스텁으로) · 8 **키 부재 시 지출 전 예외** · 9 가격 상수 · 10~13 파싱

⚠ 캐시 위치가 `store.STORE_ROOT` 로 고정됐으므로 **반드시 `monkeypatch.setattr(store, "STORE_ROOT", tmp_path)`** — 실 캐시 오염 방지. `pypdfium2` 경로에 닿으면 테스트 설계가 틀린 것.

**DoD**: 단독 **13 passed** · 2파일 합산 **59 passed** · 네트워크 0회

### MQ-1309 — 3자 대조 엔진 (핵심 태스크)

```python
READ_PLAN = (
    ReadTarget("s100-manual",          range(412, 426), "§9.1+§9.2+여유 (결측 25건)"),
    ReadTarget("ig5a-troubleshooting", range(20, 32),   "트러블슈팅 조치 구간+여유 (결측 9건)"),
    ReadTarget("ig5a-manual",          range(200, 208), "보호기능표+여유 (p.202 ANCHOR_CONFLICT)"),
)  # 14+12+8 = 34p
VERDICTS = ("CONFIRMED_ABSENT", "RECOVERABLE", "STILL_AMBIGUOUS", "DISAGREE", "INCONCLUSIVE")
PARSER_CLAIMS = ("ABSENT_IN_MANUAL", "AMBIGUOUS", "NOT_FOUND_ON_PAGE", "UNCLASSIFIED", "NO_CLAIM")
ELICE_AXES = ("ACTION_FOUND", "ROW_TEXT_ONLY", "ANCHOR_ONLY", "NO_ANCHOR", "UNREAD")
```

⚠ **구현이 이 초안 이후 축을 5종으로 늘렸다** (`ROW_TEXT_ONLY` 신설, `data/verify_actions_absence.py`
가 최신 소스 — 이 문서는 계획서일 뿐 구현 시점의 계약은 `docs/04_MCP_TOOLS.md` 가 아니라 코드
자신이다). 판독 범위의 1차 표(트립·보호기능표)에는 앵커 행마다 **항상** 긴 설명 셀이 있어,
그걸 `ACTION_FOUND` 로 세면 대조군이 자명 충족돼 리더 생존 검사(급소, 아래)가 원리적으로
발화하지 못한다(리뷰 C1) — 그래서 "앵커 행에 긴 이웃 셀이 있을 뿐"인 경우를 `ROW_TEXT_ONLY`
로 분리했다. 판정상으로는 `ANCHOR_ONLY` 와 동일하게 다룬다.

**판정 매트릭스 (구현 시점 실제 값 — 5열, `data/verify_actions_absence.py::_MATRIX` 가 정본)**

| 파서 \ Elice | ACTION_FOUND | ROW_TEXT_ONLY | ANCHOR_ONLY | NO_ANCHOR | UNREAD |
|---|---|---|---|---|---|
| `ABSENT_IN_MANUAL` | **DISAGREE** | **CONFIRMED_ABSENT** | **CONFIRMED_ABSENT** | INCONCLUSIVE | INCONCLUSIVE |
| `AMBIGUOUS` | **RECOVERABLE**(rowspan 1:1 귀속 시) / **STILL_AMBIGUOUS**(아니면) | DISAGREE | DISAGREE | INCONCLUSIVE | INCONCLUSIVE |
| `NOT_FOUND_ON_PAGE` | **RECOVERABLE** | DISAGREE | DISAGREE | INCONCLUSIVE | INCONCLUSIVE |
| `UNCLASSIFIED`·`NO_CLAIM` | RECOVERABLE | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE |

⚠ **`NO_ANCHOR` 는 절대 `CONFIRMED_ABSENT` 가 되지 않는다** — 양성 축이 죽은 상태에서 부재를 주장할 수 없다(P30 · D65).

---

#### 🔴 평가에서 드러난 결정적 누락 4건 (이게 없으면 1,530원이 전건 `INCONCLUSIVE` 로 끝난다)

**① 앵커 정의 — `error_name` 이 1차 축이다.** 실측: S100 9.2 조치사항표(p.420~421)의 항목 열은 **`Over Load`·`Over Current1`·`Out Phase Open` 같은 LCD 영문명뿐이고 코드 토큰이 한 개도 없다.** iG5A p.202 도 `code_tokens_found=0` 인데 6개 코드가 조치문을 갖는다 — triage 스스로 *"추출은 코드 토큰이 아니라 한글 명칭으로 조인한다"* 고 경고한다. **코드 토큰으로 앵커를 잡으면 대조군이 전멸하고 `READER_BLIND` 가 상시 발화해 판독 전액이 무효가 된다.**
→ **앵커 = {`code`, `display_code`, `error_name`} 정규화(대소문자·공백 무시) 매칭, `error_name` 이 1차.** `error_name` 은 정본에 이미 있다(S100=영문 LCD명 / iG5A=한글명). `FANW` 의 실제 셀이 `FAN Trip / FAN Warning` 병합이므로 **부분일치 허용**.

**② 축의 정의역 — 페이지가 아니라 "읽은 페이지 union(대상 문서 범위)" 단위다.** 앵커는 9.1(416~419)에, 조치문은 9.2(420~421)에 있다. **페이지 단위로 계산하면 모든 코드가 `ANCHOR_ONLY` 가 되고 대조군도 `ACTION_FOUND=0` → `READER_BLIND` 상시 발화.**
→ 이 전제에서만 `ABSENT_IN_MANUAL × ANCHOR_ONLY → CONFIRMED_ABSENT` 가 타당하다. **매트릭스 자체는 옳고 빠진 것은 정의역이었다.**

**③ `AMBIGUOUS × ACTION_FOUND → RECOVERABLE` 은 부당하다.** 파서가 멈춘 이유가 *"p.28 조치문이 5개 항목과 공유"* = **귀속 불가**인데, Elice 가 그 조치문을 읽어도 귀속이 안 되면 회수 후보가 아니다. 그대로 두면 **지어내기 압력이 생긴다(절대규칙 3).**
→ **`rowspan` 귀속이 1:1 로 풀렸을 때만 `RECOVERABLE`, 아니면 신설 `STILL_AMBIGUOUS`.** HTML 표 `rowspan` 처리 규칙을 명세에 포함한다 — p.420 의 `Over Load` 항목 셀은 3행을 span 한다.

**④ `_pending_review` 는 dict 가 아니라 문자열 35개**이고, 그중 **1건(S100 `FANW`)은 이미 회수돼 정본에 있다** → 초안의 "34/34 조인" DoD 가 35 vs 34 로 어긋난다.
→ 분류 정규식 4종을 명세에 고정. 실측 분포 `ABSENT_IN_MANUAL 28 · AMBIGUOUS 5 · NOT_FOUND_ON_PAGE 1 = 34` ✓. *"FANW 1건은 해소분이라 제외"* 를 리포트에 인쇄한다.

#### 대조군(`READER_BLIND`)은 실재한다 — 조건부

`error_codes.json` 의 `actions` 보유 31건을 판독 범위에 매핑한 실측:

| 판독 대상 | 대조군 후보 | 조치문 실재 위치 | 수 |
|---|---|---|---|
| `s100-manual` p.412~425 | `OCT`·`OVT`·`LVT`·`GFT`·`ETH`·`POT`·`IOL`(p.416) · `OHT`·`OC2`·`NTC`·`FAN`(p.417) · `OLW`·`ULW`·`FANW`(p.419) | **p.420~421** 9.2 조치사항표 | **16** |
| `ig5a-manual` p.200~207 | `IOL`·`OHT`·`POT`·`OVT`·`LVT`·`ETH`(p.202) · `FAN`·`ETA`(p.203) · `OCT`·`GFT`·`NBR`(p.204) | **p.205~206** 12.2 고장 대책표 | **13** |
| `ig5a-troubleshooting` p.20~31 | `RERR`·`ETB`(p.27) | p.27 | **2** ⚠ |

⚠ 세 조건: ⓐ **앵커를 `error_name` 으로 잡아야** 한다(①) ⓑ `actions_page` 는 31건 중 **3건만** 채워져 있다(D100: null = "출처 미기록") → 대조군 선정은 *"`actions` 보유 + 앵커 페이지가 판독 범위 안"* 으로 정의하고 **실제 발견 페이지를 리포트에 인쇄** ⓒ `ig5a-troubleshooting` 은 대조군이 **2건뿐**이라 대상별 판정 시 위양성 강등이 쉽다 → **대상별 판정을 쓰되 "대조군 2건, 통계적으로 약함"을 경고로 인쇄**한다.

🔴 **리더 생존 검사 (이 태스크의 급소)**: `control_codes()` — 판독 범위 안에 있으면서 **`actions` 가 이미 있는** 코드(iG5A `OCT` p.204, S100 `FANW` p.421 등)를 같은 알고리즘으로 찾는다. 초안 시점 생존 축은 "`ACTION_FOUND` 가 0건이면"이었으나, 구현 리뷰(C1)에서 **그 축 자체가 대조 대상과 무관하게 자명 참이 되는 결함**(판독 범위 1차 표에는 앵커 행마다 항상 긴 설명 셀이 있어 `ACTION_FOUND` 가 항상 ≥1이 됨)이 드러나 뒤집었다 — **생존 축은 정본 `actions` 문장 대조 통과 건수(`action_verified`)다.** `action_verified` 가 0건이면 `READER_BLIND` 경고 + **모든 `CONFIRMED_ABSENT` 를 `INCONCLUSIVE` 로 강등**한다. *"조치문이 실재하는 코드조차 못 찾는 판독기의 '없다'는 근거가 아니다."*

**조인 무결성**: 결측 34건이 `_pending_review` 사유와 34/34 매칭돼야 하고, 실패분은 `NO_CLAIM` 으로 **표에 그대로 싣는다**(조용히 버리지 않는다).

**지출 경로**: `--allow-purchase` 는 `--confirm-won <총액>` 이 `cost_estimate()["won_total"]` 과 **정확히 일치**할 때만 진행.

**DoD**: 인자 없이 실행 → **네트워크 0 · 지출 0**, 리포트 2종 생성, 전건 `INCONCLUSIVE`, `NOT_READ` 경고, exit 0 · `n_pages=34 · won_total=1530` · 조인 무결성 `34/34` 리포트 인쇄 · 정본·후보 파일 sha256 **불변**
**결정**: **D99**(정본 쓰기 0) · D105 · D103 · D26 · D32 · D65 · 절대규칙 3

### MQ-1310 — `spikes/external_store_contract.py` (15건 설계)

ⓐ 경로 규약 · ⓑ 미등록 source·경로 이탈 key 거부(4종) · ⓒ 봉투 round-trip · ⓓ **메타 allowlist**(`params`·`headers`·`Authorization`·`OC` 4종 거부) · ⓔ 멱등/상이 거부 · ⓕ `.tmp` 잔여 0 · **ⓖ 평문 자격증명 부재 + 양성 축** · ⓗ `.env.example` 키 이름 있고 실값 없음 · ⓘ `.gitignore` 3종(`git check-ignore`) · ⓙ `fetch_laws` 소급 지점 정적 검사 · ⓚ Elice 지출 가드 정적+실측 · ⓛ 판독 계획 산술(34p/1530원) · ⓜ **판정 매트릭스 오라클**(합성 8종, `NO_ANCHOR→INCONCLUSIVE`·`READER_BLIND` 강등 포함) · ⓝ store·verify 네트워크 미사용 · ⓞ 정본 불변(D99)

**ⓖ 의 양성 축 (P30 규칙 — 이 스파이크의 급소)**: 추적 파일이 0건일 수 있어 `bool(scanned)` 만으로 부족하다. **축 셋**: ① `leaks_real`(실제 추적 파일에서 환경값 검출 — 환경값 없으면 "미검증"을 detail 에 남기고 통과, `law_fetch_contract ⓚ` 선례, ⛔ 값을 스파이크에 적지 않는다) ② `scanner_alive`(**자격증명을 일부러 심은 합성 픽스처**가 반드시 검출되는지) ③ `scanned_total`. 판정 `not leaks_real and scanner_alive and scanned_total > 0`. ⛔ detail 에 `"유출 없음"` 류 결론 문구 하드코딩 금지.

⚠ `git` 부재/rc 이상은 **통과로 읽지 않는다**(FAIL + rc 인쇄). 실 캐시 유무 **양쪽에서** 통과해야 한다(Stage 3·5 에 두 번 돈다).

**DoD**: 전건 PASS · **뮤턴트 실증 2건** — ⓖ 스캐너를 `return []` 로 망가뜨리면 **ⓖ 만 FAIL**, `store_response` 의 allowlist 를 제거하면 **ⓓ 가 FAIL**

### MQ-1311 — 회귀 전수 + 기준선 + 절대규칙 5

31스위트 전수 재실행(실패 시 **단독 재실행 후 보고** — Windows 소켓 고갈 규칙) · pytest 2파일 합산 · CLAUDE.md 4지점: ⓐ 스위트 목록 30→31 ⓑ 건수표 + 총계 ⓒ **pytest 커맨드 갱신**(2파일) ⓒ' ✅ **D 범위 표기 갱신은 2026-08-19 `/done` 이 이미 처리했다**(`D1~D102` → `D1~D104`, 5파일: `CLAUDE.md`·루트 `README.md`·`docs/README.md`·`.claude/agents/reviewer.md`·`docs/status/maintq-status.html`). MQ-1311 은 **다시 하지 말고 실제 마지막 번호만 재확인**할 것 — Stage 2 가 D105 를 더하면 그때 또 밀린다. ⓓ **절대규칙 5 예외 명문화 — 예외가 셋이다**(reviewer W4): ㉠ **git 추적** 예외(응답 JSON + `data/raw/external/README.md`) ㉡ **쓰기** 예외(`README.md` 1건만, `.claude/hooks/guard_writes.py` 허용) ㉢ **캐시 JSON 은 사람·에이전트 손편집 금지**(`store.py` 단일 경유). ⛔ ㉡㉢ 을 빠뜨리면 훅과 문서가 어긋난 채로 남는다

⚠ 건수가 예측과 다르면 **예측이 아니라 실측을 적는다.** `ruff format` 은 돌리지 않는다(2026-08-19 선례). 프론트는 무변경이라 `next build` 재실행 불필요 — 그 사실을 기록에 명시.

### MQ-1312 — 백로그·문서 마감 (⛔ `CLAUDE.md` 안 만짐)

**P28**: ⓐ "미해소" → **"규약·구현체 완료(D103) · 소비자 2종 적용"**. ⓒ 는 그대로 부분.
**P31**: → **"교차검증 착수 — 대조 엔진 완성, 판독은 사람 승인 대기"**. ⛔ **완료로 적지 않는다** — 판독 전에는 "불일치 미해소"가 사실이고, 완료로 적으면 2026-08-19 에 방금 고친 낡은 기술이 재발한다.

### MQ-1313 / MQ-1314 — 실판독 · 확정 (Stage 5)

```
uv run python data/verify_actions_absence.py --allow-purchase --confirm-won 1530   # MQ-1313
uv run python data/verify_actions_absence.py                                       # MQ-1314 (캐시만, 지출 0)
```

캐시 우선이라 중단 후 재실행해도 산 페이지는 다시 사지 않는다. 캐시 34개를 **커밋한다**(D103).

결과 서술 규칙: `CONFIRMED_ABSENT` 다수 = **성공이다**(부재가 사실로 확정) — 회수 0건을 실패로 쓰지 않는다(스펙 §1). `READER_BLIND` 발화 시 **판정을 인용하지 않고** 1,530원이 헛돈이었다는 사실을 그대로 기록. `RECOVERABLE` 은 ⛔ 정본·후보에 **쓰지 않고** D99 게이트를 **다음 스프린트**로 넘긴다.

---

## 6. 열린 판단 · 착수 전 처리

### 6-1. 해소된 것

1. ~~`pypdf` vs `--with`~~ → **`pypdfium2` 직접 선언 확정**(§0-2, 실측)
2. ~~iG5A 트러블슈팅본에 p.31 이 있는가~~ → **있다.** 전수 46페이지
3. ~~`D1~D102` 갱신 주체~~ → **MQ-1311 단독**(5파일, 실측)

### 6-2. 🔴 Stage 3 이전에 반드시 확정 — 판독 범위와 금액

스파이크 ⓛ 가 `34p / 1,530원` 을 **산술로 고정**하므로 숫자를 먼저 정해야 한다. 평가가 **실측 근거로 9페이지(405원) 감축을 제안**했다:

| 구간 | 실측 소견 | 판단 |
|---|---|---|
| S100 p.412~414 | **9장이 아니다** — p.412 전체 기능표, p.413·414 는 17자 여백면. 9장은 **p.415 시작** | 제외 후보 (−3p) |
| S100 p.422~425 | 9.3 기타 문제(증상 키, 코드 없음) → 코드별 부재 판정 기여 **0** | 제외 후보 (−3p) |
| iG5A-TS p.29~31 | 2.2 기타 문제(증상 키) → 기여 **0** | 제외 후보 (−3p) |
| **iG5A p.201** | **pdfplumber 로 0자** — 이 스프린트에서 **가장 값이 큰 1페이지** | ⛔ 반드시 유지 |

감축 시 **25p · 1,125원**. ⚠ 다만 앞뒤 여유는 *"표가 구간 밖으로 이어지는가"* 를 보기 위한 것이라(스펙 §2-3) 감축은 **그 목적을 일부 포기하는 것**이다. → **Stage 3 dry-run 에서 페이지별 텍스트량을 실측한 뒤 사람에게 최종 확인**받고 확정한다. 승인 문서(`TODO_직접할일.md`)의 금액도 함께 갱신한다.

### 6-3. 남은 명세 재량

- **`ACTION_FOUND` 의 12자 문턱**은 임의값이다. 정본에 닿지 않아 느슨해도 안전하지만 **실측과 함께 리포트에 인쇄**한다(`extract_triage` 의 `thresholds` 절 형식)
- **MQ-1310 ⓖ 양성 축 구현 함정**: `git grep` 으로 스캔하면 합성 픽스처가 **추적 파일이 아니라 검출되지 않아** `scanner_alive` 가 원리적으로 발화 못 한다. → 스캔을 순수 함수 `scan(paths, needles)` 로 분리해 ① 실축은 `git ls-files` 목록에 ② 생존축은 tmp 픽스처에 적용. ⛔ **`git add` 로 우회 금지**(인덱스 오염)를 DoD 에 명시
- **spikes 건수 예측 887±3 은 "letter 1개 = check 1행"일 때만 성립.** ⓑ4종·ⓓ4종·ⓘ3종·ⓜ8종을 개별 행으로 내면 40건을 넘는다 → 명세에 *"ⓐ~ⓞ 각 1행"* 을 못박거나 예측을 **887~910** 으로 넓힌다. 어느 쪽이든 **최종 기록은 러너 출력**이다

### 6-4. 착수 전 액션

- **브랜치 분기**: 현재 `sprint-12-s29-ui` → `sprint-13-external-store` 신설 (머지는 요청 시에만)
- `TODO_직접할일.md §Sprint 13` 승인 항목은 **이미 등재돼 있다**(커밋 `ce92f04`)

---

## 7. 평가에서 기각한 지적 1건

tool-builder 가 *"CLAUDE.md 기준선이 낡았다(기록 871/252 vs 실측 872/253)"* 고 보고했으나 **실측 결과 틀렸다.** `CLAUDE.md:104` 는 이미 **872**, `:119` 는 **`ui_honesty_contract 253`** 이다(커밋 `28c4f69` 에서 갱신). 평가자가 본 `871` 은 `:158~160` 의 **과거 경위 설명 문단**(870→871 이 어떻게 나왔는지)이며 그 뒤에 `871→872` 문단이 이어진다. → **MQ-1311 에 "누락분 정정" 항목을 넣지 않는다.**

⚠ 이 건을 남겨 두는 이유: 다음 사람이 같은 문단을 보고 또 "낡았다"고 판단할 수 있다. **현재 기준선은 문서 상단(`:104`·`:119`)이고 하단 문단은 역사 기록**이라는 점을 여기 못박는다.

---

**실행**: `git switch -c sprint-13-external-store` 후 `/stage 1`

---

## Stage 1 완료 (2026-08-19)

**커밋**: `e647991` — `[M1] feat: Sprint 13 Stage 1 — 외부 응답 원본 보관 규약 (D103, P28 ⓐ)`
**브랜치**: `sprint-13-external-store` (master·sprint-12 미머지)

| TASK | 산출물 | 결과 |
|---|---|---|
| MQ-1301 | `data/external/store.py` (신규) | 왕복 시나리오 **28건 PASS** · 네트워크 라이브러리 참조 **0**(주석 포함) · 파생 상수 **0**(뮤턴트로 실증) |
| MQ-1302 | `.gitignore` · `data/raw/external/README.md` | `git check-ignore` **4/4** |
| MQ-1303 | `docs/10_DECISIONS.md` D103 | 1행 +0 −0 · 4셀 |
| MQ-1304 | (검증만) | 재실행 불필요 확인 — 산출물 무변경 |
| 사후 | `.claude/hooks/guard_writes.py` | README 쓰기 예외 1건(사용자 승인) · **5케이스 검증** |

**회귀**: spikes **30스위트 872건 · FAIL 0**(`mcp_client_contract` 연속 실행 시 1회 소켓 고갈 → **단독 재실행 통과**) · `ruff check` 통과 · ⛔ 재시드 안 함(DB 무개봉)

**reviewer**: **PASS** — 블로커 0 · 경고 5 · 참고 2. **경고 5건 전부 같은 커밋에서 해소**(W1 D103 문구 · W2 자격증명 스캔 우회 · W3 key 원문 인쇄 · W4 훅 미등재 · W5 판정 로직 이중화).

### Stage 2 로 넘어가는 미결

1. **`retrieved_at` 은 `+00:00` 로 확정** — D39 의 `...Z` 는 **API 전송** 규정이고 파일 계층 선례(`fetch_laws.py:677`)가 `+00:00` 이다. ⛔ **MQ-1310 이 `endswith("Z")` 로 단언하면 안 된다**
2. **`store.py` 공개 함수는 7개** — 명세의 6개 + `credential_scan_status()`. reviewer 가 *"오히려 요구된 것"*(P30 양성 축)으로 판정했다. ⛔ MQ-1310 이 "정확히 6개"로 잠그면 안 된다
3. **메타 값은 스칼라 제한**(`_META_VALUE_TYPES`) — 명세에 없던 추가 제약이나 D103 ⓓ 를 강화하는 방향이라 채택. 소비자 메타가 전부 스칼라라 파손 0
4. **참고 N1**(reviewer) — D103 ⓔ *"`store.py` 단일 경유"* 는 현재 강제 수단이 0이다. MQ-1310 에 *"`store.py` 외 모듈에 `raw/external` 경로 리터럴 0건 + 양성 축"* 정적 검사 1행 추가 권고
5. **참고 N2**(reviewer) — `store_response` 는 `exists()` → `os.replace` check-then-act 라 동시 실행 시 append-only 가 원리적으로 뚫린다. 단일 프로세스 스크립트라 실해 없음

---

## Stage 2 완료 (2026-08-19)

**커밋**: `4b8f8e8` — `[M1] feat: Sprint 13 Stage 2 — 보관 모듈 소비자 2종 + Elice 도입 (D105)`

| TASK | 산출물 | 결과 |
|---|---|---|
| MQ-1305 | `data/rules/fetch_laws.py` (`_store_payload` 신설 + 호출 1지점) | **지뢰 2종 회피 확인** — 금칙어 4종 실측 **0건**, import 는 419행 **함수 안 지연 import**. `law_fetch_contract` **28건 1회차 PASS** |
| MQ-1306 | `data/external/elice_docvision.py`(신규) · `pyproject.toml` · `uv.lock` | 캐시 확인(184행)이 `_submit_and_wait`(212행)보다 **앞** · `requests` 0건 · `pypdfium2>=5.9.0` 직접 선언 |
| MQ-1307 | `docs/10_DECISIONS.md` **D105** | 1행 +0 −0 · 4셀 · 요구 문구 3종 포함 |
| MQ-1308 | `data/external/test_elice_docvision.py`(신규) | **13 passed** · 실 캐시 디렉터리 미생성(격리 확인) |

**회귀**: spikes **30스위트 872건 · FAIL 0 · 재시도 0** · pytest **83**(rules 46 + llm_cache 24 + elice 13) · `ruff check` 통과 · ⛔ 재시드 안 함 · ⛔ 네트워크·지출 **0**

**reviewer**: **PASS** — Critical·Important·Minor **전부 0건**. 구현자 우려 3건 판단:
- `_elements_of` 의 `payload.get("body", payload)` — 오인 시 **fail-soft**(빈 리스트) 방향이고 판정 정본이 아니라 파싱 편의 함수 → 위반 아님. 실 Elice 스키마 검증 전까지 **관찰 항목**
- 임시 디렉터리 `rmdir()` 실패 무시 — 지출·정본과 무관한 부수 정리라 적절한 견고화
- `_no_network` autouse fixture — **"과보호가 아니라 D105 가 요구하는 수준의 방어"**(reviewer 판정)

### Stage 3 로 넘기는 미결

1. 🔴 **D 범위 표기가 또 낡았다** — D105 신설로 `D1~D104`(5파일)가 어긋났다. **한 세션에 두 번째**다(`/done` 이 D102→D104 로 맞춘 직후). **MQ-1311 이 반드시 처리**할 것
2. ⚠ `_elements_of` 의 봉투/생응답 정규화는 **실 Elice 응답으로 검증되지 않았다** — Stage 5 실판독 때 첫 응답에서 확인할 것
3. `uv.lock` 의 `pypdfium2` 잠금이 실제로 `uv sync` 가능한지는 육안 확인에 그쳤다(reviewer ⚠)

