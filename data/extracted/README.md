# `data/extracted/` — 파생 산출물 규약

이 디렉터리는 **추출·가공으로 만들어진 산출물의 정본(正本)** 이다. 원본(`data/raw/` 의 매뉴얼
PDF·외부 응답)에서 파이프라인을 거쳐 나온 것들이고, **전부 git 으로 추적한다**.

> **관할은 `data/extracted/` 다. 파생 산출물이 여기에만 있는 것은 아니다** — `data/iros/` 에 담보 통계 4건
> (`fetch_iros.py` 산출)이 있고 역시 git 추적이다. 아래 규약(§2·§3)은 **위치와 무관하게 파생 결과 전반에
> 적용**한다.

> **한 줄 규약 (D60)** — **원본은 파일(git)이 정본, DB 는 조회용 사본이다.**
> 재적재로 언제든 복원 가능해야 하고, **DB 를 지워도 근거는 남아야 한다.**

---

## 1. 지금 여기 있는 것

| 파일 | 만든 것 | DB 사본 |
|---|---|---|
| `error_codes.json` | `extract_error_codes.py` | ✅ `error_codes` 테이블 — 런타임 **질의 3종** (`lookup_error_code:71`·`create_po_draft:107`·**`data/hotspot_status.py:72` JOIN**) + **FK 의존 1종** (`create_repair_record`) |
| `residual_curve.json` | `build_residual_curve.py` | ✅ `residual_curve` 테이블 (`05_DB_SCHEMA §17`, D74) |
| `manual_chunks.jsonl` | `chunk_manual.py` | ❌ `mcp_server/rag.py` 가 **파일을 직접** 읽는다 |
| `ig5a_code_map.json` · `ig5a_action_map.json` | 추출 파이프라인 | ❌ 빌드타임 전용 |
| `extract_triage.json` | `extract_triage.py` | ❌ 빌드타임 전용 |
| `error_codes_actions.candidate.json` | `extract_error_codes.py --candidates-only` | ❌ 후보 파일 (D99) |
| `actions_absence_verification.json` | `verify_actions_absence.py` | ❌ 검증 리포트 |
| `ie5_code_candidates.json` | `extract_ie5_codes.py` | ❌ 후보 파일 (D99·D33, P29) |

---

## 2. 언제 테이블로 올리는가 — **게이트 조건 하나** (D106)

**"런타임 DB 질의 소비자(조인 포함)가 실제로 생겼을 때"만 올린다.**

*"SQL **조인**"* 으로 좁게 읽지 말 것 — 그러면 키 조회형인 `error_codes`(`lookup_error_code.py:71`)가
게이트를 통과하지 못하는데 그건 **이미 테이블이 있다.**

그 전에는 파일 그대로 둔다. 이유는 셋이다:

1. **D60 요구가 파일만으로 이미 충족된다** — git 추적 파일은 DB 를 지워도 남는다.
2. **사본이 하나 늘면 drift 축이 하나 는다** — 파일과 DB 가 어긋날 수 있는 경로가 생기고,
   그걸 막으려면 자가검증을 또 붙여야 한다 (아래 4단계 ④).
3. **소비자가 없는 테이블은 YAGNI 다** — D103 이 자기 선택지 ⓒ(파일+DB 사본 병행)를
   기각한 근거가 정확히 이것이다: *"지금 DB 조회 소비자가 0 이라 YAGNI"*.

**"나중에 필요할 것 같다"는 게이트를 통과하지 못한다.** 승격은 되돌리기 쉽고(아래 절차가
4단계뿐이다), 성급한 승격은 되돌리기 어렵다(회귀·문서·마이그레이션이 딸려 온다).

### 승격하지 **않아도** 되는 신호

- 소비자가 **빌드타임 스크립트**뿐이다 → 파일을 직접 읽으면 된다
- 소비자가 **한 프로세스 안에서 전량 로드**해 쓴다 → `mcp_server/rag.py` 선례 (`manual_chunks.jsonl`)
- **사람 검수 대기 중인 후보 파일**이다 → D99·D33. 승인 전에는 적재 자체가 금지다

---

## 3. 승격 절차 — 4단계

새 파생 결과를 올릴 때 **이 순서 그대로** 한다.

> **선례는 두 개고, 완전한 것은 하나도 없다.** `residual_curve`(D74)는 ①~③을 밟았지만 **④가 없다** —
> `seed.py` 검사 ⑯ 은 격자 내부 성질과 `assets` 조인만 보고 **파일↔DB 대조를 하지 않는다**(`spikes/` 참조 0건).
> 반대로 **`error_codes` 에는 ④가 있다** — 검사 **㉚** 이 DB 3행을 `error_codes_actions.candidate.json` 과 대조한다.
> 즉 **①~③은 `residual_curve`, ④는 `error_codes` 를 보고 베낀다.** 한쪽만 보면 ④를 빼먹는다.

