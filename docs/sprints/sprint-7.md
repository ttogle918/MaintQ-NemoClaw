# Sprint 7 — S9→S10 관통 · S18 UI 정직성 · 3·4차 평가

**수립**: 2026-08-09 · **부제**: 설비를 팔 때와 살 때를 실제로 동작하는 수준까지

**사용자 지시**: *"S9→S10 을 정비사 콘솔 → 팀장 승인 큐까지 end-to-end. **BLOCKING 우회 처분 0건,
서명 없는 처분 확정 0건**이 실제로 막히는지 회귀로 증명. S18 은 **확인 안 된 항목을 확인된 것처럼
보여주는 UI 가 없는지** 특히 확인. **S17·`detect_law_revision` 은 v2 로 제외.**
완료 기준은 **위 3개 + `00_MVP_SCOPE §완료 기준` 5지표를 함께**."*

**선행 상태**: Sprint 6 전 스테이지 완료(`9999fc2`). 회귀 **414건**(spikes 396/21스위트 + seed 18) ·
결정 **D1~D88** · MCP 도구 **코어 7 + 확장 7 = 14종**(D69 프로파일 게이트, 기본 `core`).

---

## ⚠ 읽는 순서 — 이 문서의 우선순위

> **§개정 사항이 §태스크별 상세 명세보다 우선한다.**
> 명세는 PM 1차안이고, 개정은 tool-builder 가 **실호출·실측으로 검증한 뒤** 고친 것이다.
> 두 절이 충돌하면 **개정을 따른다.**

---

## 사용자 전제 중 이미 해소된 것 (실측 확인)

사용자는 *"룰 엔진 + 단위테스트는 있는데 MCP 도구로 안 연결됨"* 으로 알고 있었으나 **Sprint 6 이 오늘 해소했다**:

| 항목 | 상태 |
|---|---|
| `check_disposal_blockers` MCP 등록 | ✅ `server.py:216`(full 프로파일) |
| `verify_ownership` 9카테고리 | ✅ 자산당 38항목 · 9자산 전부 `PARTIAL` · **`PARTIAL→VERIFIED` 승격 분기 코드에 없음** · 상수·동적 이중 방어선 |
| S9 REST | ✅ `POST /api/assets/{id}/disposal/precheck` · D71 매핑 · 회귀 24건 |
| 처분 판정 5종 | ✅ 전부 재현. `CLEAR` 는 `SCRAP`·`TRANSFER` 에서만(D78, 전수 실증) |
| **`generate_disposal_document`** | ❌ 미착수 — **이번 스프린트의 본체** |
| **프론트** | ❌ Sprint 6 은 의도적으로 **프론트 0** — 승인 큐 공유가 통째로 남았다 |
| **서명 경로** | ❌ 없음 → *"서명 없는 확정 0건"* 을 아직 증명할 수 없다 |

## 🔴 `LAW_API_OC` 발급·검증 완료 — 계획의 최대 변수가 풀렸다

```
GET lawSearch.do?OC=<9자>&target=law&type=JSON&query=조세특례제한법  →  200 · totalCnt 3 · MST 280409
```

tool-builder 실호출 전수 결과: **7/7 조문 본문 도달 · 5/7 즉시 적용 · 2/7 정체성 대조에 걸림**.
이로써 `build_evidence_bundle` 이 **항상 `law_text_unavailable` 로 거부되던 게 풀리고 S10 이 실데이터로 관통 가능**해졌다.

### 🚨 실측이 잡은 함정 — `조문내용` 은 본문이 아니라 제목이다

```
조문내용          = '제32조(세금계산서 등)'              ← 15자, 이게 전부
항[0].항내용      = '① 사업자가 재화 또는 용역을 공급…'   ← 본문은 여기
항[0].호[0].호내용 = '1. 공급하는 사업자의 등록번호와…'
```

`text = 조문내용` 으로 매핑하면 `apply_fetch:239` 의 비어있지 않음 검사를 **통과**하고
**15자짜리 제목이 계층 1 "조문 원문"으로 해시되어 서명 번들에 실린다.**
`11 §2` 가 *"조문 원문을 손으로 타이핑하지 않는다 — 그 순간 출처 있는 사실이 아니라 누가 적은 텍스트가 된다"*
고 한 것과 같은 실패가 **자동 수집 경로에서** 일어난다.

**확정된 형식** (추측 구간이 사라졌다):
```
JO   = f"{int(article):04d}00"          # 6자리. '24'·'002400000' 은 HTTP 200 인데 조문 없이 침묵 실패
MST  = ?OC=..&target=law&type=JSON&query=..&display=100&search=1
#      display 기본 20 → 상법 실패 / search=2 는 본문검색이라 전 법령 실패
```

### 정체성 대조 2건 — D75 가 설계대로 막았다

| law_ref_id | 등록 title | API title | 처리 |
|---|---|---|---|
| `KR-STTC-146` | ~~`세액공제액의 추징`~~ | **`감면세액의 추징`** | ✅ **2026-08-09 사람 승인·정정 완료** |
| `KR-CITA-ENF-31` | `즉시상각의제` | `즉시상각의 의제`(공백) | ⬜ 승인 대기 — `classify_expenditure` 전용이라 **S10 무영향** |

`KR-STTC-146` 은 `TAX-CREDIT-2Y` 가 참조하므로, 정정 전에는 **세액공제 발화 자산 3건
(`AST-L3-CONV`·`AST-L4-WRAP`·`AST-L4-DUST`)의 번들·서명이 전부 막혀 있었다.**
정정으로 **서사가 가장 강한 BLOCKED 자산(blocker 2건)이 살아났다.**

---

## 스프린트 크기 판정 — 분할한다

**Sprint 7** = S9→S10 관통 + S18 UI + 3·4차 평가 / **Sprint 8** = S19 · `flags` · 잔여 튜닝

| 덩어리 | S7 | 근거 |
|---|---|---|
| 법령 실수집 `fetch_from_api` | ✅ | 없으면 `build_evidence_bundle` 이 **항상** 거부 → S10 이 시작조차 안 된다 |
| 번들 선행 조건 6건(W5·W6·W7·계약근거·N1·N2) | ✅ | **서명을 얹기 전에** 해야 한다. 서명 후에 고치면 **이미 서명된 해시가 무의미**해진다 |
| `generate_disposal_document` + 서명 API + 승인 큐 | ✅ | 요청 1번의 본체 |
| 프론트(승인 큐 3종 · 서명 UI · 자산 화면 2종) | ✅ | *"실제로 동작하는 수준까지"* 를 UI 없이 못 채운다 |
| S18 UI 정직성 | ✅ | 백엔드는 이미 완료 → **실질 작업은 UI + 회귀 + 로직 이관** |
| 3차 평가(측정) + 원인 분석 | ✅ | **코드 무변경.** 지금 안 재면 튜닝의 기준선이 영영 사라진다 |
| 4차 평가(튜닝 후 재측정) | ✅ | 1회 반복까지 계획에 포함 |
| `create_repair_record`(S19) | ❌ S8 | 지시에 없다. **`repair_records` 12건은 이미 시드돼 `get_maintenance_metrics` 가 소비 중** — S10 증빙 패키지는 **읽기**만 필요하고 그건 오늘 동작한다. 단 **큐는 3종을 전제로 설계**(`kind` enum 에 `repair` 포함, 항상 0건) → S8 이 계약 변경 없이 추가된다. **"3종으로 설계하고 2종을 구현한다"** |
| `flags` 발생·해소 | ❌ S8 | 요청 밖. `flags` 0행으로도 S9·S10 이 완결된다 |
| 증빙 패키지 해시 고정 | ❌ S8 | S7 은 **"고정되지 않는다"를 명시**하는 선까지(D86) |
| S17 · `detect_law_revision` | ❌ v2 | 사용자 명시 제외. ⚠ `check_revisions()` 는 이미 존재하고 MQ-701 이 `fetch_from_api` 를 채우면 **자동으로 살아난다 — 도구로 노출하지 않을 뿐**이다(MQ-712 가 문서에 명시) |

---

## Sprint 7 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---|---|---|---|
| **Stage 1** | MQ-701, 702, 703, 704 | ✅ 4병렬 | 조문 원문 **6/7 적용**(146 정정 반영) · 엔진 주입점·`facts_used` · **3차 평가 기준선** · 플래키 격리 |
| **Stage 2** | MQ-705 | — | 번들 5키 재설계 (W5·W6·W7·계약근거·N1·N2) |
| **Stage 3** | MQ-706, 707, **707b** | ✅ 3병렬 | 쓰기 도구 · 서명/승인큐 REST + DDL 2게이트 · **실사 로직 `data/` 이관 + `/ownership` REST** |
| **Stage 4** | MQ-708 | — | **BLOCKING 우회 0건 · 서명 없는 확정 0건** + S9→S10 스모크 |
| **Stage 5** | MQ-709a | — | 프론트 계약 전환(`kind` 도입, **`po` 만 렌더**) — 발주 흐름 무회귀 |
| **Stage 6** | MQ-709b, 710, 711 | ✅ 3병렬 | 처분 상세·서명 UI · S18 실사 화면 · S9→S10 진입 화면 |
| **Stage 7** | MQ-712, 713 | ✅ 2병렬 | 계약 문서 + D81~D88 전파 · 지표 튜닝 + 4차 평가 |

```
MQ-701 ─┬─────────────► MQ-705 ─┬─► MQ-706 ──┐
MQ-702 ─┘                        ├─► MQ-707 ──┼─► MQ-708 ─► MQ-709a ─┬─► MQ-709b ─┐
MQ-704 ──────────────────────────┴─► MQ-707b ─┘                       ├─► MQ-711 ──┼─► MQ-712
                                     MQ-707b ─────────────────────────┴─► MQ-710 ──┘
MQ-703 ──────────────────────────────────────────────────────────────────────────► MQ-713
```

### 스테이지 구성 근거

- **Stage 1 4병렬** — 파일 교집합 0 실측. 701=`fetch_laws.py`+`laws/`+2스파이크 /
  702=`engine.py`+`test_rules.py`+`services/disposal.py`+2스파이크 / 703=`eval/` / 704=stdio 스위트 3종
- **MQ-703 을 Stage 1 에 두는 이유** — ⓐ **코드를 한 줄도 안 고친다**(측정만) ⓑ 도구를 1종 더 얹기 **전에** 재야
  D69 기준선이 유효하다 ⓒ 튜닝은 원인 분석 산출물이 없으면 **추측 수정**이 된다
- **Stage 2 단독** — `build_evidence_bundle.py` 한 파일에 6개 이슈가 전부 걸린다. 그리고
  **서명을 얹기 전에 끝나야 한다** — 번들이 무엇을 고정하는지 모르는 채 해시에 사람 서명을 붙이면 그 서명이 무의미하다
- **Stage 3 3병렬** — 706=`mcp_server/` / 707=`backend/{services,routers}`+`main.py`+`seed.py` /
  707b=`data/ownership.py`+`verify_ownership.py`+`services/ownership.py`+`routers/disposal.py`.
  ⚠ **707b 는 `main.py` 를 건드리지 않는다** — `disposal.py` 라우터가 이미 `prefix="/api/assets"` 다
- **Stage 4 단독** — *"두 개의 0건"* 은 요청의 헤드라인이고 **도구(706)와 API(707) 양쪽을 동시에 관통해야만**
  증명된다. 어느 한쪽에 붙이면 **자기 코드를 자기가 검증**하는 구조가 된다
  (Sprint 6 Stage 4 에서 전용 회귀가 없어 블로커가 Stage 6 까지 살아남을 뻔한 것과 같은 실패를 미리 막는다)
- **Stage 5 단독** — `ApprovalQueueScreen`→`QueueList`·`PoDetail`→`DecisionBar` + `mappers.tsx`·`types.ts`·`api.ts` 가
  **한 덩어리**다. `poId`→`id`+`kind` 전환은 이 파일들을 **원자적으로** 바꿔야 하므로 병렬 불가
- **Stage 6 3병렬** — 709a 가 `lib/api.ts` 에 **신규 fetcher 전부를 한 번에** 넣고 닫으므로,
  Stage 6 의 세 태스크는 `api.ts` 를 **읽기만** 하고 각자 신규 컴포넌트·라우트만 만든다.
  ⚠ **710 은 711 의 `AssetHeader` 를 import 하지 않는다**(같은 스테이지 의존 금지) — 자체 최소 헤더를 만든다

### 공유 파일 단일 소유자 격리

| 공유 파일 | 유일 소유 | 스테이지 |
|---|---|---|
| `data/rules/engine.py` · `test_rules.py` · `backend/services/disposal.py` | MQ-702 | 1 |
| `data/rules/fetch_laws.py` · `laws/*.json` · `spikes/asset_tools_contract.py`(1차) | MQ-701 | 1 |
| `eval/run_eval.py` · `eval/score.py` | MQ-703 | 1 |
| `mcp_server/tools/build_evidence_bundle.py` · `asset_tools_contract.py`(2차) | MQ-705 | 2 |
| `mcp_server/server.py` · `db.py` · `backend/agent/prompts.py` · `prompt_rules.py` · `tools_profile_contract.py` | MQ-706 | 3 |
| `backend/main.py` · `data/seed.py` | MQ-707 | 3 |
| `mcp_server/tools/verify_ownership.py` · `backend/routers/disposal.py` | MQ-707b | 3 |
| `frontend/lib/{api,types,mappers,queueState}` · `components/queue/**` | MQ-709a | 5 |
| `docs/**` · `CLAUDE.md` · `README` | MQ-712 | 7 |
| `backend/agent/prompts.py`(2차) · `loop.py` | MQ-713 | 7 |

---

# 🔄 개정 사항 (tool-builder 실측 평가 반영) — **명세보다 우선**

tool-builder 평가: *"구조는 건전하다. 스테이지 분할 근거, 단일 소유자 격리, 뮤턴트 선행 확인,
4층 방어 설계는 모두 타당하고 실측과 대조해 오류가 거의 없다(414건 정확 일치, DDL·트리거·프론트 인용 전부 일치)."*
수정은 **범위 누락 1건 + 명세 보강 5건**.

## MQ-701 — 전면 개정

1. **`text` 는 `조문내용 + 항내용 + 호내용 + 목내용` 평탄화.** ⛔ `조문내용` 단독 금지(위 §함정)
2. `조문여부 == '조문'` 인 단위만 선택 — `'전문'`(절 제목)은 버린다.
   **`KR-OSHA-93`·`KR-STTC-24` 는 2건이 반환된다**
3. `조문시행일자` 는 `YYYYMMDD` → `effective_from` 은 `YYYY-MM-DD` 로 **변환**
4. `promulgation_no` 는 조문 단위가 아니라 응답 `기본정보` 에 있다
5. **⚠ JSON 을 채운 뒤 반드시 `uv run python data/seed.py --with-error-codes` 재실행** —
   `law_refs` 는 **DB 사본**이고(D60) 도구·REST 는 DB 를 본다. 재시드 없이는 파일만 바뀐다
6. ⛔ **정체성 불일치 자동 정정 금지** — `apply_fetch` 가 파일을 손대지 않고 중단하는 것이 정상이다
7. **DoD 변경**: 결과표에 `FETCHED 6 / MISMATCH 1 / FAILED 0`(146 정정 반영) ·
   **`FETCHED` 전 건에서 `len(text) > len(조문내용)`** ∧ **항 ≥1 인 조문은 `항내용` 첫 40자가 `text` 에 포함** ·
   재시드 후 `SELECT count(*) FROM law_refs WHERE fetch_status='FETCHED'` → **6** ·
   `law_fetch_contract` 6 → **8건**(ⓖ `조문내용` 만 담은 응답 → **적용 거부** · ⓗ `'전문'` 섞인 응답에서 `'조문'` 만 선택)
8. `data/analysis/law_fetch.md` 에 판정표 + `JO`·`display=100&search=1` 근거 + **평탄화 전/후 길이 대조표**

### S10 데모 자산 (`KR-STTC-146` 정정 후)

| 자산 | verdict | 인용 조문 | 번들 |
|---|---|---|---|
| `AST-L3-CONV` | **BLOCKED**(blocker 2건) | `KR-STTC-24`·`KR-STTC-146`·`KR-CIVIL-388` | ✅ **정정으로 살아남** |
| `AST-L2-SPDL` | CONDITIONAL | `KR-OSHA-93`·`KR-VAT-32` | ✅ |
| `AST-L3-LIFT` | SALE=CONDITIONAL / SCRAP=CLEAR | `KR-VAT-32` / (없음) | ✅ |
| `AST-L4-WRAP` | HOLD | `KR-STTC-24`·`KR-STTC-146` | ✅ |
| `AST-L4-DUST` | INSUFFICIENT_FACTS | `KR-STTC-*` | ✅ |

→ **MQ-708 의 임시 픽스처가 불필요해졌다.** 실 시드로 BLOCKED 경로 번들을 검증한다.
단 MQ-701 이 6/7 을 실제로 달성하지 못하면 픽스처로 되돌아간다(그 경우 스위트가 **"실 시드 아님"을 출력**).

## MQ-702 — 위험 진단 정정

- ❌ **삭제**: *"각 스위트가 4줄을 지역 중복"* — **`evidence_completeness` 를 단언하는 스위트는 0건**이다(전수 grep). 없는 문제였다
- ✅ **진짜 결합점**:
  ```python
  # mcp_server/tools/check_disposal_blockers.py:197-199
  if completeness == "LAW_TEXT_PENDING":
      disclaimer += _LAW_PENDING_NOTE
  ```
  > ⛔ **드리프트 검사에서 `disclaimer` 를 MCP 도구 출력 기준으로 단언하지 말 것.**
  > **MQ-701 이 조문을 채우는 순간 접미사가 사라져 값이 바뀐다.** `message` 를 대조에서 뺀 것과 같은 이유.
  > **`engine.DISCLAIMER` 와 REST 응답값을 직접 비교하고 MCP 출력은 쓰지 않는다.**

  **이 한 줄이면 Stage 1 4병렬이 안전하다.**
- `facts_used`·`laws_used` 키 추가는 **전수 키집합 단언 스위트가 없어 무회귀**

## MQ-703 — D88 이중 게이트

`/health.tools_profile` 은 **이미 존재**(`main.py:111`)하고 `run_eval.py:669` 가 **이미 `/health` 를 읽는다**
→ 신규 작업은 **가드 로직과 결과 기록뿐**이다.

```python
if (health.get("tools_profile") != "core" or (health.get("tools") or 0) > 7) \
   and not args.allow_full_profile:
    raise SystemExit(2)
```
`tools_profile` 은 `main.py:105` 가 **"참고값"으로 규정**한 env 에코라 단독 게이트는
**MCP 자식이 다른 env 로 떴을 때 통과**한다. `tools` 는 `list_tools()` 실측이므로 **둘을 겹친다.**

## MQ-704 — 보고 요건

실행에서 **3스위트 모두 1회 통과(플래키 미재현)**. DoD(연속 20회 0실패) 유지하되 보고에
**"미재현은 해결을 뜻하지 않는다 — 격리 적용은 `MAINTQ_DB` 경로 출력과 실 DB mtime 불변으로 증명한다"** 명시.

## MQ-705 — `laws[]` 범위 명확화 (중요)

| 필드 | 범위 | 해시 |
|---|---|---|
| `evidence_bundle.laws[]` | **4버킷에 실린 findings 의 `law_refs` 합집합만** | ✅ `text_hash` 필수 → `law_text_unavailable` 검사 대상 |
| `evidence_bundle.evaluated[]` | 평가된 **전** 룰의 `{rule_id, rule_version, verdict, law_refs[]}` | ❌ **ID 목록만** |

**근거**: W7 이 해소하려던 것은 *"어떤 룰을 평가해서 CLEAR 였는지"* 이지
*"평가만 하고 발화하지 않은 룰의 조문 원문까지 해시 고정"* 이 아니다.
후자를 요구하면 **미수집 조문 1건이 서명 경로 전체를 잠근다.** 이 경계를 코드 주석과 `04 §14` 에 남긴다.

**DoD 추가**: ⑮ `evaluated[]` 항목은 `text_hash` 키를 **갖지 않는다** ·
⑯ `KR-CITA-ENF-31` 미수집 상태에서 `AST-L2-SPDL` SALE 번들이 **성공**한다

## 🆕 MQ-707b — 실사 판정 로직 `data/` 이관 + `/ownership` REST (Stage 3)

> **B1 해소.** MQ-710 이 `GET /api/assets/{id}/ownership` 을 전제하는데 **그 엔드포인트가 없고
> 아무 태스크도 만들지 않았다.** `/api/assets` 라우터에는 `GET ""`·`GET /{id}`·`POST /{id}/disposal/precheck` 3개뿐이다.

- **변경 파일**: `data/ownership.py`(신규) · `mcp_server/tools/verify_ownership.py`(위임 래퍼로 축소) ·
  `backend/services/ownership.py`(신규) · `backend/routers/disposal.py` ·
  `spikes/asset_tools_contract.py` · `spikes/ownership_api_contract.py`(신규)
- **선행**: 없음

| 안 | 판정 |
|---|---|
| **(가) 9카테고리·`FIXED_UNVERIFIED`·`RISK_BY_ITEM`·`_verdict` 를 `data/ownership.py` 로 이관, MCP 도구는 위임** | ✅ **채택.** 650행 **순수 함수 + DB 조회** 모듈이라 위험이 낮다. D73 이 *"`data/` 는 두 프로세스가 공유해도 되는 데이터 계층"* 이라 **신규 결정 불필요** — `data.rules.engine` 선례와 동형 |
| (나) backend 재구현 | ❌ **MQ-702 가 지우고 있는 W2 드리프트를 새로 만드는 것.** 같은 스프린트 안에서 자기모순 |
| (다) 프론트 목업만 | ❌ 사용자 요청 2번의 증명 가치가 사라진다 |

```python
# data/ownership.py — mcp_server·backend 어느 쪽도 import 하지 않는다 (D15)
CATEGORIES: tuple[str, ...]              # 9종, 순서 고정
FIXED_UNVERIFIED: dict[str, tuple[tuple[str, str], ...]]
def verify(con, *, asset_id=None, equipment_id=None) -> dict:
    """반환은 현행 도구 출력과 **바이트 동일**. status/reason 체계 그대로 (D9)."""

# mcp_server/tools/verify_ownership.py — 얇은 래퍼
def verify_ownership(asset_id=None, equipment_id=None) -> dict:
    with read_only() as con: return data.ownership.verify(con, ...)
#   DESCRIPTION 은 이 파일에 남긴다 (04 §9 가 "코드 정본" 으로 인용)

# backend/routers/disposal.py 추가
GET /api/assets/{asset_id}/ownership     # 역할 게이트 없음 (D71 과 같은 이유 — 읽기 판정)
```

- **이관은 리팩터링이지 재설계가 아니다.** 로직·문안·상수를 **한 글자도 바꾸지 않는다.**
  바꾸고 싶은 것이 보이면 **보고하고 넘어간다**
- `backend/services/ownership.py` 는 `import data.ownership as _own` **모듈 참조**
  (Sprint 5 W1 의 `DB_PATH` 로드시점 고정 사고 회피). 커넥션은 **`mode=ro` URI**
- **HTTP 매핑**: `ok`→200 / `not_found`(`unknown_asset`·`unknown_equipment`·`no_host_asset`)→**404** /
  `error`→**500**. ⛔ **`PARTIAL` 을 409 로 만들지 말 것** — 실사 판정은 "지금 상태로는 불가"가 아니라
  **정상 결과**다. 409 로 주면 D71 이 처분 판정에 부여한 의미가 흐려진다
- `no_host_asset` 은 404 이되 본문에 사유를 싣는다 — **"문제 없음"이 아니다**
- **DoD**: ① **이관 동치 증명** — 이관 전 9자산 출력을 덤프해 두고 이관 후와
  `json.dumps(sort_keys=True)` **바이트 동일**. 다르면 실패 ② `asset_tools_contract` 48건 **전부 통과**
  ③ `ownership_api_contract` **신규 10건**(9자산 200+`PARTIAL` · 카테고리 9 · 38항목 ·
  `VERIFIED`엔 `evidence`/`UNVERIFIED`엔 `limit` · **REST==MCP 직접 대조** · 없는 자산 404 ·
  `INV-L1-01`→404 `no_host_asset`+사유 · **`PARTIAL` 이 409 아님** · `X-Role` 무관 · DB 행 수 불변)
  ④ `git grep "from mcp_server" backend/` → 0 · `git grep "from backend" mcp_server/` → 0
- **지켜야 할 결정**: D73 · D15 · D9 · D62 · D78 · `11 §6`

## MQ-708 — 3열 분리

- **`KR-STTC-146` 정정으로 임시 픽스처가 불필요**해졌다(위 §S10 데모 자산). 실 시드로 검증한다
- **전수 매트릭스 보정**: `law_text_unavailable` 로 draft 가 안 생기는 조합은
  **"우회 성공"이 아니라 "번들 불가"** 로 별도 집계. **두 실패를 한 칸에 뭉개면 게이트가 통과한 것처럼 보인다**
- **DoD 추가**: 매트릭스 출력에 `[서명거부 N] [번들불가 M] [서명성공 K]` **3열 분리**. `N+M+K == 대상 조합 수`

## MQ-709 → **709a / 709b 순차 분할**

> 개명이 아니라 **재작성**이다. `ApprovalQueueScreen` 의 상태가 `useState<ApiPo[]>`,
> 상세가 `getPo→toEvidenceEntries/toQuotes`, 결재가 `approvePo/rejectPo` 다.
> 파일은 14 가 아니라 **15개**(누락분 `app/(console)/manager/po/[poId]/page.tsx`).

**MQ-709a — 계약 전환 (Stage 5 단독)**
- `lib/types.ts` · `mappers.tsx` · `queueState.ts`(신규) · `api.ts`(**신규 fetcher 전부** —
  approvals·decisions·sign·assets·precheck·**ownership**) · `QueueList.tsx` ·
  `ApprovalQueueScreen.tsx` · `mock/queue.tsx` · `manager/page.tsx` · **`manager/po/[poId]/page.tsx`**
- **범위 제한**: `kind` 유니온·`stateView`·`detailHref`·`kind` 배지까지. **상세는 `po` 만 렌더**
- **DoD**: **기존 발주 승인 흐름 무회귀**가 유일한 판정 기준 — `api_contract` 28건 · `tsc`·`build` ·
  수동(발주 목록·상세·승인·반려·403/409/422 표시 이전과 동일) · `/api/approvals` 에 처분서가 섞여도 발주 렌더 무손상
- **DoD 정정**: `git grep "poId" frontend/**` → 0건은 **기계 검증 불가**다
  (`PoDraftCard`·`ChatThread`·`DiagnosticConsole`·`api.ts` 의 `poId` 는 정당하게 남는다).
  → **`grep -n "\.poId" frontend/components/queue frontend/components/screens/ApprovalQueueScreen.tsx` → 0건**

**MQ-709b — 처분 상세·서명 (Stage 6)**
- `DecisionDetail.tsx`·`SignBar.tsx`(신규) · `DecisionBar.tsx` · `EvidenceCard.tsx` ·
  `app/(console)/manager/decision/[decisionId]/page.tsx`(신규) · `ApprovalQueueScreen.tsx`(**분기 추가만**)
- 내용은 기존 명세 그대로(verdict 배너 · 4버킷 · 조문 칩 · `missing_sections` 강제 렌더 ·
  `hash_fixed:false` 표시 · `SignBar` override 게이트 · 409 `evidence_changed` 처리)

## MQ-710 — L3 제거 · 제약 추가

- **선행**: MQ-709a **+ MQ-707b**(엔드포인트 제공자)
- **검증 3층 → 2층**: L1 순수 함수 9건 · L2 소스 정적 4건 = **13건**.
  **L3(실 데이터 렌더) 삭제** — 서버 기동·자산 순회는 이 태스크의 검증 단위를 넘는다
- ⛔ **초록 위장 금지**: spike 출력 말미에
  **"L3(실 데이터 렌더)은 이 스위트가 검증하지 않는다 — 수동 체크리스트가 유일한 확인 수단이다"** 출력
- **제약 추가**: `lib/ownership.ts` 는 **React 를 import 하지 않는다** +
  **`@/` 경로 별칭도 쓰지 않는다**(`tsconfig.json` 에 `paths` 별칭이 있어 별칭을 쓰면 단독 `tsc` 가 깨진다).
  spike 가 두 가지를 단언
- **실행 검증됨**: `npx tsc check.ts --outDir out --module commonjs --target es2020 --skipLibCheck` → exit 0,
  `node out/check.js` → PASS, **신규 의존성 0**(node v22.14.0)

## MQ-712 · MQ-713 — 추가분

- **MQ-712**: `06 §2.5` 에 **`GET /api/assets/{id}/ownership`** · `11 §5` 에 **실사 로직이
  `data/ownership.py` 로 이관됐고 도구는 위임한다**(D73 적용 2번째 사례) ·
  `11 §8` 에 **`KR-CITA-ENF-31` 정체성 불일치**를 사람 승인 대기로 기록 ·
  **S17 은 v2 지만 `check_revisions()` 는 이미 존재하고 도구로 노출만 안 한다**는 사실 명시.
  신규 스위트 **6종** 반영
- **MQ-713**: 부품 특정은 **"미달"이 아니라 "판정 불가(`related_parts` 사람 승인 전, D12)"** 로
  **별도 행에 분리 기재**. 미달과 판정 불가를 한 칸에 쓰면 튜닝의 성패가 흐려진다.
  ⛔ **`SAFETY_BASELINE` 문구는 수정하지 않고 보고만 한다**(사람 승인 대상)

---

# 태스크별 상세 명세 (PM 1차안)

> ⚠ **위 §개정 사항과 충돌하면 개정이 우선한다.**

# 태스크별 상세 구현 명세

---

#### MQ-701 — 법제처 조문 원문 실수집 (`fetch_from_api`)