### ① 정본 파일을 확정한다
- 산출 스크립트가 **멱등**해야 한다 — 같은 입력이면 같은 파일
- `_status` 로 사람 승인 상태를 표현한다면 **한국어 마커**를 쓴다
  (`data/extract_error_codes.py` 의 `DRAFT_MARKERS = ("초안", "승인 전")` · `is_draft_status()`)
- **git 추적을 확인한다** — `git ls-files --error-unmatch <파일>` 이 성공해야 한다.
  `git check-ignore` **만으로는 부족하다** — 그것은 *"무시되지 않음"* 만 보장하고, `git add` 전의 새 산출물은
  무시되지도 추적되지도 않은 채 그 검사를 **통과한다**

### ② `docs/05_DB_SCHEMA.md` 에 절을 신설한다
- 절 머리에 **정본 파일 경로를 명시**한다 — `> 정본은 data/extracted/xxx.json` (§17 형식)
- 조인 키를 명시한다 (§17 은 `(category, age_bucket)`)
- `docs/README.md`·`CLAUDE.md` 의 **테이블 개수 표기**가 함께 늘어난다

### ③ `data/seed.py` 에 로더를 붙인다
- 경로 상수 + `seed_xxx(con) -> tuple[int, str]` 함수 (`seed_residual_curve` 형식)
- **파일이 없으면 0행 + 경고이고 시드는 성공한다.** 죽이지 않는다 —
  `seed_residual_curve` 의 docstring 이 이유를 적어 뒀다: *"곡선이 없으면 소비 측 도구가
  `HOLD` 를 내는 게 정답이지, 시드가 죽어서 DB 자체가 없어지는 건 과잉이다."*
  이건 D62(*"모른다 → 통과"* 금지)와 같은 계열이다 — **없음을 없음으로 흘려보낸다**

### ④ 자가검증에 **drift 검사**를 추가한다 (이 단계를 빼면 승격하지 말 것)
사본을 만든 순간 **파일과 DB 가 어긋날 수 있는 축**이 생긴다. 그걸 잡는 검사가 없으면
승격은 **개선이 아니라 부채**다. **drift 대조 선례는 둘이다**:

- `seed.py` 검사 **⑬** — `law_refs` 사본 ≡ `laws/*.json` 파일 목록 (D60, **동적 대조**)
- `seed.py` 검사 **㉚** — `error_codes` DB 3행 ↔ `error_codes_actions.candidate.json` 대조
  (**이 디렉터리 산출물의 유일한 ④ 선례**)

> **검사 ⑭ 를 여기 끼워 넣지 말 것** — `rules` 5행 · 근거 없는 룰 0건만 보는 **적재 무결성** 축이고
> **파일과 대조하지 않는다**(`seed.py:2390~2395` 실측). ④가 요구하는 것은 *"두 사본이 어긋나면 잡는다"* 다.

**부재 검사에는 liveness 앵커를 함께 건다** — `not mismatch` 만으로는 *"사실이 참"* 과
*"쿼리가 0행을 봤다"* 를 구분하지 못한다. **대조 건수 > 0** 을 판정에 함께 넣고,
**detail 에는 결론이 아니라 두 축의 실측값**을 찍는다 (CLAUDE.md 회귀 절 · P30).

> `seed.py:2625` 주석이 같은 논리를 적어 뒀다 — *"하드코딩 4종으로 적으면 자산이 늘 때
> 대장 누락을 못 잡는다 (검사 ⑬ 과 같은 논리)"*. **동적 대조**를 쓴다.

---

## 4. 하지 말 것

- **원본을 여기에 두지 말 것** — 매뉴얼 PDF·외부 API 응답은 `data/raw/` 다.
  외부 응답은 `data/external/store.py` **한 곳**만 경유해 기입한다 (D103 ⓔ)
- **DB 를 정본으로 삼지 말 것** — `data/seed.py` 재실행이 테이블을 갈아엎는다.
  CLAUDE.md 가 **두 번의 실제 사고(MQ-708·MQ-713a)** 로 기록해 둔 사실이다.
  근거가 DB 안에만 있으면 **회귀를 한 번 돌리는 것만으로 증거가 소멸한다**
- **사람 검수 전 후보를 정본에 병합하지 말 것** (D99·D33)

---

## 5. 관련 결정

| D | 내용 |
|---|---|
| **D60** | 원본은 파일(git)이 정본, DB 는 조회용 사본 |
| **D74** | `residual_curve` 값 원천 — 승격 **①~③의 선례**(④는 없다, §3 경고 참조) |
| **D99** | 후보 파일 격리 — 사람 승인 시에만 정본 병합 |
| **D33** | 사람 승인 전 미적재가 기본 |
| **D103** | 외부 응답 원본 보관 (`data/raw/external/`) — 선택지 ⓒ 기각 근거가 §2 와 같다 |
| **D106** | 파생 결과의 DB 승격은 **런타임 DB 질의 소비자가 생겼을 때만** (이 문서 §2·§3) |