- **복무 시나리오**: S10 (근거 번들 → 서명). S9 의 인용 품질 향상은 부수
- **변경 파일**: `data/rules/fetch_laws.py`(수정) · `data/rules/laws/*.json`(데이터 갱신, 커밋) · `spikes/law_fetch_contract.py`(수정) · `spikes/asset_tools_contract.py`(수정) · `data/analysis/law_fetch.md`(신규)
- **⛔ 금지**: `engine.py`·`seed.py`·`build_evidence_bundle.py` 접근

- **인터페이스**
  ```python
  def fetch_from_api(law_ref_id: str, *, timeout: float = 10.0) -> dict:
      """반환: {"article": str, "title": str, "text": str,
                "clause": str|None, "effective_from": str|None,
                "promulgation_no": str|None, "source_url": str}
      예외: RuntimeError(키 미설정) · LawFetchError(신설, 네트워크·응답 형식·조문 부재)
      ※ apply_fetch 가 소비하는 dict 형태와 정확히 일치해야 한다 (fetch_laws.py:238-283)
      """
  def resolve_mst(law_name: str, *, timeout: float = 10.0) -> str: ...
  def _jo_param(article: str, clause: str | None = None) -> str: ...
  ```

- **핵심 로직 (순서를 지킬 것 — 코드 주석 `fetch_laws.py:70-73` 이 정한 순서다)**
  1. **키 재확인이 첫 단계다.** `lawSearch.do?OC=<값>&target=law&type=JSON&query=조세특례제한법` 을 호출해 `totalCnt > 0` 을 확인. ⚠ **키가 비어도 HTTP 200 이 온다** — 본문 `{"result":"필수입력요소 검증에 실패..."}` 를 반드시 검사할 것. 이 검사 없이 `json.loads` 성공을 성공으로 읽으면 조용히 넘어간다.
  2. `resolve_mst(law_name)` — 법령명 exact match 로 `MST` 확보. **동명이 여러 건이면 예외**(자동 선택 금지 — D50 태도). 7건의 `law_name` 은 5종(`조세특례제한법` 2건 공유·`부가가치세법`·`산업안전보건법`·`상법`·`민법`·`법인세법 시행령`).
  3. `lawService.do?OC=..&target=law&MST=..&type=JSON&JO=..` 로 조문 단위 조회. **`JO` 형식을 추측해서 박지 말 것** — 실호출로 확정하고, 확정된 형식과 그 근거(실제 요청 URL·응답 발췌)를 `data/analysis/law_fetch.md` 에 남긴다. 형식이 확인되기 전에는 `_jo_param` 을 구현하지 않는다.
  4. 응답을 `apply_fetch` 가 먹는 dict 로 정규화. **`article`·`title` 매핑을 빠뜨리지 말 것** — 법제처 필드명은 `조문번호`·`조문제목` 이고, 빠뜨리면 D75 의 정체성 게이트가 `LawMismatchError` 로 **정상 중단**시킨다(그게 설계된 동작이다).
  5. `apply_fetch(law_ref_id, fetched)` 호출. **`apply_fetch` 를 우회해 파일을 직접 쓰지 말 것** — 정체성 대조·2단계 기록(D75)이 전부 거기 있다.
  6. CLI 확장: `--fetch-all`(7건 순회, 건별 결과 표 출력) · `--pending`(Sprint 6 N-7 이월, `pending_revisions/` 열람).
  7. `check_revisions()` 의 `except` 에 **`OSError` 추가**(Sprint 6 N-7 이월) — 1건 실패가 전체 스캔을 중단시키지 않게.
  8. `_write_law`·`_confirm_pending_revision` 을 **`tmp + os.replace`** 원자적 쓰기로(Sprint 6 N-6 이월).

- **부분 실패 대응 (사용자 질문 3 — 반드시 이행)**
  - `--fetch-all` 은 **한 건 실패로 중단하지 않는다.** 7행 결과표를 출력하고 exit 0.
  - **우선순위**: `KR-VAT-32` > `KR-STTC-24`·`KR-STTC-146` > `KR-OSHA-93` > `KR-KCC-652` > `KR-CIVIL-388` > `KR-CITA-ENF-31`.
    근거: `VAT-INVOICE` 가 **모든 SALE precheck 에서 반드시 발화**하므로(D78 부수 확정) `KR-VAT-32` 없이는 어떤 매각 자산도 번들을 만들 수 없다. `KR-CITA-ENF-31` 은 처분 룰이 참조하지 않아 S10 에 무관하다.
  - **S10 진행 판정 기준을 `law_fetch.md` 에 표로 남긴다**:

    | 수집 결과 | S10 진행 방식 |
    |---|---|
    | 7/7 | 전 자산 번들 가능. 계획대로 |
    | `KR-VAT-32` 포함 부분 수집 | **SALE 데모 자산을 수집된 조문만 인용하는 자산으로 고정**한다. `law_fetch.md` 에 자산별 필요 조문 매트릭스를 싣고 MQ-708 스모크가 그 자산을 쓴다 |
    | `KR-VAT-32` 실패 | **SCRAP/TRANSFER 로 S10 데모를 전환**한다(`AST-L3-LIFT` SCRAP=CLEAR 실측). 단 CLEAR 자산은 `laws[]` 가 비므로 **D83 의 `evaluated[]` 가 있어야 번들이 의미를 갖는다** — MQ-705 가 이 경로를 반드시 커버 |
    | 0/7 (키 무효 등) | MQ-705 는 **합성 픽스처로만** 검증하고 MQ-706·707·708 은 `law_text_unavailable` 을 **1급 경로로** 테스트한다. UI 는 "근거 원문 미수집 — 서명 불가" 상태를 렌더한다. **스프린트는 멈추지 않는다** |

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | 키 미설정 | `RuntimeError` (기존 75-80행 유지) |
  | 200 인데 `{"result":"필수입력요소..."}` | `LawFetchError` — **성공으로 읽지 않는다** |
  | 조문번호·제목 불일치/누락 | `apply_fetch` 가 `LawMismatchError` → **파일 미수정**. 결과표에 `MISMATCH` |
  | 네트워크 타임아웃 | `LawFetchError`, 해당 행만 `FETCH_FAILED` |
  | 이미 FETCHED + 해시 상이 | `REVISION_PENDING` (덮어쓰지 않음, D60·D75) |
  | 조문이 여러 항으로 쪼개져 옴 | `clause` 에 담고 `text` 는 조 단위 통합. **조 단위 유지가 인용 앵커의 전제**(`11 §2`) |

- **지켜야 할 결정**: D59(법령은 룩업 — 벡터 인덱싱 금지) · D60(append-only) · D61(불변식 2) · D75(2단계 기록·정체성 대조) · D19(원본 읽기 전용)
- **DoD**
  - `uv run python data/rules/fetch_laws.py --fetch-all` → 7행 결과표 출력 · exit 0 · **네트워크 실호출**
  - `data/rules/laws/*.json` 중 `FETCHED` 인 건은 `text` 비어있지 않음 ∧ `text_hash` 가 `engine.text_hash(text)` 와 일치
  - `uv run python data/rules/fetch_laws.py --check` → 재실행 시 전부 `UNCHANGED` (멱등)
  - `uv run python spikes/law_fetch_contract.py` — 기존 25건 유지 + **신규 6건**: ⓐ `{"result":"필수입력요소..."}` → `LawFetchError` ⓑ `조문번호` 미매핑 응답 → `LawMismatchError`·파일 md5 불변 ⓒ `_jo_param` 이 확정 형식과 일치 ⓓ `check_revisions` 가 `OSError` 1건에도 나머지를 완주 ⓔ `_write_law` 원자성(중간 실패 시 원본 md5 불변) ⓕ `--pending` 열람. **네트워크 미사용**(모킹)
  - `uv run python spikes/asset_tools_contract.py` — 기존 48건 유지. `evidence_completeness`·`law_text_unavailable` 단언을 **`laws/*.json` 파생**으로 전환(하드코딩 0건)
  - `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **41 passed**(불변)
  - `data/analysis/law_fetch.md` 에 ⓐ 확정된 `JO` 형식 + 실제 요청 URL ⓑ 7건 결과표 ⓒ 자산별 필요 조문 매트릭스 ⓓ S10 진행 판정
  - `uv run ruff check data spikes` 통과

---

#### MQ-702 — 엔진 주입점 · `facts_used` 반환 · W2 복제 제거 · MCP↔REST 대조 확장

- **복무 시나리오**: S9·S10 (판정 원천 일원화 — 서명의 전제)
- **변경 파일**: `data/rules/engine.py` · `data/rules/test_rules.py` · `backend/services/disposal.py` · `spikes/disposal_api_contract.py` · `spikes/rules_db_load.py`
- **⛔ 금지**: `mcp_server/**` 접근 (MQ-705·706 소유)

- **인터페이스**
  ```python
  # engine.py:504 시그니처 확장 — 기존 위치 인자는 그대로
  def check_disposal_blockers(
      facts: dict,
      at: date | None = None,
      *,
      laws: dict[str, LawRef] | None = None,   # None 이면 현행대로 load_laws() (하위호환)
      rules: dict[str, Rule] | None = None,
  ) -> dict:
      """반환 dict 에 두 키 추가:
         "facts_used": dict   — 판정에 실제로 쓰인 facts 사본 (D82)
         "laws_used":  list[str] — 판정이 참조한 law_ref_id 정렬 목록 (인용 여부 무관)
      """
  # 신규 — 문구 복제 제거 (W2)
  NOT_CONSIDERED: tuple[str, ...]
  DISCLAIMER: str
  def laws_all_fetched(laws: dict[str, LawRef]) -> bool: ...
  ```

- **핵심 로직**
  1. **주입점**: `laws`/`rules` 가 주어지면 `load_laws()`/`load_rules()` 를 **호출하지 않는다**. 주어지지 않으면 현행 동작 유지 → 기존 호출자 3곳(MCP 도구·REST 서비스·`test_rules`) 무영향.
  2. `facts_used` 는 **입력 `facts` 의 얕은 사본**을 그대로 싣는다. 재조립·필터 금지 — 재조립하면 "판정이 본 사실"과 "번들에 실린 사실"이 다시 갈린다.
  3. `laws_used` 는 **평가된 전 룰의 `law_refs` 합집합**을 정렬해 싣는다. 발화한 룰만 세면 CLEAR 자산에서 빈 목록이 되어 W7 이 그대로 남는다.
  4. **W2 해소**: `backend/services/disposal.py:289-294` 의 문자열 복제를 제거하고 `engine.NOT_CONSIDERED`·`engine.DISCLAIMER` 를 import. `import data.rules.engine as _engine` 형태로 **모듈 참조**할 것 — `from … import DISCLAIMER` 는 로드 시점에 값을 고정한다(Sprint 5 W1 의 `DB_PATH` 사고와 같은 유형).
  5. **MCP↔REST 대조 확장**(Sprint 6 이월 #3): `spikes/rules_db_load.py` 의 대조를 `verdict` 단독 → **`verdict` + 4버킷 각각의 `rule_id` 집합 + `disposal_type` + `law_refs` 집합**으로 확장. ⛔ `message` 는 **넣지 말 것**(자유 문장이라 취성).
  6. `laws_all_fetched()` 헬퍼는 **엔진에 두되** MQ-701 은 쓰지 않는다(같은 스테이지 의존 금지). Stage 2 이후 소비자가 쓴다.

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | `laws` 만 주입, `rules` 미주입 | 허용. `rules` 는 `load_rules(laws)` — **주입된 laws 로** 로드(무결성 게이트가 같은 사본을 본다) |
  | 주입된 `rules` 가 주입된 `laws` 에 없는 참조 | `RuleIntegrityError` (D61 불변식 2 — 주입 경로라고 게이트를 낮추지 않는다) |
  | `facts` 가 빈 dict | 현행대로 전 룰 `INSUFFICIENT_FACTS`. `facts_used` 는 `{}` |
  | 호출자가 `facts_used` 를 변형 | 얕은 사본이라 원본 미오염. 단 중첩 값은 공유 — facts 에 중첩 구조가 없음을 `build_facts` 가 보장 |

- **지켜야 할 결정**: D62(사실 부족 ≠ 조건 미해당) · D61 · D73(`data/` 공유 계층) · D79(우선순위는 엔진에만) · **D82**(착수 전제)
- **DoD**
  - `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **41 + 신규 5 = 46 passed**
    (신규: 주입 laws 로 판정이 갈리는가 · 주입 rules 에 미등록 참조 → `RuleIntegrityError` · `facts_used` 가 입력과 동일 · `laws_used` 가 CLEAR 자산에서도 비지 않음 · `laws_all_fetched` 3케이스)
  - `uv run python spikes/disposal_api_contract.py` → 기존 24건 유지 + **드리프트 검사 2건**(`not_considered`·`disclaimer` 가 엔진 값과 **동일 객체 유래**)
  - `uv run python spikes/rules_db_load.py` → 기존 21건 + **대조 확장 4건**
  - **뮤턴트 확인 필수**: `LIEN-CONSENT.disposal_type` 을 BLOCKING→PRECONDITION 으로 바꿔 확장 대조가 **실제로 FAIL** 하는지 확인 후 원복. Sprint 6 트러블슈팅 7 이 *"이 뮤턴트로는 verdict 가 안 변한다"* 고 실증한 바로 그 지점이다
  - `git grep -n "생산 계획·대체 설비" backend/` → **0건**
  - `uv run ruff check data backend spikes` 통과

---

#### MQ-703 — 3차 평가 실행 · 원인 분석 · 프로파일 가드 (D88)

- **복무 시나리오**: S1~S4 (완료 기준 5지표)
- **변경 파일**: `eval/run_eval.py` · `eval/results/<타임스탬프>.{json,md}`(신규 산출) · `data/analysis/eval_gap_3rd.md`(신규) · `spikes/eval_score_contract.py`
- **⛔ 금지**: `backend/**`·`mcp_server/**` 코드 수정 — **이 태스크는 측정만 한다.** 고치고 싶은 것을 발견하면 `eval_gap_3rd.md` 에 적고 MQ-713 으로 넘긴다

- **인터페이스**
  ```python
  # run_eval.py 추가
  parser.add_argument("--allow-full-profile", action="store_true")
  # 서버 기동 후 GET /health 를 읽어 결과에 기록
  meta = {"tools_profile": health["tools_profile"], "tools": health["tools"],
          "llm_provider": os.environ.get("MAINTQ_LLM_PROVIDER") or "gemini"}
  # tools_profile == "full" 이고 --allow-full-profile 없으면 SystemExit(2)
  ```

- **핵심 로직**
  1. **D88 가드 먼저 넣고 그다음 측정한다.** 순서가 반대면 3차가 `full` 로 돌았는지 사후에 알 수 없다.
  2. 시드: `uv run python data/seed.py --with-error-codes`. **`--today` 금지**(세션 로그 §트러블슈팅 4 — 검증 쿼리가 벽시계라 위양성 FAIL).
  3. 3차 실행: `uv run python eval/run_eval.py --yes`. `MAINTQ_TOOLS_PROFILE` 은 **export 하지 않는다**.
  4. `meta` 를 결과 JSON 과 MD 머리말에 싣는다.
  5. **`eval_gap_3rd.md` 는 다음을 반드시 담는다**:
     - 2차(`20260805-061720`) 대비 지표별 증감표
     - **미측정 수정 4건이 무엇이었고 어느 지표에 걸리는가** — 특히 D66(`parts` 필드)·D76(도구 결과 구조 보존)은 **부품 특정 지표의 판정 소스를 직접 바꾼 수정**이다
     - **실패 문항의 군집 분석.** 2차 실측: T13·T14·T15(S2 3문항)가 **부품·인용·안전 3지표를 동시에** 떨어뜨린다. 안전 추가 실패는 T06·T09·T11·T16. → 원인이 3개가 아니라 **1~2개일 가능성**을 먼저 검증할 것
     - 문항별 `traces` 원본 확인 — `GET /api/chat/{sid}/trace` 로 **도구가 실제로 무엇을 반환했는지** 대조. `tool_payload` 컬럼(D76-2)이 있으면 그것을 쓴다
     - **MQ-713 이 실행할 후보 수정 목록** — 각 항목에 "어느 지표를 몇 % 움직일 것으로 보는가"가 아니라 **"어느 문항이 왜 실패했는가"** 를 적는다. 근거 없는 개선폭 추정 금지
  6. ⚠ **부품 특정 정확률은 `related_parts` 사람 최종 승인 전이라 "실적"으로 인용할 수 없다**(D12). 결과 MD 머리말의 기존 경고 문구를 유지·갱신한다.

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | LLM 키 없음 | 실행 불가. **스프린트를 막지 않는다** — Stage 1 의 다른 3태스크와 무관. 이 경우 MQ-713 이 Sprint 8 로 이월되고 그 사실을 sprint 문서에 기록 |
  | 일부 문항 실행 실패 | 분모 제외 + MD 에 사유 명시(기존 동작) |
  | 재생 이벤트 오염 | `has_replay` 로 분모 제외 (D55, 기존) |
  | `tools_profile == "full"` | `SystemExit(2)` + 안내. **조용히 진행 금지** |

- **지켜야 할 결정**: D69·**D88**(착수 전제) · D56(제공자 분기·env 우선) · D12(검수 전 실적 인용 금지) · D54·D66(판정 소스)
- **DoD**
  - `eval/results/<신규>.md` 존재 · 머리말에 `tools_profile: core` · `tools: 7` 기록
  - `uv run python eval/run_eval.py --dry-run` 에서 프로파일 가드 동작 확인 — `MAINTQ_TOOLS_PROFILE=full` 로 exit 2, `--allow-full-profile` 로 exit 0
  - `uv run python spikes/eval_score_contract.py` → 기존 건수 유지 + **가드 2건**
  - `data/analysis/eval_gap_3rd.md` — 증감표 · 군집 분석 · **traces 원본 대조 근거** · 후보 수정 목록
  - `uv run ruff check eval spikes` 통과

---

#### MQ-704 — 플래키 3스위트 per-suite DB 격리 (Sprint 6 이월 #4)

- **복무 시나리오**: 전 시나리오 (회귀 신뢰성)
- **변경 파일**: `spikes/s4_smoke.py` · `spikes/mcp_client_contract.py` · `spikes/sp2_mcp_roundtrip.py`
- **핵심 로직**
  1. 각 스위트 진입 시 `data/maintq.db` 를 **임시 디렉터리로 복사**하고 `MAINTQ_DB` 를 그 사본으로 지정해 자식 프로세스에 상속. `mcp_server/db.py:21` 이 이미 이 env 를 읽는다(실측 확인).
  2. 서브프로세스 종료를 **`wait()` 로 기다린다**(sleep 아님). Windows 는 핸들 해제가 비동기라 이게 없으면 다음 스위트가 writer 락을 못 잡는다.
  3. 종료 시 사본 삭제. 삭제 실패는 **경고만**(테스트 실패로 만들지 않는다).
  4. **연속 20회 재현 스크립트**로 실패율을 기록한다 — 0/20 이 아니면 원인이 다르다는 뜻이므로 그 사실을 남긴다.
- **엣지 케이스**: 임시 경로에 한글·공백 → `Path.as_posix()` 로 URI 조립(기존 `db.py:61` 패턴 재사용) / DB 사본 중 WAL 파일 잔존 → `-wal`·`-shm` 도 함께 복사하거나 복사 전 `PRAGMA wal_checkpoint(TRUNCATE)`
- **지켜야 할 결정**: D15(프로세스 분리 — 사본 경로는 env 로만 전달) · D30
- **DoD**
  - 3스위트 **연속 20회 실행 실패 0회** (기록을 태스크 보고에 첨부)
  - 건수 불변: `s4_smoke`·`mcp_client_contract`·`sp2_mcp_roundtrip` 각각 기존과 동일
  - 실행 후 `data/maintq.db` **mtime·size 불변**(사본을 썼다는 증거)
  - `uv run ruff check spikes` 통과

---

#### MQ-705 — 근거 번들 재설계 (W5·W6·W7·계약근거·N1·N2)

- **복무 시나리오**: S10
- **변경 파일**: `mcp_server/tools/build_evidence_bundle.py` · `spikes/asset_tools_contract.py` · `spikes/bundle_integrity.py`(신규)
- **선행**: MQ-701(조문 원문) · MQ-702(주입점·`facts_used`)

> ### 🔴 Stage 1 인계 — 번들은 **엔진을 직접 호출**해야 한다 (반드시 읽을 것)
>
> `build_evidence_bundle.py:81` 은 현재 **MCP 도구**를 부른다:
> `from .check_disposal_blockers import check_disposal_blockers as _judge`.
> 그 뒤 `engine.load_laws_from_db(con)` 로 조문을 **다시** 읽고 `engine.build_facts(row, …)` 로
> 사실을 **다시** 조립한다 — 즉 **D82 가 없애려던 W5(판정=파일 사본 / 해시=DB 사본)와 facts 재조립이 그대로 남아 있다.**
> MQ-702 는 주입점만 열었고 **프로덕션 소비자는 0곳**이다(현재 사용처는 `test_rules.py`·`rules_db_load.py` 뿐).
>
> 게다가 Stage 1 에서 MCP 출력을 `04 §8` 13키로 **화이트리스트 고정**했다(`_ENGINE_CONTRACT_KEYS`).
> `facts_used`·`laws_used` 는 계약 밖 키라 **MCP 도구 경유로는 받을 수 없다.**
>
> **→ MQ-705 는 `engine.check_disposal_blockers(facts, at, laws=laws, rules=rules)` 를 직접 호출하고
> 반환된 `facts_used`·`laws_used` 를 그대로 쓴다. MCP 도구 경유 금지.**
> 경유하면 두 값을 못 받아 W5 가 남고, 번들이 "판정과 다른 사본으로 해시한다"는 원래 결함으로 되돌아간다.
>
> **DoD 추가**: ⑰ `build_evidence_bundle` 이 `check_disposal_blockers`(MCP 도구)를 import 하지 않는다 ·
> ⑱ 번들의 `facts_used` 가 판정에 실제로 쓰인 facts 와 동치다(재조립본이 아니다)

- **인터페이스 — 번들 스키마 3키 → 5키 (D83)**
  ```json
  {
    "status": "ok",
    "asset_id": "AST-L3-LIFT",
    "evidence_bundle": {
      "laws": [{"law_ref_id":"KR-VAT-32","effective_from":"2025-01-01",
                "text_hash":"sha256:…"}],
      "rules": [{"rule_id":"VAT-INVOICE","rule_version":2,
                 "rule_hash":"sha256:…"}],
      "evaluated": [{"rule_id":"TAX-CREDIT-2Y","rule_version":1,"verdict":"CLEAR"},
                    {"rule_id":"VAT-INVOICE","rule_version":2,"verdict":"TRIGGERED"}],
      "contracts": [{"contract_ref":"여신거래기본약관",
                     "text_hash": null, "hash_fixed": false,
                     "note":"계약 조항 원문 원천이 저장소에 없다 — 이 근거는 해시로 고정되지 않는다"}],
      "facts": { …engine 이 반환한 facts_used 그대로… }
    },
    "bundle_hash": "sha256:…",
    "hash_spec": "sha256/nfkc-ws/canonical-json-v1",
    "verdict": "CONDITIONAL",
    "not_considered": [ …판정 주체 값 그대로… ],
    "built_at": "2026-08-09T05:12:44Z",
    "disclaimer": "…"
  }
  ```

- **핵심 로직**
  1. **W5 — 원천 일원화.** DB 에서 `laws` 를 **한 번** 로드하고(`engine.load_laws_from_db(con)`), 그것을 `engine.check_disposal_blockers(facts, laws=laws, rules=rules)` 에 **주입**한다. 인용 집합·`text_hash`·`effective_from` 이 **같은 객체**에서 나온다. ⛔ 파일 로더와 DB 로더를 한 호출 안에서 섞지 말 것.
  2. **W6 — `rule_hash`.** 룰 본문의 정준 직렬화 해시:
     ```python
     RULE_HASH_FIELDS = ("rule_id","rule_version","label","category","disposal_type",
                         "source_type","law_refs","contract_refs","interpretation",
                         "required_facts","trigger","boundary","message",
                         "resolve_options","confidence","requires_expert_review")
     rule_hash = engine.text_hash(canonical_json({k: getattr(rule,k) for k in RULE_HASH_FIELDS}))
     ```
     `authored_by`·`reviewed_at`·`revision_note` 는 **제외**한다(메타데이터라 판정에 무관 — 넣으면 주석 수정이 "변조"로 보인다). 제외 목록을 코드 주석에 근거와 함께 남긴다.
  3. **W7 — `evaluated[]`.** `laws_used`·평가된 전 룰을 `rule_id` 정렬로 싣는다. **CLEAR 자산도 비지 않는다.** 이게 W7 의 유일한 해소다.
  4. **계약 근거.** `contract_refs` 를 `contracts[]` 로 싣되 `text_hash: null`·`hash_fixed: false`. ⛔ **`law_text_unavailable` 검사 대상에 넣지 말 것** — 넣으면 `LIEN-CONSENT` 자산 번들이 구조적으로 영원히 불가능해진다(`04 §14` 이미 명시).
  5. **N1 — 해시 의미 명시.** `hash_spec` 필드를 **번들 밖**에 둔다(안에 넣으면 스펙 문자열 변경이 해시를 흔든다). `disclaimer` 에 *"변조 없음의 기준은 바이트 동일이 아니라 NFKC + 공백 정규화 후 동일이다"* 를 명시.
  6. **N2 — 자산 수정 감지.** 판정 **전**과 번들 조립 **후** 자산 행을 두 번 읽고 `engine.text_hash(canonical_json(build_facts(row)))` 를 비교. 불일치 → `status:"error"`, `reason:"asset_modified"`. 기존 `asset_disappeared` 는 그대로 유지.
  7. **`bundle_hash` 산출 규약은 그대로**(`04 §14`): `sort_keys=True`·`separators=(",",":")`·`ensure_ascii=False`·`engine.text_hash()` 재구현 금지. **리스트 4종은 명시적으로 정렬**: `laws`→`law_ref_id`, `rules`·`evaluated`→`(rule_id, rule_version)`, `contracts`→`contract_ref`.
  8. **`built_at`·`evaluated_at`·`hash_spec` 은 번들 밖**(불변).

- **엣지 케이스**
  | 상황 | 반환 |
  |---|---|
  | 인용 조문 중 미수집 1건 이상 | `error/law_text_unavailable` + `missing_law_refs[]` (기존 동작 유지) |
  | CLEAR 자산(`laws`·`rules` 빈 배열) | **성공.** `evaluated[]` 는 비지 않는다. `bundle_hash` 산출됨 |
  | `contract_refs` 만 있고 `law_refs` 없는 룰 발화 | 성공. `contracts[]` 에만 실림 |
  | 판정 직후 자산 행 소실 | `error/asset_disappeared` |
  | 판정 직후 자산 행 **수정** | `error/asset_modified` (신규) |
  | `disposal_mode` enum 밖 | `error/invalid_input` (위임 전 차단, 기존) |
  | `RuleIntegrityError` | `error/rule_integrity` |
  | 같은 입력 2회 호출 | `bundle_hash` 동일 (멱등) |

- **지켜야 할 결정**: D60 · D61 · D62 · **D82·D83**(착수 전제) · D10(저장 금지 — 이 도구는 `decisions` 를 INSERT 하지 않는다) · D9(예외 금지)
- **DoD**
  - `uv run python spikes/bundle_integrity.py` — **신규 14건**:
    ① 같은 입력 2회 → 해시 동일 ② `built_at` 만 다른 두 응답 → 해시 동일 ③ 룰 본문 1글자 변경(같은 `rule_version`) → **`rule_hash` 변경** ④ 룰 메타(`revision_note`) 변경 → `rule_hash` **불변** ⑤ CLEAR 자산 번들에 `evaluated[]` 비어있지 않음 ⑥ `contracts[]` 에 `hash_fixed:false` ⑦ `contracts` 가 `law_text_unavailable` 을 유발하지 않음 ⑧ 리스트 4종 정렬 확인 ⑨ 판정 laws 와 해시 laws 가 **동일 객체 유래**(주입 확인) ⑩ 전각/공백 변형 → 해시 동치(N1 명시) ⑪ 판정 후 자산 UPDATE 주입 → `asset_modified` ⑫ 자산 DELETE → `asset_disappeared` ⑬ `hash_spec` 이 번들 **밖** ⑭ `decisions` 행 수 불변
  - **뮤턴트 4종으로 먼저 깨뜨려 확인**(전부 원복): ⓐ `rule_hash` 제거 → ③ FAIL ⓑ `evaluated[]` 제거 → ⑤ FAIL ⓒ 주입 대신 `load_laws()` 재호출 → ⑨ FAIL ⓓ 자산 재읽기 제거 → ⑪ FAIL. **깨지지 않으면 그 회귀는 방어선이 아니다**
  - `uv run python spikes/asset_tools_contract.py` → 기존 48건 유지 + 번들 항목 갱신
  - MQ-701 결과에 따라: 조문 수집 성공 시 **실 DB 에서 `status:"ok"` 번들 1건 이상** 산출 확인 / 미수집 시 `law_text_unavailable` 이 정상 경로임을 확인
  - `uv run ruff check mcp_server spikes` 통과

---

#### MQ-706 — `generate_disposal_document` 쓰기 도구 + 등록

- **복무 시나리오**: S10
- **변경 파일**: `mcp_server/tools/generate_disposal_document.py`(신규) · `mcp_server/db.py`(수정) · `mcp_server/server.py`(수정) · `backend/agent/prompts.py`(수정) · `spikes/prompt_rules.py`(수정) · `spikes/tools_profile_contract.py`(수정) · `spikes/write_tool_contract.py`(수정)
- **⛔ 금지**: `backend/services|routers/**`·`data/seed.py` 접근 (MQ-707 소유)

- **인터페이스**
  ```python
  DESCRIPTION = (
    "설비 자산의 처분 승인서·진술보장서 '초안'을 생성한다. 확정이 아니다. "
    "반드시 check_disposal_blockers 로 판정을 먼저 확인한 뒤 사용자가 처분을 결정한 후에만 호출할 것. "
    "판정이 BLOCKED·HOLD·INSUFFICIENT_FACTS 여도 초안은 만들어진다 — 그 사실이 초안에 기록되고, "
    "차단을 뚫을지는 팀장이 승인 화면에서 사유와 함께 결정한다. "
    "너는 override 를 요청하거나 사유를 대신 작성할 수 없다 — 그 파라미터가 없다. "
    "근거 조문 원문이 아직 수집되지 않았으면 초안 생성이 거부된다 — 해시할 근거가 없는 서류는 만들지 않는다."
  )

  def generate_disposal_document(
      reason: str,                       # 필수 — 기본값 없음 (D80)
      asset_id: str | None = None,       # either-or
      equipment_id: str | None = None,
      disposal_mode: str = "SALE",
      disposal_date: str | None = None,
  ) -> dict: ...
  ```
  ```json
  // output ok
  { "status":"ok", "decision_id":"DEC-0001", "state":"draft",
    "decision_type":"DISPOSAL", "asset_id":"AST-L3-LIFT",
    "verdict_at_signing":"CONDITIONAL", "bundle_hash":"sha256:…",
    "override": false,
    "next_step":"이 초안은 확정이 아니다. 팀장 승인 큐에서 서명해야 처분이 확정된다.",
    "documents_preview": {"approval":"…","representation_warranty":"…"},
    "unreviewed_template_notice":"문서 문안은 미검수 초안이다 (TODO_직접할일.md)" }
  ```

- **★ `decisions` draft INSERT 계약 (MQ-707 이 이 값을 전제로 개발한다 — 어기지 말 것)**

  | 컬럼 | 값 |
  |---|---|
  | `decision_id` | `DEC-%04d` — `SELECT decision_id … ORDER BY decision_id DESC LIMIT 1` +1 (`create_po_draft._next_po_id` 패턴 복제) |
  | `asset_id` | 해석된 자산 |
  | `decision_type` | `'DISPOSAL'` 고정 |
  | `evidence_bundle` | `json.dumps(evidence_bundle, ensure_ascii=False, sort_keys=True, separators=(",",":"))` — **번들의 정준 직렬화 그대로**. 다시 직렬화하면 서명 시 해시 재대조가 깨진다 |
  | `bundle_hash` | 도구가 산출한 값 그대로 |
  | `verdict_at_signing` | **draft 시점 verdict.** 이름이 `_at_signing` 이지만 서명 시 MQ-707 이 재산출해 대조한다(D84) |
  | `override` | **`0` 고정** (D81) |
  | `override_reason` | **`NULL` 고정** (D81) |
  | `reviewed_by` · `signed_at` | **`NULL` 고정** |
  | `state` | `'draft'` 고정 |

  > `decisions` 에는 `reason`·`session_id`·`requested_by` 컬럼이 **없다**(실측 DDL). `reason` 은 `evidence_bundle` 밖에 둘 자리가 없으므로 **MQ-707 이 seed.py DDL 에 `reason TEXT`·`requested_by TEXT REFERENCES users`·`session_id TEXT` 3컬럼을 추가**한다. 이 태스크는 그 컬럼에 `reason` 만 채우고 나머지는 NULL 로 둔다 — 신원·세션은 백엔드가 stamp 한다(D23·D37 복제).

- **핵심 로직**
  1. `build_evidence_bundle` 을 **함수로 직접 호출**(`from .build_evidence_bundle import build_evidence_bundle`). 실패 시 그 status/reason 을 **그대로 전파**(§14 계약과 동일 태도). 특히 `law_text_unavailable` → **draft 를 만들지 않는다.** 해시할 근거가 없는 처분 서류는 계층 3의 존재 이유를 무너뜨린다.
  2. `reason` 미기재/공백 → `error/reason_required` (`create_po_draft:58` 패턴).
  3. `mcp_server/db.py` 에 **`decision_writer()`** 추가 — `draft_writer` 와 같은 구조로 TEMP TRIGGER 2개:
     ```sql
     CREATE TEMP TRIGGER IF NOT EXISTS mcp_no_decision_update
     BEFORE UPDATE ON decisions
     BEGIN SELECT raise(ABORT, 'MCP 도구는 decisions 를 수정할 수 없습니다 (D10)'); END;
     CREATE TEMP TRIGGER IF NOT EXISTS mcp_no_decision_delete …
     ```
     ⛔ `draft_writer` 를 재사용해 `decisions` 를 쓰지 말 것 — 그러면 `po_drafts` 전용 트리거만 걸린 커넥션으로 `decisions` 를 만지게 된다.
  4. **문서 렌더는 미리보기만**(D86). `documents_preview` 는 번들에서 조립한 문안이며 **DB 에 저장하지 않는다**. 정식 렌더는 `GET /api/decisions/{id}` 가 한다.
  5. **문안 템플릿은 `unreviewed_template_notice` 를 강제한다.** 진술보장서는 법적 효력이 있는 문서다 — 안전 문구(D2·safety-guardrail)와 같은 성격으로 **사람 검수 전이라는 사실을 출력에 싣는다.** ⛔ LLM 이 문안을 생성하게 하지 말 것: 템플릿은 코드 상수이고 **번들의 값만 치환**한다.
  6. `server.py` 등록: `full` 블록 안. `reason` 은 **기본값 없음**(D80). `_DISPOSAL_MODE_FIELD`·`_DISPOSAL_DATE_FIELD` 재사용.
  7. `prompts.py` EXT 규칙 신설(기존 11 → 12): *"`generate_disposal_document` 는 초안만 만든다. 사용자에게 '처분이 완료됐다'고 말하지 말 것. `override` 는 네 권한이 아니다."* **도구별 게이트**(MQ-612 선례)로 붙여 `core` 프로파일에서 규칙이 새지 않게 한다.

- **엣지 케이스**
  | 상황 | 반환 |
  |---|---|
  | `law_text_unavailable` | 전파. **draft 미생성**, `decisions` 행 수 불변 |
  | `asset_modified` / `asset_disappeared` | 전파. draft 미생성 |
  | `no_host_asset`(분전반) | `not_found/no_host_asset` |
  | verdict `BLOCKED` | **정상 draft 생성**(`override=0`). "차단됐다"가 아니라 "차단된 채로 결재에 올라간다" (D63) |
  | 같은 자산 중복 호출 | 두 건의 draft. **막지 않는다** — 중복 결재는 사람이 큐에서 판단한다 |
  | `decisions` UPDATE 시도 | TEMP TRIGGER ABORT → `error/integrity` |
  | `reason` 공백 | `error/reason_required` |

- **지켜야 할 결정**: **D81**(착수 전제) · D10 · D23·D37 · D80 · D9 · D69 · D63
- **DoD**
  - `uv run python spikes/write_tool_contract.py` → 기존 14건 + **신규 8건**:
    ① draft 생성 후 `state='draft'`·`override=0`·`override_reason IS NULL`·`reviewed_by IS NULL`·`signed_at IS NULL` ② `UPDATE decisions` 시도 → ABORT ③ `DELETE decisions` 시도 → ABORT ④ `law_text_unavailable` → 행 수 불변 ⑤ BLOCKED 자산 → draft 생성됨(막지 않음) ⑥ 도구 스키마에 `override`·`override_reason`·`reviewed_by` **키가 없음** ⑦ `evidence_bundle` 을 다시 파싱해 `text_hash(canonical)` 가 저장된 `bundle_hash` 와 일치 ⑧ `reason` 공백 거부
  - `uv run python spikes/tools_profile_contract.py` → **`core`=7 / `full`=15**. `generate_disposal_document` 등록 제거 뮤턴트로 **FAIL 확인 후 원복**
  - `uv run python spikes/prompt_rules.py` → `len(RULES)==12`. `tool_names=CORE_7` 일 때 `generate_disposal_document` **0건 누출**
  - `uv run python spikes/sp2_mcp_roundtrip.py` · `mcp_client_contract.py` 무회귀
  - `uv run ruff check mcp_server backend spikes` 통과

---

#### MQ-707 — 서명 REST + 승인 큐 통합 REST + `decisions` 스키마 게이트

- **복무 시나리오**: S10 (계층 3 확정)
- **변경 파일**: `backend/services/decisions.py`(신규) · `backend/routers/decisions.py`(신규) · `backend/services/approvals.py`(신규) · `backend/routers/approvals.py`(신규) · `backend/main.py`(수정) · `data/seed.py`(수정) · `spikes/api_contract.py`(수정) · `spikes/approvals_contract.py`(신규)
- **⛔ 금지**: `mcp_server/**`·`backend/services/po.py` 의 기존 함수 시그니처 변경

- **인터페이스**
  ```
  GET  /api/decisions?state=pending          # 목록 (역할 무관 조회)
  GET  /api/decisions/{decision_id}          # 상세 + 렌더된 문서·증빙 패키지 (D86)
  POST /api/decisions/{id}/submit            # draft → pending   (technician만, 403 대칭)
  POST /api/decisions/{id}/sign              # pending → signed  (manager만)
       body: {override?: bool = false, override_reason?: str|null, note?: str|null}
  POST /api/decisions/{id}/reject            # pending → rejected (manager만, reason 필수 → 422)

  GET  /api/approvals?state=pending&kind=    # 통합 큐 (D85)
  ```
  ```python
  # services/decisions.py
  BLOCKING_VERDICTS = ("BLOCKED", "HOLD", "INSUFFICIENT_FACTS")   # engine.VERDICTS 파생
  class DecisionTransitionError(Exception): ...
  class EvidenceChanged(Exception): ...          # → 409
  class OverrideRequired(Exception): ...         # → 409
  class OverrideReasonRequired(Exception): ...   # → 422
  def sign(decision_id, *, reviewed_by, override, override_reason, note) -> dict: ...
  def render_documents(bundle: dict, con) -> dict: ...   # D86 — 저장하지 않는다
  ```

- **핵심 로직**
  1. **`data/seed.py` DDL 보강 3건**
     ```sql
     -- decisions 에 컬럼 3개 추가 (MQ-706 draft 계약)
     reason TEXT, requested_by TEXT REFERENCES users, session_id TEXT,
     -- ★ "서명 없는 확정 0건" 을 스키마로 잠근다
     CHECK (state <> 'signed' OR (signed_at IS NOT NULL
                                  AND reviewed_by IS NOT NULL
                                  AND length(trim(bundle_hash)) > 0)),
     -- ★ "BLOCKING 우회 처분 0건" 을 스키마로 잠근다
     CHECK (state <> 'signed' OR override = 1
            OR verdict_at_signing IN ('CONDITIONAL','CLEAR'))
     ```
     이 두 CHECK 가 핵심이다 — **코드 버그나 미래의 잘못된 UPDATE 로도 뚫을 수 없다.** D10 이 도구에 UPDATE 권한을 아예 안 준 것, D63 이 사유 없는 override 를 CHECK 로 막은 것과 같은 태도.
     ⚠ 두 번째 CHECK 의 verdict 목록은 `engine.VERDICTS` 와 어긋날 수 있다 → `seed.py` 가 DDL 생성 후 `set(engine.VERDICTS) - {'CONDITIONAL','CLEAR'} == set(BLOCKING_VERDICTS)` 를 **자가검증 ⑲** 로 확인한다.
  2. **`sign()` 순서 — 순서가 계약이다**
     ```
     ① 행 조회 · 없으면 KeyError → 404
     ② state != 'pending' → DecisionTransitionError → 409
     ③ 번들 재산출: bundle = build(facts from stored evidence_bundle.facts)
        - disposal_mode·disposal_date 를 저장된 facts 에서 꺼낸다 (별도 컬럼 불필요 — 실측 확인:
          build_facts 가 facts["disposal_mode"]·["disposal_date"] 를 넣는다)
        - 재산출 해시 != 저장된 bundle_hash → EvidenceChanged → 409
        - ⛔ backend 는 MCP 도구를 부르지 않는다. data.rules.engine 을 직접 쓴다 (D73)
     ④ 재산출 verdict ∈ BLOCKING_VERDICTS 이고 override != True → OverrideRequired → 409
     ⑤ override == True 이고 override_reason 공백 → OverrideReasonRequired → 422
     ⑥ UPDATE: state='signed', signed_at=UTC now, reviewed_by=X-User,
                override, override_reason, verdict_at_signing=<재산출 verdict>
     ```
     **③ 이 ④ 보다 먼저인 이유**: 근거가 바뀐 상태에서 override 를 받으면 *"사람이 본 것과 다른 근거에 서명"* 이 된다. 근거 무결성이 권한 판단보다 앞선다.
     **`verdict_at_signing` 을 재산출 값으로 덮는 이유**: 컬럼 이름이 말하는 것이 서명 시점 판정이다. draft 시점 값을 남기면 필드가 거짓말을 한다.
  3. **`/api/approvals` 조립** (D85) — `po_drafts` 와 `decisions` 를 각각 조회해 공통 형태로 합치고 `created_at DESC` 정렬:
     ```json
     { "items": [ {
         "kind": "po"|"disposal",
         "id": "PO-0117"|"DEC-0001",
         "title": "냉각팬 ×2" | "AST-L3-CONV 매각 처분",
         "state": "pending",                    // 원 state 문자열 그대로 (변환 금지)
         "urgency": "urgent"|null,              // 처분서에는 없다 → null. 지어내지 않는다
         "requested_by": str|null, "requested_by_name": str,
         "created_at": "…Z",
         "detail_path": "/api/po/PO-0117"|"/api/decisions/DEC-0001",
         "verdict": "BLOCKED"|null,             // kind=='disposal' 일 때만
         "requires_override": true|false|null   // 위와 동일
       } ] }
     ```
     - `kind` enum 은 `("po","disposal","repair")` — **`repair` 는 Sprint 7 미구현이라 항상 0건**. enum 에 미리 넣는 이유는 Sprint 8 이 계약 변경 없이 추가되게 하기 위함이며, **그 사실을 응답 스키마 주석과 `06 §2.6` 에 명시**한다.
     - ⛔ `state` 를 공통 어휘로 정규화하지 말 것. `approved` 와 `signed` 는 다른 사건이다.
     - **`/api/po` 응답 형태·경로 무변경**(D85). `spikes/api_contract.py` 28건이 그대로 통과해야 한다.
  4. **문서 렌더** (D86, `render_documents`) — 저장하지 않고 `GET /api/decisions/{id}` 응답 조립 시점에 계산:
     - **처분 승인서**: 자산·처분방식·일자 · verdict · blockers/preconditions 목록 · **인용 조문 각주**(`bundle.laws[].law_ref_id` → `law_refs` 테이블의 `law_name 제N조(제목)`)
     - **진술보장서**: 룰별 진술 항목 + `contracts[]` 의 `hash_fixed:false` 표시
     - **증빙 패키지(축소판)**: 정비 이력 요약(`repair_records` 중 `signed_at IS NOT NULL` 만 — `12 §11` 가드레일) + 보전지표(`get_maintenance_metrics` 와 **같은 산식**을 backend 가 재구현하지 말고… ⚠ 도구는 `mcp_server` 소유라 import 불가(D15). **`repair_records` 집계 SQL 을 backend 에 두되 산식이 `12 §2`·D70 과 같음을 주석·회귀로 대조**한다)
     - ⚠ **감가상각 명세는 만들지 않는다** — `assets` 에 상각 스케줄 원천이 없다. `12 §8` 4종 중 3종만 제공하고 **빠진 1종을 응답 필드로 밝힌다**(`missing_sections: ["감가상각 명세 — 상각 스케줄 원천 없음"]`). 지어내지 않는다(D65 태도).
     - 응답에 **`hash_fixed: false` 와 "이 증빙 패키지는 서명 해시로 고정되지 않는다"** 를 강제(D86).
  5. **역할 게이트**: `submit`=technician / `sign`·`reject`=manager. `backend/deps.require()` 재사용. **양방향 403**(manager 가 submit → 403). ⚠ `precheck` 에는 여전히 게이트를 두지 않는다(D71) — 읽기 판정과 확정 경로를 섞지 않는다.
  6. `backend/main.py` 에 `include_router(decisions.router)`·`include_router(approvals.router)` 2줄 추가.

- **엣지 케이스**
  | 상황 | HTTP |
  |---|---|
  | 없는 `decision_id` | 404 |
  | `draft` 상태에서 `sign` | 409 (`DecisionTransitionError`) |
  | 재산출 해시 불일치 | **409 `evidence_changed`** |
  | BLOCKED + `override` 미지정 | **409 `override_required`** — 본문에 blockers·resolve_options 를 실어 보낸다(S4 태도) |
  | `override=true` + 사유 공백 | **422** (라우터 검증) — DB CHECK 가 2차 방어선 |
  | technician 이 `sign` | **403** |
  | 룰 카탈로그 0행 | 503 (`precheck` 과 동일, D71) |
  | 조문 미수집이라 재산출 불가 | 409 `evidence_changed` 가 아니라 **409 `law_text_unavailable`** — 원인을 정확히 말한다 |
  | 이미 `signed` 인 건 재서명 | 409 |

- **지켜야 할 결정**: D63(override + 사유 필수) · D38(403/409/422 분리) · D39(UTC) · D41(users FK) · D23·D36 · D18 · D71(precheck 게이트 없음 유지) · D73 · **D84·D85·D86**(착수 전제)
- **DoD**
  - `uv run python data/seed.py --with-error-codes` → 기존 ①~⑯ + **신규 ⑰⑱⑲** 전부 PASS
    (⑰ `decisions` 신규 컬럼 3종 존재 · ⑱ 두 CHECK 가 실제로 거부하는지 INSERT 시도로 확인 · ⑲ CHECK 의 verdict 목록이 `engine.VERDICTS` 와 정합)
  - `uv run python spikes/api_contract.py` → **기존 28건 전부 통과**(`/api/po` 무회귀 증명)
  - `uv run python spikes/approvals_contract.py` — **신규 18건**:
    ① `/api/approvals?state=pending` 이 po·disposal 양쪽을 담는다 ② `kind` 필터 동작 ③ `repair` 필터 → 0건(에러 아님) ④ `state` 가 원 어휘 그대로 ⑤ `urgency` 가 처분서에서 `null` ⑥ `detail_path` 가 실제 200 ⑦~⑫ submit/sign/reject 정상 경로 + 403 대칭 2건 ⑬ 409 `override_required` ⑭ 422 사유 누락 ⑮ 409 `evidence_changed`(자산 UPDATE 주입) ⑯ 서명 후 `signed_at`·`reviewed_by` non-null ⑰ `GET /api/decisions/{id}` 에 `missing_sections`·`hash_fixed:false` ⑱ `/api/po` 응답 키 집합 불변
  - **직접 SQL 로 뚫기 시도 2건이 실패해야 한다**: `UPDATE decisions SET state='signed' WHERE …`(signed_at NULL) → CHECK 위반 / `UPDATE … state='signed', signed_at=…, reviewed_by=…` (verdict=BLOCKED, override=0) → CHECK 위반
  - `uv run ruff check backend data spikes` 통과

---

#### MQ-708 — BLOCKING 우회 0건 · 서명 없는 확정 0건 회귀 + S9→S10 통합 스모크

- **복무 시나리오**: S9 · S10 (사용자 요청 1번의 **증명**)
- **변경 파일**: `spikes/disposal_sign_contract.py`(신규) · `spikes/s10_smoke.py`(신규)
- **선행**: MQ-706 · MQ-707
- **⛔ 금지**: **제품 코드 수정 금지.** 이 태스크에서 결함이 나오면 **회귀를 완화하지 말고** 결함으로 보고한다(Sprint 6 의 "완화가 아니라 테스트를 강하게" 원칙)

- **핵심 로직 — `disposal_sign_contract.py` (전수 · 다층)**
  1. **전수 매트릭스.** 시드 9자산 × 3모드 = 27조합을 `check_disposal_blockers` 로 판정하고 verdict 별로 분류한다. `BLOCKING_VERDICTS` 조합 **전부**에 대해:
     - 도구로 draft 생성 → `override=0` 확인
     - `submit` → `sign`(override 없이) → **전부 409**. 한 건이라도 200 이면 FAIL
     - `sign(override=true, reason="…")` → 200, `override=1`·`override_reason` 저장 확인
  2. **4층 방어 각각을 독립으로 확인한다** (한 층을 무력화해도 다른 층이 잡는지):
     | 층 | 검사 |
     |---|---|
     | ① MCP 도구 | 스키마에 `override`·`override_reason` 키 **부재** |
     | ② MCP 커넥션 | `decision_writer` 로 `UPDATE decisions` → ABORT |
     | ③ REST 로직 | `sign` 이 `override_required` 409 |
     | ④ DB CHECK | 직접 SQL UPDATE → CHECK 위반 |
  3. **"서명 없는 확정 0건"**:
     - `UPDATE decisions SET state='signed'` (signed_at NULL) → CHECK 위반
     - `state='signed'` 인 전 행에 대해 `signed_at IS NOT NULL AND reviewed_by IS NOT NULL AND reviewed_by IN (SELECT user_id FROM users)` — **불변식 쿼리로 확인**
     - technician `sign` → 403
  4. **뮤턴트 4종으로 먼저 깨뜨린다**(전부 원복):
     ⓐ `sign()` 의 ④ 게이트 제거 → 전수 매트릭스 FAIL ⓑ DDL CHECK 2개 중 하나 제거 → 해당 SQL 검사 FAIL ⓒ `decision_writer` 트리거 제거 → ② FAIL ⓓ 도구에 `override` 파라미터 추가 → ① FAIL. **깨지지 않는 검사는 제출하지 않는다**

- **핵심 로직 — `s10_smoke.py` (`s4_smoke.py` 패턴 복제)**
  1. 임시 DB 사본 + `MAINTQ_DB` 지정(MQ-704 패턴 재사용). 실 DB 오염 0.
  2. 서버 기동(`MAINTQ_TOOLS_PROFILE=full`) → `/health` 대기.
  3. 관통 경로:
     ```
     POST /api/assets/{id}/disposal/precheck  → 200|409 + verdict
     MCP  generate_disposal_document          → decision_id, state=draft
     POST /api/decisions/{id}/submit  (tech)  → 200, state=pending
     GET  /api/approvals?state=pending        → 그 decision_id 가 kind=disposal 로 보인다
     GET  /api/decisions/{id}                 → 승인서·진술보장서·증빙 패키지 렌더 + missing_sections
     POST /api/decisions/{id}/sign    (mgr)   → 200|409(override_required)
     검증: state='signed' · bundle_hash 불변 · signed_at·reviewed_by non-null
     ```
  4. **CLEAR/CONDITIONAL 경로와 BLOCKED 경로를 둘 다 완주**시킨다.
  5. MQ-701 결과가 부분 수집이면 `law_fetch.md` 매트릭스가 지정한 자산을 쓴다. **0/7 이면** 스모크는 `law_text_unavailable` 에서 멈추는 것을 정상 경로로 검증하고 그 사실을 출력에 남긴다 — **초록으로 위장하지 않는다**.

- **엣지 케이스**: 서버 기동 실패 → 명시적 FAIL(스킵 금지) / `full` 프로파일이 안 켜진 채 실행 → 도구 부재를 FAIL 로 보고 / 스모크가 남긴 `decisions` 행 → 임시 DB 라 실 DB 무영향(실행 후 실 DB `decisions` 행 수 불변을 단언)
- **지켜야 할 결정**: D63 · D38 · D10 · D69
- **DoD**
  - `uv run python spikes/disposal_sign_contract.py` — **신규 22건 이상**, 전수 매트릭스 포함, 뮤턴트 4종 사전 확인 기록 첨부
  - `uv run python spikes/s10_smoke.py` — **신규 12건 이상**, 실 서버·실 MCP
  - 실행 후 `data/maintq.db` **mtime·size 불변**
  - 두 스위트 **연속 5회 실행 실패 0회**
  - `uv run ruff check spikes` 통과

---

#### MQ-709 — 승인 큐 3종 렌더 + 서명 UI + 프론트 계약 단일 확장

- **복무 시나리오**: S10 (팀장 서명) · 기존 S1~S3(발주 승인) 무회귀
- **변경 파일**: `frontend/lib/api.ts` · `lib/types.ts` · `lib/mappers.tsx` · `lib/queueState.ts`(신규) · `components/screens/ApprovalQueueScreen.tsx` · `components/queue/QueueList.tsx` · `components/queue/PoDetail.tsx` · `components/queue/DecisionDetail.tsx`(신규) · `components/queue/DecisionBar.tsx` · `components/queue/SignBar.tsx`(신규) · `components/queue/EvidenceCard.tsx` · `app/(console)/manager/page.tsx` · `app/(console)/manager/decision/[decisionId]/page.tsx`(신규) · `lib/mock/queue.tsx`
- **⛔ 금지**: `components/asset/**`·`lib/ownership.ts` 접근 (Stage 6 소유)

- **인터페이스**
  ```ts
  // lib/types.ts
  export type ApprovalKind = "po" | "disposal" | "repair";
  export interface QueueEntry {
    kind: ApprovalKind;
    id: string;                 // ★ poId 를 대체한다
    title: string;
    note?: string;
    urgency: Urgency | null;    // 처분서는 null — 지어내지 않는다
    state: string;              // 원 어휘 그대로 (po: approved / disposal: signed)
    meta: string;
    detailHref: string;
    verdict?: string | null;
    requiresOverride?: boolean | null;
  }

  // lib/queueState.ts — D87 의 total 맵
  export const STATE_LABEL: Record<ApprovalKind, Record<string, {text:string; tone:Tone}>>;
  export const KIND_LABEL: Record<ApprovalKind, string>;
  export function stateView(kind: ApprovalKind, state: string): {text:string; tone:Tone};
  //   ↑ 맵에 없는 값은 { text: state, tone: "warn" } — 절대 "ok" 로 떨어지지 않는다

  // lib/api.ts 신규 fetcher (Stage 6 의 두 화면도 여기만 쓴다)
  getApprovals(role, state?, kind?) · getDecision(role, id) · submitDecision(id)
  signDecision(id, {override, override_reason, note}) · rejectDecision(id, reason)
  getAssets(role, params?) · getAsset(role, assetId) · precheckDisposal(role, assetId, body)
  getOwnership(role, assetId)
  ```

- **핵심 로직**
  1. `ApprovalQueueScreen` 의 `getPoQueue` 3회 호출 → **`getApprovals` 3회**(pending / 종결 2종)로 교체. 목업 폴백 배너(`source==="mock"`)는 그대로 유지 — 조용한 목업 금지 원칙(현행 주석).
  2. `QueueList` 의 링크를 `/manager/po/${poId}` → **`entry.detailHref`** 로. `kind` 배지를 항목에 추가.
  3. 상세는 `kind` 로 분기: `po` → 기존 `PoDetail`(**계약 무변경**), `disposal` → 신규 `DecisionDetail`.
  4. **`DecisionDetail`** 구성:
     - verdict 배너 — `BLOCKED`/`HOLD`/`INSUFFICIENT_FACTS` 는 **경고 톤 + 해소 경로 목록**. ⛔ 절대 성공 톤 금지(D87)
     - blockers·preconditions·holds·insufficient 4버킷 + **인용 조문 칩**(매뉴얼 인용 칩 `CitationChip` 과 시각적으로 구분 — 근거의 성격이 다르다)
     - 승인서·진술보장서 미리보기
     - 증빙 패키지 + **`missing_sections` 를 반드시 렌더**(빠진 절을 숨기면 D65 태도가 무너진다)
     - **`hash_fixed:false` 항목에 "해시로 고정되지 않은 근거" 표시**(D86)
     - `bundle_hash` 모노스페이스 표시
  5. **`SignBar`**:
     - `requiresOverride === false` → "서명하고 확정" 버튼
     - `requiresOverride === true` → 버튼이 **비활성**이고, `override` 체크박스 + **사유 textarea 를 채워야만** 활성화. 사유 없이 제출 자체가 불가능한 UI. ⛔ 자동 체크·기본 사유 문구 금지
     - override 활성 시 경고 배너: *"판정을 뚫고 확정합니다. 사유와 서명자가 기록됩니다."*
     - 409 `evidence_changed` 응답 → **"근거가 변경되었습니다. 다시 검토해야 합니다."** + 재조회 버튼. 무시하고 재시도하는 경로를 만들지 말 것
  6. 에러 표시는 기존 `extractDetail` 재사용 — 403/409/422 를 구분해 보여주는 현행 동작 유지(D38 요점).
  7. `lib/mock/queue.tsx` 의 `PENDING`·`RECENT` 를 새 `QueueEntry` 형태로 갱신 + 처분서 목업 1건 추가.

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | 백엔드 미기동 | 기존 목업 폴백 + 경고 배너(현행 유지) |
  | `kind` 가 `repair` | 목록에 렌더하되 상세는 "Sprint 8 미구현" 안내. **숨기지 않는다** |
  | 모르는 `state` 문자열 | `stateView` 가 `warn` 톤 + 원문 표시. **초록 금지** |
  | `urgency: null` | 배지 자체를 만들지 않는다. `"normal"` 로 채우지 않는다 |
  | `verdict: null`(po) | verdict 영역 미렌더 |
  | 서명 성공 후 | 목록 재조회 + 성공 배너. 상세는 `signed` 상태로 전환되고 **버튼이 사라진다** |

- **지켜야 할 결정**: D18(승인은 채팅 밖) · D38 · D63 · **D85·D86·D87**(착수 전제) · D26·D32·D57(인용 페이지 표시 규약 — 프론트가 계산하지 않는다)
- **DoD**
  - `cd frontend && npx tsc --noEmit` exit 0 · `npm run build` 성공
  - **수동 체크리스트(스크린샷 첨부)**: ⓐ 발주서·처분서가 한 큐에 보인다 ⓑ BLOCKED 처분서의 서명 버튼이 **비활성** ⓒ override 체크 + 사유 입력 후에만 활성 ⓓ 사유 비우면 다시 비활성 ⓔ 서명 후 `signed` 배지 ⓕ `missing_sections` 가 화면에 보인다
  - `uv run python spikes/api_contract.py` 무회귀(백엔드 계약 미변경 확인)
  - `git grep -n "poId" frontend/components frontend/lib` → **`QueueEntry` 관련 잔재 0건**

---

#### MQ-710 — S18 실사 검증 화면 + UI 정직성 회귀 (D87)

- **복무 시나리오**: S18 (사용자 요청 2번)
- **변경 파일**: `frontend/lib/ownership.ts`(신규) · `components/asset/VerificationMatrix.tsx`(신규) · `components/asset/ResidualRiskCard.tsx`(신규) · `app/(console)/technician/asset/[assetId]/ownership/page.tsx`(신규) · `spikes/ui_honesty_contract.py`(신규) · `frontend/lib/__checks__/ui_honesty.ts`(신규)
- **⛔ 금지**: `lib/api.ts`·`lib/types.ts`·`components/queue/**` 접근 (MQ-709 소유)

- **인터페이스 — 순수 함수 계층 (React 무의존)**
  ```ts
  // lib/ownership.ts
  export type ItemState = "VERIFIED" | "UNVERIFIED";
  export type Verdict = "VERIFIED" | "PARTIAL" | "UNVERIFIED";
  export type Tone = "ok" | "warn" | "danger" | "muted";

  /** ★ D87 — 상태→표시의 유일한 total 맵. 이 파일 밖에 사본을 만들지 않는다. */
  export const ITEM_VIEW: Record<ItemState, {badge:string; tone:Tone}> = {
    VERIFIED:   { badge: "확인됨",  tone: "ok"   },
    UNVERIFIED: { badge: "미확인",  tone: "warn" },
  };
  export const VERDICT_VIEW: Record<Verdict, {headline:string; tone:Tone}> = {
    VERIFIED:   { headline: "…", tone: "ok"   },
    PARTIAL:    { headline: "확인되지 않은 항목이 남아 있습니다 — 안전하다는 뜻이 아닙니다",
                  tone: "warn" },
    UNVERIFIED: { headline: "…", tone: "danger" },
  };
  export function itemView(state: string): {badge:string; tone:Tone};
  //   ↑ 맵 밖 값 → { badge: `미확인 (${state})`, tone: "warn" }. 절대 "ok" 아님
  export function toRows(api: OwnershipApi): Row[];
  export function auditRows(rows: Row[]): string[];   // 위반 목록. 비어야 정상
  ```

- **핵심 로직**
  1. `toRows` 는 **9카테고리 전부**를 만든다. 항목 0건 카테고리도 헤더를 만든다 — **빼면 "확인 안 한 것"이 화면에서 사라진다**(`04 §9` 명시).
  2. `auditRows` 가 강제하는 불변식 4가지:
     - `state !== "VERIFIED"` 인 행의 `tone` 이 `"ok"` 이면 위반
     - `state === "UNVERIFIED"` 인데 `limit` 이 비었으면 위반 (*이유 없는 미확인은 만들지 않는다*)
     - `state === "VERIFIED"` 인데 `evidence` 가 비었으면 위반
     - 카테고리 수 ≠ 9 이면 위반
  3. **컴포넌트는 판단하지 않는다.** `VerificationMatrix.tsx` 는 `row.badge`·`row.tone` 을 **그대로** 렌더한다. 자체 조건 분기·색 상수 금지.
  4. `PARTIAL` 배너는 **화면 최상단**에 warn 톤으로, `verdict` 와 `unverified.length` 를 함께 표시. `residual_risk`·`mitigation` 은 `ResidualRiskCard` 로 항상 표시(비어 있으면 "산출 없음"이라고 밝힌다).
  5. 요약 지표는 **"N/M 확인됨" 형태로만** 표시한다. ⛔ **퍼센트 진행바 금지** — 82% 진행바는 "거의 다 됐다"로 읽히는데 `PARTIAL` 의 의미는 정반대다. 이 판단을 코드 주석에 근거와 함께 남긴다.

- **검증 방법 (사용자 질문 5 — 이게 핵심)**

  프론트에 테스트 러너가 없다(실측: `tsc --noEmit`·`next build` 뿐). 러너를 새로 도입하지 않고 **기존 도구만으로** 3층 회귀를 만든다:

  | 층 | 무엇을 잡나 | 방법 |
  |---|---|---|
  | **L1 — 순수 함수 단언** | 매퍼가 미확인을 `ok` 로 만드는가 | `frontend/lib/__checks__/ui_honesty.ts` 를 `npx tsc --outDir <tmp> --module commonjs --target es2020` 로 컴파일 후 `node` 실행. 신규 의존성 0(`tsc` 는 이미 회귀에 있다). `ownership.ts` 는 **React 를 import 하지 않는다** — 이 제약이 L1 을 가능하게 하므로 spike 가 그 사실도 단언한다 |
  | **L2 — 구조 단언** | 컴포넌트가 매퍼를 우회해 자기 색을 칠하는가 | `spikes/ui_honesty_contract.py` 가 `VerificationMatrix.tsx` 소스에서 다음을 **0건**으로 단언: `"확인됨"`·`"VERIFIED"`·`"UNVERIFIED"` 문자열 리터럴 · `--green`·`--ok` 색 토큰 · `state ===` 비교. 즉 **컴포넌트는 스스로 "확인됨"이라 말할 수단이 없다** |
  | **L3 — 렌더 단언** | 실제 자산 9건에서 초록이 새는가 | `next build` 산출이 아니라, **`toRows` 를 시드 9자산의 실 API 응답에 적용**해 `auditRows` 가 빈 배열인지 확인. API 응답은 spike 가 백엔드를 띄워 `GET /api/assets/{id}/ownership` 로 받는다(MQ-709 가 만든 fetcher 와 같은 경로) |

  **뮤턴트 3종으로 먼저 깨뜨린다**(전부 원복):
  ⓐ `ITEM_VIEW.UNVERIFIED.tone` 을 `"ok"` 로 → L1 FAIL
  ⓑ `VerificationMatrix.tsx` 에 `if (row.state === "UNVERIFIED") return <Green/>` 삽입 → L2 FAIL
  ⓒ `toRows` 가 항목 0건 카테고리를 스킵 → L1·L3 FAIL

  **깨지지 않으면 그 검사는 방어선이 아니다** — Sprint 6 이 8번 반복해 배운 것.

  추가로 **큐 상태 라벨도 같은 spike 가 검사한다**: `lib/queueState.ts`(MQ-709 산출)의 `stateView` 가 맵 밖 값에 `"ok"` 를 주지 않는지 L1 에서 함께 단언.

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | `no_host_asset`(INV-L1-01) | "호스트 자산 없음 — 판정 대상이 아닙니다" 안내. ⛔ **"문제 없음"으로 렌더 금지** |
  | 도구가 `internal_error` | 오류 배너. **빈 매트릭스를 "확인 결과 없음"으로 렌더 금지** |
  | 백엔드 미기동 | 목업 폴백 + 경고 배너(화면 B 선례) |
  | `verdict` 가 미지 문자열 | `warn` 톤 + 원문 표시 |
  | `insured=false`(확인된 미부보) | `VERIFIED` 로 표시하되 **`residual_risk` 에 무보험 위험이 남는다**(D78 · `04 §9` 명시) |

- **지켜야 할 결정**: **D87**(착수 전제) · D62 · D78 · D65(추정치 고지) · `11 §6`(PARTIAL 승격 불가)
- **DoD**
  - `uv run python spikes/ui_honesty_contract.py` — **신규 16건**(L1 9 · L2 4 · L3 3), 뮤턴트 3종 사전 확인 기록 첨부
  - `cd frontend && npx tsc --noEmit` exit 0 · `npm run build` 성공
  - `grep -c "import.*react" frontend/lib/ownership.ts` → **0**
  - **수동 체크리스트(스크린샷)**: ⓐ 9카테고리 전부 보인다 ⓑ 미확인 항목이 초록이 아니다 ⓒ 미확인 항목마다 이유(`limit`)가 보인다 ⓓ `PARTIAL` 배너에 "안전하다는 뜻이 아닙니다" ⓔ 진행바가 없다 ⓕ 분전반(`INV-L1-01`)이 "문제 없음"으로 보이지 않는다

---

#### MQ-711 — S9→S10 처분 진입 화면 (정비사 콘솔 → 승인 큐 관통)

- **복무 시나리오**: S9 · S10
- **변경 파일**: `frontend/components/asset/DisposalPanel.tsx`(신규) · `components/asset/AssetHeader.tsx`(신규) · `components/asset/FindingList.tsx`(신규) · `app/(console)/technician/asset/page.tsx`(신규, 자산 목록) · `app/(console)/technician/asset/[assetId]/disposal/page.tsx`(신규)
- **⛔ 금지**: `lib/api.ts`·`lib/queueState.ts`·`lib/ownership.ts`·`components/queue/**`·`components/asset/VerificationMatrix.tsx` 접근

- **핵심 로직**
  1. **자산 목록** — `getAssets` 로 9자산 + `equipment_count`. 라인 필터. `asset_id` NULL 인 인버터는 여기 안 나온다(자산이 아니므로).
  2. **처분 사전판정 패널**
     - `disposal_mode` 3지 선택(`SALE`/`SCRAP`/`TRANSFER`) + `disposal_date` 입력
     - ⚠ **`disposal_date` 를 오늘로 자동 채우지 말 것** — `build_facts` 가 "모르는 날짜를 오늘로 대체하지 않는" 이유가 그대로 UI 에 적용된다(D62). 비어 있으면 "미입력 시 세액공제 조항이 사실 부족으로 남습니다" 안내만 띄운다
     - `precheckDisposal` 호출. **200 과 409 를 같은 화면으로 렌더**한다(`06 §2.5` — 409 본문이 200 과 같은 형태인 이유가 정확히 이것)
     - verdict 배너 + 4버킷(`FindingList`) + `citations` 조문 칩 + `resolve_options` + `missing_facts` + `not_considered`·`disclaimer`
     - **`evidence_completeness: LAW_TEXT_PENDING` 을 화면에 표시**한다. 숨기면 근거 상태를 사용자가 모른다
  3. **"처분서 초안 요청" 액션** — 채팅으로 자연어 요청을 보내는 대신 **명시적 버튼**. D29 가 "이력 기록은 명시적 액션"이라 한 것과 같은 태도.
     ⚠ 이 버튼이 호출하는 것은 **MCP 도구가 아니라 `/api/chat` 도 아니다.** 도구는 에이전트만 부른다(D15·D10). 화면 버튼은 `POST /api/chat` 으로 "이 자산의 처분서 초안을 만들어 줘" 를 보내 **에이전트가 도구를 부르게** 하거나, 사람 전용 경로가 필요하다.
     → **결정 필요 지점.** 두 안:
       - (가) 채팅 경유 — 에이전트 오케스트레이션 서사에 부합하고 신규 API 0. 단 SSE 스트림을 이 화면이 소비해야 해서 화면이 무거워진다
       - (나) `POST /api/decisions`(사람 전용 draft 생성) 신설 — 화면은 단순해지지만 **쓰기 경로가 2개**가 되어 `generate_disposal_document` 의 존재 이유가 흐려진다
     → **(가)를 권고한다.** 근거: 이 프로젝트의 주제가 도구 오케스트레이션이고(CLAUDE.md), 승인 큐 진입은 D18 대로 채팅 밖에서 일어나므로 "요청은 에이전트, 결재는 큐"라는 기존 분업이 그대로 유지된다. **구현**: 버튼 → `/technician?prefill=…&equipment=…` 로 이동해 채팅 컴포저에 문장을 채워 넣고 **전송은 사용자가** 누른다(자동 전송 금지 — 사람이 무엇을 요청하는지 보고 눌러야 한다). 이 안이면 신규 API 0, 신규 SSE 소비 0.
     ⚠ 이 선택은 **MQ-712 가 `06_REPO_API` 에 기록**해야 한다.
  4. **관통 배선 확인 링크**: 초안 생성 후 채팅의 결과 카드에서 `/manager/decision/{id}` 로 이동 가능해야 한다(MQ-709 가 만든 라우트).

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | 409 응답 | **정상 렌더**(에러 화면 아님). "지금 상태로는 처분 불가 + 해소 경로" |
  | 503(카탈로그 미적재) | "서버 설정 문제 — 관리자 문의" (500 과 구분, D71) |
  | 422(enum·날짜) | 입력 필드 옆 인라인 오류 |
  | `verdict: CLEAR` 인데 mode=SALE | **발생하지 않는다**(D78 부수 확정). 그럼에도 나오면 warn 배너 — 계약 위반 신호 |
  | 조문 미수집 | `LAW_TEXT_PENDING` 배지 + "서명용 증빙은 아직 만들 수 없습니다" |

- **지켜야 할 결정**: D71(precheck 무저장·403 없음) · D62 · D79 · D18 · D29(명시적 액션) · D26·D32
- **DoD**
  - `cd frontend && npx tsc --noEmit` exit 0 · `npm run build` 성공
  - **수동 체크리스트(스크린샷)**: ⓐ `AST-L3-CONV` SALE → BLOCKED 2건이 조문 인용과 함께 보인다 ⓑ `AST-L4-WRAP` SALE → HOLD 가 "전문가 검토"로 안내된다 ⓒ `AST-L4-DUST` → INSUFFICIENT_FACTS 가 `missing_facts` 와 함께 보인다 ⓓ `AST-L3-LIFT` SCRAP → CLEAR ⓔ `disposal_date` 가 자동으로 채워지지 않는다 ⓕ 초안 요청 → 채팅 → 승인 큐 → 서명까지 **한 번에 관통**
  - MQ-708 의 `s10_smoke.py` 무회귀

---

#### MQ-712 — 계약 문서 정합 + D81~D88 기입

- **복무 시나리오**: 전체 (문서가 코드와 어긋나면 다음 스프린트가 잘못된 전제로 출발한다)
- **변경 파일**: `docs/10_DECISIONS.md` · `04_MCP_TOOLS.md` · `06_REPO_API.md` · `11_ASSET_LIFECYCLE.md` · `12_MAINT_VALUE.md` · `00_MVP_SCOPE.md` · `07_BACKLOG.md` · `03_WIREFRAME.html` · `README.md` · `CLAUDE.md`
- **핵심 로직 — 반드시 **코드와 대조**해서 쓴다 (MQ-613 이 문서 5건의 거짓을 잡은 방식)**
  1. **D81~D88 기입** + 전 문서의 D 범위 표기 `D1~D80` → `D1~D88` (**기입 전 `git grep -n "D1~D80"` 으로 대상을 전부 찾을 것** — Sprint 6 에서 4곳이었다)
  2. `04_MCP_TOOLS` — **§15 `generate_disposal_document` 신설**(코어 7 + 확장 **8**). §14 번들 스키마를 5키로 갱신 + `rule_hash` 산출 규약 + `asset_modified` reason 추가. reason 색인 갱신
  3. `06_REPO_API` — **§2.6 `/api/decisions` · §2.7 `/api/approvals` 신설**(D85). §2.4 상태 전이 다이어그램에 `decisions` 추가. **§2.2 `/api/po` 는 손대지 않는다**(무변경이 계약이다)
  4. `11_ASSET_LIFECYCLE` — §5 표에서 `generate_disposal_document` **"미구현" 해제**. §8 F3 완료 표시. **§8 법령 수집 체크리스트를 MQ-701 실측으로 갱신**(몇 건이 실제로 수집됐는지). §2 계층 3 예시를 실제 번들 5키로 교체
  5. `12_MAINT_VALUE` — §8 증빙 패키지에 **"4종 중 3종 제공, 감가상각 명세는 원천 없음"** 명시. §10 표에서 `create_repair_record` 를 **Sprint 8** 로 정정
  6. `00_MVP_SCOPE` — 확장 기능 9(부분)·11(계층 3 완료)·12 상태 갱신. 인프라 절 "확장 7종" → **8종**. 테이블 수 재확인
  7. `07_BACKLOG` — **P24 완료 표시**. P25(S19)를 Sprint 8 로 명시. **⛔ P1~P23·P26~P29 승격 금지**
  8. `03_WIREFRAME.html` — 화면 B 에 처분서 카드·서명 바, 신규 자산 화면 2종 반영
  9. `CLAUDE.md` — 회귀 스위트 목록에 신규 5종 추가(`bundle_integrity`·`disposal_sign_contract`·`s10_smoke`·`approvals_contract`·`ui_honesty_contract`). **절대 규칙 1번에 `decisions` 추가**: *"MCP 도구는 `po_drafts`·`decisions` 에 draft INSERT 만 가능"*
  10. `README` — 도구 수·회귀 건수·D 범위를 **러너 출력 실측치**로
  11. **MQ-711 이 택한 초안 요청 경로**(채팅 경유)를 `06 §2.1` 과 `02_SCENARIOS` S10 에 기록
  12. **S17·`detect_law_revision` 이 v2 로 제외됐고, `check_revisions()` 는 코드에 살아 있으나 도구로 노출하지 않는다**는 사실을 `11 §10-3` 에 명시
- **엣지 케이스**: 문서가 주장하는 수치와 실측이 다르면 **실측을 쓰고 차이를 기록**한다 / 코드와 대조 불가한 주장은 삭제한다
> ### Stage 2 인계 — `04 §14` 에 반드시 반영할 것
>
> 1. **번들 3키 → 5키 (D83)** — `laws` · `rules`(**`rule_hash` 추가**) · **`evaluated`** · **`contracts`** · `facts`.
>    §14 코드블록 위에 Stage 2 가 붙여 둔 `⚠⚠ 아래 예시는 낡았다` 경고를 **지우고** 실제 스키마로 교체한다.
> 2. **`hash_spec` 필드** — 번들 **밖**(N1). 안에 넣으면 스펙 문자열 수정이 과거 서명을 전부 깬다.
> 3. **`asset_modified` reason 신설** (N2 — 판정 전후 자산 행 재읽기).
> 4. **`contracts[]` 는 `law_text_unavailable` 검사 대상이 아니다** — 넣으면 `LIEN-CONSENT` 자산 번들이
>    구조적으로 영원히 불가능해진다. 이 경계를 문서에 남긴다.
> 5. **🔴 실패 어휘 불일치 해소** — 엔진이 던지는 `KeyError`/`TypeError`/`ValueError` 를
>    **`§8`(`check_disposal_blockers`)은 `engine_error`, `§14`(`build_evidence_bundle`)는 `internal_error`** 로 낸다.
>    같은 실패가 도구마다 다른 이름인데, 이건 §14 가 스스로 경고해 둔 바로 그 상태다.
>    MQ-705 가 MCP 도구 경유를 끊으면서 생겼다. **어느 쪽으로 통일할지 정하고 문서·코드를 함께 고쳐라.**
>    통일 후 `spikes/bundle_integrity.py` ⑳(두 도구 어휘 대조)에 **엔진 예외 케이스를 추가**해 잠글 것.

- **DoD**
  - **코드 대조 단언 40건 이상**을 태스크 보고에 표로 첨부(MQ-613 선례: 46건)
  - `git grep -n "D1~D8[0-7]"` → 오래된 표기 0건
  - `git grep -n "미구현.*generate_disposal_document"` → 0건
  - `git grep -n "확장 7종"` → 갱신 누락 0건
  - 회귀 무영향(문서 전용)

---

#### MQ-713 — 지표 튜닝 + 4차 평가

- **복무 시나리오**: S1~S4 (완료 기준 5지표)
- **변경 파일**: `backend/agent/prompts.py` · `backend/agent/loop.py` · `eval/results/*`(신규) · `data/analysis/eval_gap_4th.md`(신규)
- **선행**: MQ-703(원인 분석)
- **⛔ 금지**: `eval/testset.json` 수정(사람 승인 완료본 — 고치면 3차와 비교 불가) · `eval/score.py` 판정 완화 · `MAINTQ_TOOLS_PROFILE=full` 로 평가

- **핵심 로직**
  1. **MQ-703 의 `eval_gap_3rd.md` 후보 목록에서만 고른다.** 새 가설을 즉석에서 만들지 않는다.
  2. **한 번에 하나의 축만 건드린다** — D56·D69 가 반복해 지킨 원칙. 프롬프트와 루프를 같이 고치면 어느 쪽이 효과였는지 분리 불가.
  3. **2차 실측이 가리키는 우선순위**(내가 결과 MD 에서 확인한 군집):
     - **T13·T14·T15(S2 3문항)가 부품·인용·안전 3지표를 동시에 실패**한다. 셋 다 `elapsed 4~6초`로 다른 문항의 1/3 — **도구를 거의 안 부르고 끝났다**는 신호다. 여기 하나를 고치면 3지표가 함께 움직일 수 있다. **가장 먼저 볼 것**
     - 안전 추가 실패 T06·T09·T11·T16 은 `DANGER_KEYWORDS` 트리거 미발화 가능성 — `prompts.py` 의 키워드 집합과 해당 문항 응답 텍스트를 대조
     - 부품 특정은 D66(`parts` 필드)·D76(구조 보존)이 **이미 판정 소스를 바꿨다**. 3차 수치를 먼저 보고 판단 — 3차에서 이미 올랐으면 추가 수정 불필요
  4. **안전 문구 자체는 건드리지 않는다.** `SAFETY_BASELINE` 은 사람 승인 대상이다(`TODO_직접할일.md`). 고칠 수 있는 것은 **발행 조건**(트리거·시점)뿐이며, 문구 변경이 필요하다고 판단되면 **수정하지 말고 사람 승인 항목으로 보고**한다.
  5. 4차 실행 → `eval_gap_4th.md` 에 3차 대비 증감 + **어떤 수정이 어느 문항을 어떻게 바꿨는지 문항 단위로** 기록.
  6. **5차는 조건부다**: 4차에서 남은 실패가 **단일 원인 군집**으로 특정되고 그 수정이 프롬프트·루프 범위 안이면 1회 더. 그렇지 않으면 **Sprint 8 로 이월하고 이유를 적는다.** ⛔ 목표 미달을 숨기거나 판정을 완화하지 말 것.

- **엣지 케이스**
  | 상황 | 동작 |
  |---|---|
  | 4차가 3차보다 **나빠짐** | 수정을 **되돌린다.** 되돌린 사실과 이유를 기록 |
  | LLM 응답 변동으로 판정이 흔들림 | 같은 커밋에서 2회 실행해 변동폭을 기록. **1회 결과로 개선을 주장하지 않는다** |
  | 부품 특정이 목표 미달 | `related_parts` 사람 최종 승인이 **선행 조건**임을 명시(D12). 승인 전 수치는 실적이 아니다 |
  | 안전 경고가 문구 변경 없이 100% 불가 | 사람 승인 항목으로 보고 후 **Sprint 8 이월** |
  | 키 없음 | 태스크 전체를 Sprint 8 로 이월. 스프린트 종료를 막지 않는다 |

- **지켜야 할 결정**: D69·**D88** · D56 · D12 · D2(안전 문구는 사람 승인) · D22·D54·D66(판정 소스 불변)
- **DoD**
  - `eval/results/<4차>.md` — `tools_profile: core` 기록
  - `data/analysis/eval_gap_4th.md` — 3차 대비 문항 단위 증감 + 수정↔문항 대응표
  - `uv run python spikes/prompt_rules.py` 무회귀(규칙 수 유지)
  - `uv run python spikes/agent_loop_contract.py`·`eval_score_contract.py` 무회귀
  - **미달 지표가 남으면 `sprint-7.md` 에 "무엇이 왜 남았고 다음에 무엇을 시도할 것인가"를 남긴다.** 미달을 감춘 종료는 실패 판정

---

---

# 완료 기준 달성 계획

## 사용자 요청 3건

| 요청 | 어느 스테이지에서 어떻게 증명하는가 |
|---|---|
| **① S9→S10 end-to-end** | **Stage 4 MQ-708 `s10_smoke.py`** 가 `precheck → 도구 draft → submit → /api/approvals 노출 → 상세 → sign → state='signed'` 를 **실 서버·실 MCP** 로 관통. **Stage 6 MQ-711** 이 UI 관통(수동 체크리스트)을 더한다 — **기계 증명 + 사람 확인 2층** |
| **② BLOCKING 우회 처분 0건** | **4층 방어를 각각 독립으로 회귀**: ⓐ 도구 스키마에 `override` 키 **부재**(D81) ⓑ MCP 커넥션 TEMP TRIGGER ⓒ REST `sign()` 409 `override_required` ⓓ **DDL CHECK**. **시드 9자산 × 3모드 전수**로 BLOCKING 조합 전부 시도. **뮤턴트 4종으로 먼저 깨뜨려** 각 층이 실제로 잡는지 확인 |
| **③ 서명 없는 처분 확정 0건** | **DDL CHECK** `state<>'signed' OR (signed_at IS NOT NULL AND reviewed_by IS NOT NULL AND bundle_hash 비어있지 않음)` — **DB 가 거부하므로 코드 버그로도 뚫을 수 없다.** + 불변식 쿼리 + technician 403 + 직접 SQL 뚫기 2건이 CHECK 위반으로 실패 |

## `00_MVP_SCOPE §완료 기준` 5지표

| 지표 | 현재 | 계획 |
|---|---|---|
| 부품 특정 ≥90% | 26.7%(2차) | **"미달"이 아니라 "판정 불가"로 분리 기재** — `related_parts` 사람 승인 전이라 D12 상 어떤 수치도 실적이 아니다. 3·4차 수치는 **참고치**로만 싣고 승인 여부를 함께 표기 |
| 인용률 100% | 83.3% | Stage 1 MQ-703 측정(core 고정, D88) → 원인 분석 → Stage 7 MQ-713 튜닝 + 4차. 실패 3건이 **전부 S2(T13~T15)** 라 단일 원인 군집 가능성을 먼저 검증 |
| 안전 경고 누락 0 | 61.1% | 동일 경로. ⛔ **문구는 사람 승인 대상이라 건드리지 않고 발행 조건만** 조정 |
| 미지 코드 환각률 0% | PASS | 유지 확인. 확장 도구는 `core` 에 안 보이므로 영향 없음 |
| 권한 위반 403 100% | PASS | `/api/po` 형태 **불변**(D85)으로 기존 판정 경로 보존 + **신규 403 경로 2건**(`decisions.submit`·`sign`). ⚠ `precheck`·`ownership` 에는 **403 을 만들지 않는다**(D71) |

### 정직한 판정

- **이건 기능 구현이 아니라 측정 → 원인 분석 → 튜닝 루프다.** 그래서 Stage 1(측정)과 Stage 7(튜닝)을 갈랐다 — 붙이면 튜닝이 추측이 된다
- **계획하는 반복은 2회**(3차 기준선 + 4차 검증). 조건부 5차 1회
- ⚠ **수렴을 약속하지 않는다.** 2차 실측이 보여 주는 것은 실패의 **군집**이지 원인이 아니다.
  **3회 안에 5지표 전부 통과한다는 근거는 지금 없다** — 있다고 쓰면 그게 근거 없는 추정이다
- **D69 기준선은 Sprint 7 종료 시점에도 유효하다** — 확장 도구를 1종 더 얹지만 `full` 에서만 등록되고 평가는 `core` 로 돈다

---

# 회귀 계정

| 기준 | 현재 | 증분 | 종료 시 |
|---|---|---|---|
| **spikes + seed** | **414**(spikes 396/21스위트 + seed 18) | law_fetch +8 · disposal_api +2 · rules_db_load +4 · eval_score +2 · bundle_integrity **+14** · write_tool +8 · approvals **+18** · **ownership_api +10** · disposal_sign **+22** · s10_smoke **+12** · ui_honesty **+13** · seed **+3** = **+116** | **≈530 / 27스위트** |
| **pytest**(별도 기준) | 41 | test_rules +5 | **46** |

⚠ **위 숫자는 목표가 아니다.** 건수는 **러너 출력이 기준**이며 **직전 실행보다 줄었다면 테스트가 사라진 것**으로 판정한다.

**공통 회귀 명령**
```
uv run python data/seed.py --with-error-codes          # ⛔ --today 금지
uv run --with pytest python -m pytest data/rules/test_rules.py -q
uv run python spikes/<각 스위트>.py                     # 21 + 신규 6
uv run ruff check data backend mcp_server spikes eval
cd frontend && npx tsc --noEmit && npm run build        # Stage 5 이후
```
플래키 3스위트는 **MQ-704 이후 재시도 없이 통과해야 한다.** 재시도가 필요하면 MQ-704 가 실패한 것이다.

---

# 사람 선행 / 승인 항목

## ✅ 해소됨

- **D81~D88 승인** — 2026-08-09 전부 승인, `10_DECISIONS.md` 기입 완료
- **`LAW_API_OC`** — 발급·실호출 검증 완료(7/7 조문 본문 도달)
- **`KR-STTC-146` title 정정** — 2026-08-09 승인. `세액공제액의 추징` → **`감면세액의 추징`** 적용 완료

## 🔴 스프린트 중 — 우선순위 순

| 항목 | 언제 | 막히는 것 |
|---|---|---|
| **`related_parts` 사람 최종 승인** | MQ-713 전 | 부품 특정 정확률이 **"판정 불가"** 로 남는다(D12). 완료 기준 5지표 중 1개가 구조적으로 확정되지 않는다 |
| **처분 승인서·진술보장서 문안 검수** ⭐신규 | MQ-706 후 · 데모 전 | **법적 효력이 있는 문서**다. 안전 문구(D2)와 같은 성격 — 승인 전까지 출력에 `unreviewed_template_notice` 가 붙는다 |
| **`SAFETY_BASELINE` 문안 검수** | MQ-713 중 | 발행 조건 조정만으로 안전 경고 100% 가 안 되면 문구를 손대야 하는데 그건 사람 승인 대상. **MQ-713 은 수정하지 않고 보고만 한다** |
| **`N = 8` 기준내용연수 대조** | MQ-701 직후 | 잔가곡선 전체. **`LAW_API_OC` 가 생겼으므로 별표5·6 을 함께 수집 시도 가능** — 값 채택은 사람 판단 |
| **`KR-CITA-ENF-31` title 정정** | 여유 있을 때 | `즉시상각의제` vs `즉시상각의 의제`(공백). `classify_expenditure` 전용이라 **S10 무영향** |
| `RESIDUAL_AT_LIFE_END = 0.50` 동의 · `parts.part_class` 40종 감수 | Sprint 8 전 | `assess_repair_value` 3지 판단 |

## 🟢 기존 이월

시드 부품명·가격 감수 · `data/raw/IE5_..._200617 (1).pdf` 중복 삭제 ·
`data/maintq.db.before-reseed-20260808` 정리 · 데모 영상 · README GIF·평가 결과표

---

실행: `/stage 1`
