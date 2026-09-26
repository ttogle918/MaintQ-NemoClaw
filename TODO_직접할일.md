# 직접 해야 할 일 (사람 손 필요)

Claude가 대신 못 하는 것들. 순서대로.

## 지금 (M1 시작 전)

> 🔵 **이 절 전체가 오래 미체크로 낡아 있었다 (2026-09-16 실측 정정).** M1 은 Sprint 1 에
> 끝났는데 체크박스가 착수 시점 그대로였다. 각 항목에 **확인한 근거**를 함께 적는다 —
> 근거 없이 체크만 옮기면 다음 사람이 또 의심한다.

- [x] ~~**LS일렉트릭 매뉴얼 다운로드**~~ — **완료.** `data/raw/` 에 `iG5A_Troubleshooting_Rev1.0_150415.pdf` ·
  `S100_Manual_Korean_V4.2.pdf` · `IE5_User Manual(Standard|Simple)_Kor_V1.0` 이 있고,
  추출·적재까지 끝났다(`error_codes` **70행** = iG5A 24 / S100 41 / IE5 5, RAG 코퍼스 1,229청크).
  - ⚠ iG5A 는 **완전본이 아니라 트러블슈팅본**으로 착지했다 — 보호기능·에러 표가 여기 있어
    목적은 충족됐다(D24~D27). 이후 IE5 2종이 추가돼 매뉴얼은 **3기종**이 됐다(D109·D110)
- [x] ~~AI허브(aihub.or.kr) 회원가입 + 「기계시설물 고장 예지 센서」 다운로드 **승인 신청**~~ —
  **완료 — 다만 다운로드 승인은 결국 불필요했다.** D16 의 취지가 *"적재가 아니라 **분포 참고**"*
  라서 4종 고장 유형 분포만 참고해 `error_history` 200건을 생성했다
  (근거 주석: `data/seed.py:1269`, 경위: `data/data_list.md:430`)
- [x] ~~GitHub 레포 생성 (`MaintQ`) + 이 폴더 초기 커밋~~ — **완료.**
  `origin = https://github.com/ttogle918/MaintQ.git`. `.gitignore` 의 `data/raw/` 차단도 걸렸고,
  이후 **예외 1건**이 생겼다 — `data/raw/external/` 만 negation 으로 추적한다(D103, 절대규칙 5 ㉠)
- [x] ~~Anthropic API 키 준비~~ — **완료.** `.env` 에 `ANTHROPIC_API_KEY` 존재(2026-09-16 확인).
  다만 **주력 provider 가 아니다** — `MAINTQ_LLM_PROVIDER` 기준 실운용은 gpt-oss/Elice/NVIDIA 쪽이고
  `anthropic` SDK 는 선택적 의존성으로 지연 import 된다(`backend/agent/llm.py:86`)
- [ ] **Anthropic 월 비용 상한 설정** — ⚠ 위 항목에서 **분리했다.** 키 존재는 레포에서 확인되지만
  상한은 Anthropic 콘솔 설정이라 **여기서 확인할 방법이 없다.** 설정했다면 이 줄을 체크할 것

## M1 중

- [x] ~~안전 문구 정정 승인: "5분" → "10분 이상"~~ — 승인·전파 완료 (2026-07-18): 02_SCENARIOS·03_WIREFRAME·safety-guardrail 스킬·06 testset 기준에 매뉴얼 근거 페이지와 함께 반영
- [x] ~~추출 전략 승인~~ — D24로 확정 (pdfplumber 텍스트 규칙 파싱)
- [x] ~~**iG5A 매핑 최종 확인**~~ — **2026-07-28 승인 완료.** ② 4건은 180dpi 재렌더링 이미지로
  재확인(COL=입력결상 등 표대로), ③ 2건 결정: `__L` 표기 그대로 채택 + canonical 정책(키패드
  표기 기준, 통신 비트명은 aliases) 제안대로 승인. `ig5a_code_map.json` 갱신 →
  `extract_error_codes.py` 재실행(`_status` 는 이제 맵 파일에서 자동 유도, 하드코딩 아님) →
  `seed.py --with-error-codes` 로 iG5A 24 + S100 41 = **65건 적재 완료**.
  검수표: `data/analysis/ig5a_code_mapping.md` (완료 기록 남김)
  > ⚠ **위 절차 기록은 그대로 유효한 완료 기록(과거형)이다.** 다만 **정본 갱신 경로가 이후 바뀌었다** —
  > Sprint 9(MQ-921, D99)부터는 재추출만으로 곧장 정본이 덮이지 않는다. `extract_error_codes.write_canonical()`
  > 가 유일한 쓰기 경로이고, `_status` 되돌림(승인→초안) 등 회귀 조건을 감지하면 **쓰지 않고 중단**한다
  > (exit 1/2). `--candidates-only` 는 후보 파일만 갱신하고 정본(`error_codes.json`)에는 손대지 않는다.
  > actions 결측 회수(MQ-919, 아래 `## actions 검수` 참조)도 이 가드를 통과해야 정본에 반영된다.
- [x] **`related_parts` 수작업 매핑 검수** — ✅ **2026-08-12 사용자 최종 승인 완료 (D12 게이트 해제)** — 파일: `data/related_parts.seed.json`.
  **2026-08-05 Claude 위임 판정 완료(8코드)** — 사용자가 이 건에 한해 위임. 매뉴얼 조치문
  (iG5A p.202~204 · S100 §9.2 p.420~421)을 직접 대조해 판정했고, 각 항목에
  `reviewed_by: "claude (사용자 위임, 2026-08-05)"` 와 `verdict` 를 남겼다.
  주요 변경: iG5A OCT 에서 모터 제거 · iG5A GFT 에 모터 추가 · **S100 OCT 반려(빈 목록)** ·
  S100 GFT 신규. 근거는 `docs/sessions/2026-08-05.md` §2.
  - [x] **사람 최종 승인 — 2026-08-12 완료.** 사용자가 내용을 확인하고 승인했다.
    위임 이력은 지우지 않고 두 단계를 모두 남긴다(`_승인_이력`) — 누가 무엇을 판단했는지가 지워지면 승인의 의미가 사라진다.
  - ✅ 이제 부품 특정 정확률을 **실적으로 인용할 수 있다**. 첫 실적: **40.0%**(목표 ≥90%, `20260812-075303` 3회차)
- [x] ~~두 기종 간 동일 표기 코드 목록 확인 (OL, OC 계열) — "같은 코드, 다른 의미" 실증 자료~~ —
  **완료.** 교집합 **12종** 확정: `BX` `ETH` `EXT` `FAN` `GFT` `LVT` `NTC` `OC2` `OCT` `OHT` `OVT` `POT`
  (`data/analysis/manual_eda.md:63`). 이 목록이 **D6 의 근거**가 됐다 — `model` 파라미터를
  enum 으로 강제하는 이유가 여기서 나온다
- [ ] 시드 데이터의 부품명/가격이 현실적인지 감수 (냉각팬 3만원대 등)
- [x] **`parts.part_class` 40종 감수 — 2026-08-13 승인 완료.** 파일: `data/seed.py` 의 `PART_CLASS` 상수.
  `CONSUMABLE` 14 / `CRITICAL` 26. **`assess_repair_value` 의 수리/교체/매각 3지 판단에 직접 영향**한다.
  - 사용자가 40종 전량을 확인하고 **초안 그대로 승인**했다 (변경 0건). 추측 분류 9종
    (히트싱크·키패드·센서 3종·접촉기·SPD·커플링·제동저항·케이블)과
    `FAN-IG5-01 = CRITICAL`(S1 주인공, 3지 판단 데모 성립 조건)에 모두 동의.
  - `data/seed.py` 의 `PART_CLASS_REVIEWED = True` 로 반영. 시드 출력이
    `[사람 검수] ✓ part_class 40종 사람 검수 완료` 로 바뀐다.
  - ✅ 이제 3지 판단 결과를 **실적으로 인용할 수 있다** (`related_parts` D12 해제와 같은 성격).

## Sprint 7 사람 판단 대기 (지금 가장 급한 것)

> **외부 블로커는 해소됐다.** `LAW_API_OC` 발급·조문 실수집이 끝나 스프린트를 막는 항목은 없다.
> 남은 것은 전부 **사람의 값 판단**이며, 미해결 상태로도 코드는 돈다(그 사실이 출력에 드러난다).
>
> 📌 **확인 시점: 스프린트 종료 후 일괄** (2026-08-10 사용자 결정). 스테이지마다 멈추지 않고
> 여기에 누적한다. Stage 별 자동 파이프라인은 이 항목들에 막히지 않고 계속 진행한다.

### 🔐 Stage 1 — 보안 (해결됨)

- [x] ✅ **법제처 인증값 평문 — 2026-08-13 히스토리 재작성 후 push 완료** (선택지 ⓑ)
  - 🚨 **이 항목이 "커밋 2개" 로 적혀 있었는데 실제로는 10개였다.** push 직전 전수 검색
    (`git rev-list --all` × `git grep`)에서 드러났다 — `c3a46c8`·`4dc6448` 외에
    `05422e1`·`3a9b2a3`·`5d2bebf`·`8787357`·`9999fc2`·`9ecc405`·`ddb4e71`·`f9472dc` 에도
    있었다. 평문이 `.env.example` 과 `docs/sessions/2026-08-09.md` 에 들어간 채로
    **후속 커밋들이 그 파일을 계속 실어 날랐기** 때문이다.
    **⚠ 교훈: "몇 개 커밋" 을 기억이나 기록에 의존하지 말고 push 직전에 전수 검색할 것.**
  - 조치: `git filter-repo --replace-text` 로 값 → `<LAW_API_OC>` 치환.
    치환 대상은 **3줄뿐**이었고, 그 문자열이 이메일·URL 로 쓰이지 않음을 먼저 확인했다
    (`<값>@`·`github.com/<값>` 추적 파일에서 0건).
    ⛔ 잘린 값 `ttogl`(5자)은 **일부러 안 건드렸다** — `C:\Users\ttogl\...` 경로가 곳곳에 있어
    치환하면 대량 파손이 난다
  - 검증 3종: HEAD 트리 `51ec64b…` **동일**(내용 손실 0) · 커밋 수 **127 → 127** ·
    평문 잔존 **0개**(로컬 전체 · 원격 전수 각각 확인)
  - **force push 불필요했다** — 원격 기준점 `c118074` 가 인증값 도입(08-09) 이전 커밋이라
    재작성 영향을 안 받았고 HEAD 의 조상으로 남아 **fast-forward** 로 올라갔다
    (`c118074..42ea37f`)
  - 📦 **재작성 이전 상태 백업**: `C:\Users\ttogl\workspace\_maintq-backup\pre-filter-20260813.bundle`
    (2.4MB · 전체 ref · `git bundle verify` 통과 · 이전 HEAD `a045bac` 포함).
    ⛔ **저장소 밖에 둔다** — 이 번들에는 평문이 그대로 들어 있으므로 저장소에 넣으면 원상복구된다.
    로컬 브랜치 `backup/pre-filter-20260813` 은 filter-repo 가 함께 재작성해 **이미 평문이 지워진**
    상태다. 진짜 원본은 번들 쪽이다
  - 재발 방지: 회귀 `spikes/law_fetch_contract.py ⓚ` 가 추적 파일에 평문이 없음을 단언한다.
    `.env` 는 `.gitignore:18` 로 차단

### 📄 Stage 1 — 조문 정정 승인

- [x] ✅ **`KR-CITA-ENF-31` 제목 정정 — 2026-08-13 승인·수집 완료.** 등록 `즉시상각의제` → `즉시상각의 의제`
  - **계층 1 이 8/8 `FETCHED` 로 완성됐다** (총 8,197자 · 해시 전건 무결)
  - 부수 확인: `verification_note` 가 물었던 *"자본적 지출 정의가 몇 조 몇 항인가"* 도 답이 나왔다 —
    **이 조 제2항**이 맞고 `law_ref_id` 정정은 불필요했다 (제3항에 소액수선비 기준 600만원·5%·3년)
- [ ] **`KR-STTC-146` 정정 확인** (`세액공제액의 추징` → `감면세액의 추징`, 2026-08-09 승인분)
  - BLOCKING 룰 `TAX-CREDIT-2Y` 의 **근거 조문 정체성 키**를 바꾼 변경이라 눈으로 한 번 더 볼 값

### 📊 Stage 1 — 3차 평가 결과 판단

- [ ] **`data/analysis/eval_gap_3rd.md` §6 후보 6건의 우선순위 동의 여부**
  - 계측(traces 보존 · 반복 실행)을 프롬프트 수정보다 **앞**에 뒀다 — 지금은 개선과 실행 간 요동을 구분할 수 없기 때문
  - ⚠ S2 안전 경고 누락은 **고치면 안 되는 실패**다. 매뉴얼 근거가 없어 안전 문구를 못 낸 것이며,
    문구를 넣는 방향으로 고치면 절대 규칙 위반이 된다. 고칠 것은 RAG 미호출이다
- [ ] **`docs/status/maintq-data-map.html`** — 법령 원문 배지를 `앞으로 만들 데이터 → 실제 데이터` 로 옮겼다.
  3분류 축 재배치가 의도와 맞는지

- [x] ✅ **law.go.kr OPEN API 활용신청 → `.env` 의 `LAW_API_OC` 기입** — **완료.** 발급·실호출 검증까지 끝났고
  Sprint 7 MQ-701 이 조문을 실수집했다 (`data/analysis/law_fetch.md`)
  - ⚠ **인증값은 API 키가 아니라 "신청 이메일 ID 앞부분"** 이다. 그래서 변수명에 "KEY" 가 들어가지 않고
    **`LAW_API_OC`** 다 (구 변수명 폴백은 `data/rules/fetch_laws.py:41` 한 곳에만 남아 있다)
  - 기입 위치: `.env` (`.env.example §외부 데이터 원천` 참고). ⛔ **값 자체는 저장소·로그·문서 어디에도 적지 않는다**
    — 회귀 `spikes/law_fetch_contract.py ⓚ` 가 추적 파일에 평문이 없음을 단언한다
  - **풀린 것**: 조문 6건 수집 완료 → `build_evidence_bundle` 이 9자산 × SALE/SCRAP **18조합 전부 `ok`**
    (`law_text_unavailable` 0건) → 계층 3 서명·S10 의 하드 선행 조건이 사라졌다

- [x] ✅ **`KR-CITA-ENF-31` 등록 제목 정정 승인 — 2026-08-13 완료** (위 §조문 정정 승인 항목과 같은 건)
  - 등록값 `즉시상각의제` → 법제처 `조문제목` `즉시상각의 의제` (**공백 1칸 차이**)
  - 수집기가 **자동 정정하지 않고 중단**한 것(`LawMismatchError`, D75)이 정상 동작이었다 —
    사람이 제목을 고친 뒤에야 수집됐다. 파일에 원문을 손으로 쓰지 않고 `fetch_laws` 로 받았다
  - **계층 1 = 8/8 `FETCHED`.** `classify_expenditure` 의 `evidence_completeness` 도 풀렸다

### ✍️ 처분 문서 문안 검수

- [x] ✅ **처분 승인서·진술보장서 문안 검수 — 2026-08-13 완료 (수정 없이 승인, D90)**
  - 검수 자료: `data/analysis/disposal_docs_review.md` — **19시나리오 · 판정 5종 전부** 렌더링본
  - 지적 5개 지점을 **전부 현행대로 수용**: 진술보장서 책임이전 구조 · `BLOCKED` 문서의 이중 문장 ·
    `확인되지 않음` 잔존 · 해시 미고정 계약근거 · 호칭 혼용
  - 출력 키 개명 `unreviewed_template_notice` → **`template_review_notice`** + 불리언
    **`template_reviewed`** 추가. 값이 "검수 완료"인데 키에 `unreviewed` 가 남으면 자기모순이다
  - 문구·상태는 **`data/doc_review.py` 한 곳**에서만 나온다 (종전엔 backend·mcp_server 두 곳에 리터럴 중복)
  - ⚠ **줄은 사라지지 않는다** — 법적 문서라 "언제 검수했는가"가 남아야 한다
- [x] 🔴 ~~**`N = 8` 법령 원문 대조**~~ — **2026-08-13 완료. `N = 8 → 10` 으로 정정** (**D89**)
  - 별표서식 API(`target=licbyl`) 로 **별표6**(업종별 자산의 기준내용연수) 실수집 + PDF 추출 대조
  - **종전 값은 두 가지가 틀렸다**: ⓐ *"범위 6~10의 중앙"* 이라는 유도 서술 — 표에는 `8년`과
    `(6년~10년)`이 **한 칸에** 있어 명시값이지 중앙값이 아니다 ⓑ **업종이 어긋났다** — 8년은
    **제4호**(의복·화학·기계수리 3종)이고 **제조업 중분류 15개는 제5호(10년)** 다
  - **업종을 `29`(기타 기계 및 장비 제조업)로 고정** → 별표6 **제5호** → `N = 10` (범위 8~12년)
  - 영향 실측: `r` 0.0830→0.0670 · 3지 판정 **27조합 중 1건 뒤집힘**
    (`INV-L4-02` 랩핑기 150만원 `HOLD → REPAIR_RECOMMENDED`)
  - 근거 전문·재현 방법: `data/analysis/useful_life_byl6.md`
  - ⚠ **곡선이 실측이 된 건 아니다** — 아래 두 가정은 그대로 남아 있다
- [ ] **`RESIDUAL_AT_LIFE_END = 0.50` 가정 동의 여부** — N년 시점 잔가율을 50%로 뒀다
  - 세법 잔존가액 `0.05` 를 **그대로 쓰지 않은 이유**는 `residual_curve.md §2-3` 에 있다(세무상 상각 한도이지 시장가가 아니다)
  - 이건 **법령 근거가 없는 순수 가정**이다. 동의하지 않으면 값과 함께 `source` 문구를 고칠 것

## Sprint 8 — A2A

- [x] ~~**A2A 연결 승인 표기 — `PARTNER_LINKS_MOCK` → `False`**~~ — ✅ **2026-09-16 완료**
  > 5행(`finallq/company` LINKED · `insuq/building` A·B·C LINKED · **D NOT_LINKED**)을
  > 확인하고 `False` 로 내렸다. 시드 출력이 *"⚠ 목업 전제다"* → *"✓ 사람 연결 승인 확인 완료"*
  > 로 바뀐다. **줄은 지우지 않는다** — 지우면 확인했다는 사실 자체가 사라진다(D90).
  > 📌 **`BLD-D` 를 미승인으로 두는 것도 확인된 선택이다.** 자산 3건이 전부 부보돼 있는데도
  > 미연결이라 *"부보와 연결 승인은 별개 축"* 을 한 건물에서 보여준다. D142 게이트가 들어가
  > **이제 실제로 막는다** — 대조군이 처음으로 제 역할을 한다.
  > ✅ **차단 사유 ㉡ 는 해소됐다 (2026-09-16, D142).** 게이트를 구현해서 이제
  > `partner_links` 가 **실제로 발신을 막는다** — `build_notify_asset_change_payload` 가
  > 건물 결 `link_state != 'LINKED'` 면 조립을 거부하고 라우터가 400 으로 돌려준다.
  > 뮤턴트로 실증했다(가드 무력화 시 회귀 2건 FAIL). 시드 주석의 "못 쏜다" 주장이
  > **이제 사실이다.**
  > 🟡 **남은 것은 사람의 사실 확인 하나뿐이다** — 시드 5행(`finallq/company` LINKED ·
  > `insuq/building` A·B·C LINKED · **D NOT_LINKED**)이 실제 승인 상태와 맞는가?
  > ⚠ **InsuQ 대장과 다른 것은 정상이다** — 그쪽은 4동 전부 `active` 라고 했다(2026-09-16 회신).
  > `partner_links` 는 **우리 쪽 승인 대장**이라 *"상대가 받아 줄까"* 가 아니라
  > *"우리 승인이 끝났는가"* 를 적는다. **BLD-D 를 미승인으로 둘지만 정하면 된다.**
  > 맞다고 판단하면 `data/seed.py` 의 `PARTNER_LINKS_MOCK = False` 로 내린다.

  아래는 종전 기록이다 (차단 사유 ㉠㉡ 진단). ~~**`False` 로 지금 내리면 안 된다**~~
  > **`False` 로 내리는 것은 «이 5행이 실제 승인된 연결이다» 라고 선언하는 것**인데,
  > 실측으로 두 가지가 걸렸다. 사용자 승인 문제가 아니라 **사실관계 문제**다.
  >
  > ㉠ **시드가 InsuQ 답변과 어긋난다.** 시드는 `BLD-D` 를 `NOT_LINKED` 대조군으로 두는데,
  > InsuQ 세션 회신(2026-09-16)은 **BLD-A~D 4동 전부 `status=active`** 라고 한다.
  >
  > ㉡ 🔴 **더 중요한 것 — 그 대조군이 주장하는 동작을 강제하는 코드가 없다.**
  > `data/seed.py` 주석은 `BLD-D` 를 두고 *"부보돼 있어도 A2A 연결 승인이 없으면 못 쏜다가
  > 한눈에 보인다"* 고 적는데, **`build_notify_asset_change_payload` 는 insuq building 의
  > `link_state` 를 아예 조회하지 않는다.** 프로덕션 코드에서 `partner_links` 를 읽는 곳은
  > `get_finallq_company_id()`(finallq **company** 행) **한 군데뿐**이다.
  > **실증됨** — 2026-09-11 에 `BLD-D` 로 S11(`notify-asset-change`)을 실제로 쏴서
  > **200 completed** 를 받았다. 대조군이 막았어야 할 호출이 그냥 나갔다.
  >
  > **→ 지금 `False` 로 내리면 코드가 지키지 않는 사실을 데이터가 「실제」라고 선언한다.**
  > 먼저 정할 것: ⓐ 링크 게이트를 실제로 구현할 것인가(조립 단계에서 `link_state != 'LINKED'`
  > 면 거부 — `insured`·`policy_id` 가드와 같은 자리), 아니면 ⓑ 게이트가 없음을 인정하고
  > 시드 주석에서 *"못 쏜다"* 주장을 걷어낼 것인가. **ⓐ 가 맞다고 본다** — 이 레포의 다른
  > 가드(D10 TEMP TRIGGER·D84 `EvidenceChanged`)가 전부 «주장을 코드가 강제»하는 형태다.
  > ⚠ ⓐ 로 가면 `BLD-D` 대조군이 **진짜 대조군이 되면서** InsuQ 의 «4동 전부 active» 와
  > 정면으로 갈린다 — 그때는 시드를 InsuQ 에 맞출지(4동 전부 LINKED) 대조군을 살릴지도 함께 정한다.

  아래는 종전 기록이다. **자격증명 실값은 확보됐다(2026-08-29 정정).** 이 항목은 오래
      *"미착수 · `.env` 4키 전부 비어 있다"* 로 적혀 있었으나 **낡았다**: **D120** 이 스킴을
      Basic(`MAINTQ_A2A_*_CLIENT_ID`/`_SECRET`)에서 **Bearer**(`INSUQ_SERVICE_TOKEN`·
      `FINALLQ_SERVICE_TOKEN` + `X-A2A-Partner-Id: maintq-agent`)로 교체했고,
      `.env` 의 그 두 키에는 **실값이 들어 있다**(FinAllQ→InsuQ 2차 홉이 같은 스킴으로 실 E2E 성공).
      남은 것은 승인이 아니라 **표기 정합**이다 — 시드 `partner_links` 5행이 여전히 **목업 전제**
      (`data/seed.py` 의 `PARTNER_LINKS_MOCK = True`)이므로, 이 5행이 실제 승인된 연결과 일치하는지
      확인한 뒤 **`PARTNER_LINKS_MOCK` 을 `False` 로** 내린다(시드 출력의 "사람 확인 대기" 고지가 사라진다).
  - ⛔ **값 자체는 저장소·세션 로그·문서 어디에도 적지 않는다** — `.env.example` 은 키 이름만 둔다
    (`LAW_API_OC` 와 같은 규칙). 회귀 `spikes/a2a_identity_contract.py ⑭` 가 `.env.example` 의
    4키에 **실값이 없음**을, ⑮ 가 `mcp_server/**` 에서 **안 보임**(D15·D93)을 단언한다
  - 지금 막히는 것은 **없다** — 자격증명을 쓰는 A2A 호출부 자체가 미착수다(QMesh 착수 후).
    이 항목은 "실값이 없다는 사실이 문서·시드에 정직하게 드러나 있는가"를 지키기 위한 것이다

## 데이터 확보 — 2026-08-14 실측으로 드러난 블로커

> 전문: [`data/analysis/part_number_sources.md`](data/analysis/part_number_sources.md) ·
> 요약: `data/data_list.md §6-4`

- [x] 🔑 **data.go.kr 조달청 서비스 활용신청** — **키가 있어도 안 된다는 게 실측됐다**
  - `.env` 의 `DATA_GO_KR_SERVICE_KEY`(96자, 인코딩키)는 **채워져 있는데**
    조달청 엔드포인트가 전부 `HTTP 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 를 낸다
  - ⚠ **대조군으로 확정했다** — 위조 키(`'A'*88`)를 넣어도 **바이트 단위로 동일한 응답**이 온다.
    즉 "키가 틀렸다"가 아니라 **이 서비스에 활용신청이 안 돼 있는 것**이다
    (data.go.kr 은 키 발급과 **서비스별 활용신청이 별개**다)
  - 신청 대상 3개만:

    | # | 데이터셋 | 쓸 곳 |
    |---|---|---|
    | 7 | [물품목록정보서비스 / 15129417](https://www.data.go.kr/data/15129417/openapi.do) | 조인 키 — 물품분류번호 ↔ `assets.category` |
    | 10 | [나라장터 계약정보서비스 / 15129427](https://www.data.go.kr/data/15129427/openapi.do) | 실거래가 |
    | — | [종합쇼핑몰 품목정보 `ShoppingMallPrdctInfoService`](https://www.data.go.kr/) | 품목별 **계약단가** |

  - 승인 후 확인법: `uv run --with python-dotenv python data/probe_g2b.py`
    — 위조 키 대조군이 스크립트에 내장돼 있어 **"승인됐다"와 "그냥 응답이 왔다"를 가른다**
  - ⛔ 이건 **확장 범위(D67)** 다. S1~S4 를 막지 않는다 — `assess_repair_value`·`residual_curve`
    의 **목업 시장가**를 실측으로 바꾸는 용도일 뿐이다

- [x] 🔍 **`inverterdrive.com` 부품 품번 원문 확인** (사람 브라우저 필요)
  - Cloudflare 봇 차단으로 **Claude 가 못 연다** (WebFetch 403 · 브라우저 자동화도 차단.
    우회하지 않았다)
  - [x] ✅ **`SV-iG5A I/OPCBASSY` 확인 완료 (2026-08-14)** — 페이지가 `Part number:` 로 명시.
        *"IG5A I/O Control Board - PCB Assembly **0.4~7.5KW-2/4**"* = **MaintQ 자산 용량대(2.2·4.0kW)를 덮는다.**
        ⚠ 판매점 주문번호 `Order code: 32155` 는 **품번이 아니다** — 같은 물건도 판매점마다 다르다
  - [x] ✅ **iG5A 냉각팬 부재 확정 (2026-08-14)** — LS 부품 목록(1페이지) **전수 확인 결과
        iG5A 는 위 제어보드 1종뿐.** 같은 목록에 팬이 4종 있다(S100 11~15 · S100 18.5~45 ·
        iS7 30~45 · **iS7 5.5kW**) → 팬 축·iG5A 축이 각각 살아 있는데 **교차만 0건**이다.
        "소용량은 원래 안 판다"도 아니다(iS7 5.5kW 존재). **품목 부재 확정**
  - [ ] (선택) 나머지 2차 출처 확인: `SV-iG5ACAB2`/`CAB3` · `LV0110/0150S100-FAN` ·
        `LV0185/0450S100-FAN` — **급하지 않다.** MaintQ 기종·용량과 어긋나 시드에 못 쓴다

- [ ] 📞 **LS ELECTRIC 고객센터/대리점에 iG5A 팬 품번 문의** ← **이제 이게 유일한 경로다**
  - 매뉴얼이 직접 그렇게 지시한다 — *"FAN교체는 구입처나 LS산전 고객센터에 문의하십시오"*
  - **4개 축이 전부 닫혔다** (공공데이터 · 제조사 문서 · 국내 유통 · 해외 판매점 목록 전수).
    마지막 축은 **사람이 눈으로 확인**했다 — 정황이 아니라 실측이다
  - 물어볼 것: `SV-iG5A` **2.2kW·4.0kW** 냉각팬의 **주문 품번**. 있으면 `parts` 에 넣는다
  - ⚠ **급하지 않다.** 이게 없어도 S1~S4 는 돈다 — `부품 특정` 지표 상한만 묶여 있다

## Sprint 13 — Elice 실호출 승인 (2026-08-19 신설)

- [x] ✅ **Elice DocVision 실호출 — 2026-08-19 사용자 승인 후 집행 완료. 실지출 1,530원**
  (34/34페이지 · 2단 구매: 파일럿 90원 → 나머지 1,440원 · 예산 40,000원의 3.8%)
  - 무엇을 사나: S100 `p.412~425`(14p) · iG5A 트러블슈팅 `p.20~31`(12p) · iG5A 표준본 `p.200~207`(8p)
  - 왜 사나: `actions` 결측 34건에 대해 저장소 안에 **서로 충돌하는 진단이 셋** 있는데
    (`_pending_review` "원래 없음" vs `extract_triage` "`CELL_SPLIT`" vs 백로그 "재추출 후보")
    아무도 대조한 적이 없다. **독립 2차 판독기**로 가른다
  - ⛔ **회수를 기대하고 사는 것이 아니다** — 부재가 사실로 확정되는 것도 유효한 산출이다.
    회수 건수를 지표로 삼으면 없는 조치문을 만들어내는 압력이 생긴다 (절대규칙 3)
  - ⚠ 판독 범위는 `extract_triage` 권고(1페이지 45원)보다 **33페이지 넓다** — Elice 의 표 HTML
    변환이 `CELL_SPLIT` 도 푼다는 **Claude 의 판단**이다. 근거는 설계 §2-3, 틀리면 1,485원이 헛돈이다
  - 설계: `docs/superpowers/specs/2026-08-19-actions-absence-verification-and-external-store-design.md`
  - ⛔ 지출은 **Stage 3 한 곳**에만 있다. Stage 1·2 는 네트워크·지출 0
  - ✅ `.env.example` 키 이름 등재는 **완료**(`ELICE_API_KEY`·`ELICE_DOCVISION_URL`, 값 없음)
- [x] 🔵 **D99 — `iG5A NTC` 사람 승인·정본 병합 완료 (2026-08-29).** 아래 위임 판정(반려)을
      **사용자가 뒤집었다.** `data/merge_approved_actions.py` 로 병합했고 비-actions 필드 70건
      해시 대조가 전건 일치했다(다른 필드 무손상). `actions` 결측 34 → **33건**,
      `actions_manual_id IS NOT NULL` 3 → **4건**(회귀 기준값도 함께 갱신: `seed.py` 검사 ㉚ ·
      `spikes/lookup_contract.py ⑭`).
  - ⚠ **아래 반려 근거 셋은 지금도 유효하다** — 병합으로 해소된 것이 아니라 사람이 감수하고 넘긴 것이다.
    기계 판정(`actions_absence_verification.json`)은 **고치지 않았다**(여전히 `STILL_AMBIGUOUS`) —
    사람이 기계를 덮었다는 사실이 기록에 남아야 하기 때문이다. 근거와 한계는 후보 파일
    `entries[].override_note` 에 보존된다
  - 🔎 뒤집기를 뒷받침한 실측: 창의 첫 조각 *"시 출력을 차단합니다."* 가 정본 `NTC` 의 causes
    *"NTC 오픈 시 출력을 차단합니다."* 와 이어지고, 앵커는 `error_name` *"NTC 오픈"* 완전일치
    (`weak_anchor=False`)다. 그래도 **공유 셀 여부는 여전히 미확인**이다
- [x] ❌ ~~**D99 재승인 — `iG5A NTC` 회수 보류(반려).**~~ Claude 위임 판정 (2026-08-19) — **위 항목으로 뒤집힘**
  판정 34건 중 `RECOVERABLE` 은 **1건뿐**이다. 정본 병합 전 사람 검수가 필요하다(MQ-919 경로).
  **사용자가 이 건에 한해 검수를 위임했다(2026-08-19).** 근거를 대조한 결과 **회수하면 안 된다**:
  1. 근거가 표 행이 아니라 **`text_window`**(240자 폴백) — 문장이 *"시 출력을 차단합니다"* 로 중간에서
     잘려 시작하고 표 머리행(`원인 조치사항`)이 본문에 섞여 있다. 리포트가 `LOOSE_LIVENESS` 로 경고하는 경로
  2. **귀속행 = 0**(미확인) · `rowspan_resolved=False`
  3. 🔴 **`_pending_review` 의 공유 항목 목록에 `'NTC 이상'` 이 명시적으로 들어 있다** —
     HWT·EEP·ERR·COM 이 `STILL_AMBIGUOUS` 로 남은 것과 **같은 공유 셀**이다.
     회수하면 **공유 조치문을 한 항목에 귀속**시키는 것이고 절대규칙 3 위반 방향이다
  - ⛔ **정본 미기입.** 이 스프린트는 정본을 쓰지 않았다(D99) — sha256 불변 확인됨
  - ⚠ **위임 판정이지 사람 최종 승인이 아니다.** `related_parts`(2026-08-05 위임 → 08-12 사람 승인)
    선례대로 두 단계를 모두 남긴다. 뒤집으려면 사람이 `data/analysis/actions_absence_verification.md`
    의 `iG5A NTC` 행 근거 원문을 직접 보고 판단할 것
  - 🔴 **파생 발견 — 판정 매트릭스에 갭이 있다**: `NOT_FOUND_ON_PAGE × ACTION_FOUND` 에는
    귀속 조건이 없고 `AMBIGUOUS × ACTION_FOUND` 에만 있다. 그래서 **같은 공유 셀인데**
    파서의 분류 차이만으로 `RECOVERABLE` 과 `STILL_AMBIGUOUS` 로 갈렸다. 다음 작업 후보
- [x] ✅ **`DISAGREE` 6건 확인 완료 — 조치 불필요.** Claude 위임 판정 (2026-08-19). **4건은 알려진 위양성**이다:
  `S100 EFAN`·`iG5A COL` 은 설명·원인문의 `교체` 가 조치 표지어에 걸린 것이고,
  `S100 LCW`·`LOR` 은 **`error_name` 이 둘 다 `Lost Command` 라 앵커가 충돌**했다.
  실제 판단이 필요했던 **`iG5A EEP`·`HWT` 2건**을 대조한 결과 **정본에 넣을 것이 없다**:
  - `EEP` — 근거가 *"사용자가 변경한 파라미터 내용을… 표시합니다"* 로 **설명문**이지 조치문이 아니다
  - `HWT` — 근거가 `하드웨어오류(Fatal)` **8자**, 라벨일 뿐이다
  둘 다 *"앵커는 봤는데 조치는 못 찾음"* 이 맞고 파서의 *"귀속 불가"* 와 어긋나지 않는다. **결측 유지.**

  🎯 **종합: 34건 중 회수 가능은 0건이다.** 기계 판정 `RECOVERABLE 1` 은 위 매트릭스 갭의 산물이고,
  위임 검수 결과는 **부재 확정 24 + 귀속 불가 4 + 나머지**로 정리된다.

## actions 검수

> Sprint 9 MQ-911 산출물. 검수 자료: `data/analysis/actions_review.md`(기계 생성, 표 3종 + 재승인 범위 절).
> 후보 파일: `data/extracted/error_codes_actions.candidate.json`(`_status`: **승인 완료 (2026-08-17)**, D99).
> ✅ **2026-08-17 사용자 최종 승인 완료** (G1·G2). 정본 병합은 이 절이 아니라 **MQ-919** 가 한다.

- [x] ① **조치문 코드별 확인(3건)** — `data/analysis/actions_review.md` 표 1의 iG5A `RERR`·`ETB`,
  S100 `FANW` 조치문 — **2026-08-17 사용자 승인**.
- [x] ② **안전 문구 확인** — 표 2 결과: 키워드(활선·방전·대기시간·감전·고전압) 스캔 대상 3건 중
  **0건 적중**. 매뉴얼 '10분 이상' 방전 대기 문구와 비교할 대상 자체가 없어 안전 문구 확인
  대상 없음 — **2026-08-17 사용자 승인**.
- [x] ③ **승인 시 절차** — `_status` 필드를 `"초안 — 사람 검수 대기 (D99). ⛔ 이 파일은 DB 에
  적재되지 않는다"` 에서 `"승인 완료 (2026-08-17)"` 로 변경 완료. 정본(`data/extracted/error_codes.json`)
  병합·`actions`/`actions_manual_id`/`actions_page` 3필드 반영은 이 절이 아니라 **MQ-919** 가 한다
  (이 파일은 병합 도구가 아니다 — D99)

## M2~M4 중

- [x] ~~**시스템 프롬프트의 안전 경고 문구 최종 검수**~~ — ✅ **2026-09-16 사용자 승인** (안전 관련은 사람이 승인) — safety-guardrail 스킬 규칙 5
  > ✅ **완료.** `backend/agent/prompts.py` 의 `SAFETY_BASELINE` 에 **`text_reviewed_at = "2026-09-16"`** 을
  > 새 키로 넣었다. ⚠ **`approved_at`(2026-07-18)은 그대로 둔다** — 그건 기준값("10분 이상")
  > 승인일이고 이번은 문안 전체 검수라 **다른 것을 승인한 기록**이다. 합치면 어느 날 무엇이
  > 승인됐는지가 사라진다.
  > 📌 **이 자리가 비어 있던 것이 실제로 대가를 치렀다** — 아래 정정 기록 참고. 날짜가 없으니
  > 잘못 선 체크를 반증할 근거도 없었다.
  > 🔴 **2026-09-16 — 체크를 되돌렸다. 이 항목은 완료된 적이 없다.**
  > `f808f39`(2026-08-18, Sprint 12 «S19→S29 번호 전수 정정» 커밋)이 **무관한 변경에 끼워**
  > `[ ]` → `[x]` 로 뒤집었다. 승인 기록이 함께 들어오지 않았고, 같은 커밋의 본문은 여전히
  > *"남은 건 paraphrase 된 문장 표현이 매뉴얼 의미를 넘지 않는가"* 라고 적혀 있다.
  > **코드가 반증한다** — `backend/agent/prompts.py:69` 주석이 *"기준값('10분 이상') 승인일.
  > **문안 전체 검수는 TODO_직접할일.md M2 항목에서 진행 중**"* 이고 `approved_at` 은
  > **`2026-07-18`**(기준값 승인일)에 머물러 있다. `docs/README.md` 와 세션 로그도 이 건을
  > **남은 사람 승인 1건**으로 센다. 셋 중 둘이 미승인을 가리키고 근거는 코드에 있다.
  > ⚠ **승인 표기가 한 번 잘못 서면 되돌릴 근거를 찾기 어렵다** — 이 항목은 안전 문구라
  > 더 그렇다. 실제로 승인했다면 **`approved_at` 갱신과 함께** 체크할 것.
  - 파일: `backend/agent/prompts.py` · 검수 대상 상수: **`SAFETY_BASELINE`** (`text` / `pages` / `approved_at`)
    - 같이 볼 것: `SAFETY_SOURCES`(문장별 매뉴얼 원문 근거), `QUALIFIED_WORKER_NOTE`(전문 기술자 원칙, 근거 페이지가 달라 분리), `DANGER_KEYWORDS`(안전 블록 발행 트리거)
  - 확인 포인트 ①: `SAFETY_BASELINE["text"]` 의 방전 대기 기준값이 **"10분 이상"** 인가 (기준값 자체는 2026-07-18 승인 완료 — 축소 표기 금지). 남은 건 **paraphrase 된 문장 표현이 매뉴얼 의미를 넘지 않는가**
  - 확인 포인트 ②: `SAFETY_BASELINE["pages"]` = **iG5A 4 / S100 2 (PDF 물리 페이지, D26)**. 인쇄 페이지로 바꾸지 말 것 — 환산은 `backend/manifest.to_print_page()` 1곳 담당 (D32·D49)
  - 확인 포인트 ③: `SAFETY_SOURCES` 의 원문 인용이 실제 매뉴얼 문장과 일치하는가 (iG5A 표준본 p.4 · S100 p.2 · 보조: iG5A 트러블슈팅 p.6)
  - 검수 전에도 **런타임은 막지 않는다** (게이트하면 안전 블록이 아예 안 나가 더 위험). 회귀: `uv run python spikes/prompt_rules.py`
  - 문안을 고치면 `docs/03_WIREFRAME.html`·`docs/02_SCENARIOS.md`·`docs/06_REPO_API.md §평가` 의 안전 문구 표기와 함께 맞출 것
- [x] ~~**`DANGER_KEYWORDS` 확장 4종 + 공백 정규화 검수** (방열핀·히트싱크·냉각팬·쿨링팬)~~ —
  **2026-07-28 승인 완료.** 네 단어 모두 함체 개방을 전제하는 작업이라 안전 경고 트리거로
  타당하다고 확인. 과잉 경고(진단 서술의 단순 언급까지 걸리는 것)는 안전 쪽으로 완화하는
  방향이라 감수 — 누락보다 낫다. 파일: `backend/agent/prompts.py` `DANGER_KEYWORDS` 끝 4종 ·
  회귀: `spikes/prompt_rules.py` ⑮
- [x] ~~평가셋 20문항의 기대 정답(부품·분기) 확정~~ — **2026-07-29 승인 완료.** `eval/testset_draft.json` 그대로 승인, `eval/testset.json` 반영(사람이 직접 cp 실행). D12 경고: 부품 특정 정확률은 `related_parts` 검수 완료 전 실적 인용 금지 유지
- [x] ~~데모 영상 촬영 (S1→S2→S3→S4 순서, 화면 A/B 전환 포함)~~ — **완료(2026-08-29 발표로 종료).**
  시나리오 1·2 촬영본 + 내부 기능 GIF **7종**(`0dd8a24`) · 발표 노트 · `maintq-diagrams.html` 최신화(`3a762b5`).
  큐시트 `docs/demo_script.md` · 촬영 노트 `docs/demo-captures/README.md`
- [x] ~~README에 데모 GIF + 평가 결과표 삽입~~ — **완료.** `README.md:38~41` 에 GIF 7종(S2·S3·S4 ·
  처분 사전점검 · 증빙 번들 · 지출 분류 · 기한/위험등급), `§평가`(`README.md:102~172`)에 결과표.
  ⚠ **미달 지표를 지우지 않고 원인과 함께 싣는 형태다** — 부품 특정 정확률 **40.0%**(목표 ≥90%)가
  그대로 있고 원인(P32, 품번 미공개)이 붙어 있다

## Q 시리즈 전사 정합 — 2026-08-14 발견

- [x] 🔴 **시나리오 번호 `S19` 충돌을 어느 쪽으로 정정할지 결정** (백로그 **P33**)
  - **무슨 일인가**: MaintQ 가 `S19` 를 *"수리 증빙 서명"* 으로 쓰고 있는데
    (`docs/02_SCENARIOS.md:82` · `docs/12_MAINT_VALUE.md §7` · `sprint-9.md` 전체),
    전사 지도 `../A2A_Q/Q시리즈_시나리오맵_S1-S18.html` 는 **`S19` 를 FinAllQ 의
    "기업 고객 온보딩"(이미 구현 완료)** 으로 잡고 있다.
  - **왜 Claude 가 못 정하나**: 번호 체계를 **세 프로젝트가 공유**한다. MaintQ 혼자 바꾸면
    다른 쪽 문서가 어긋나고, 지도를 바꾸면 **구현이 끝난 FinAllQ** 쪽이 흔들린다.
  - **고르면 되는 것**: ⓐ MaintQ 가 **`S29` 로 이동**(권장 — MaintQ 쪽은 문서만 고치면 된다.
    **DB·도구 계약·enum 에 이 번호는 없다**) / ⓑ 전사 지도를 고쳐 S19 를 MaintQ 에 주고
    FinAllQ 를 밀어낸다(비용 큼).
  - ⚠ **정정 (2026-08-14 재확인)**: 처음엔 *"S24 로 이동"* 이라고 적었는데 **틀렸다.**
    `../A2A_Q/11_A2A_SCENARIOS.md:98` 이 *"FinAllQ 가 S19~S23 을 선점했으므로 InsuQ 는
    **S24~S28** 을 쓴다"* 로 이미 배정해 뒀다. **비어 있는 첫 번호는 `S29` 다.**
    (지도 HTML 제목은 아직 `S1~S23` 이라 S24~S28 이 안 보인다 — 지도가 문서보다 늦다.)
  - ⛔ **결정 전까지 새 문서에 `S19` 를 더 늘리지 않는 편이 좋다.**
  - ✅ 실행 완료 — 2026-08-18 Sprint 12(MQ-1201)에서 MaintQ 문서 전수 S29 정정 완료.

## 결정 대기 (Claude와 의논)

- [x] 프론트엔드 스택 (React vs 단순 HTML) — M3 전까지 : React
- [x] 임베딩 모델/벡터스토어 선택 — M1 EDA에서 매뉴얼 분량 보고
- [x] 표 추출 전략 (파서 vs 비전 모델) — EDA 결과로 결정

## Sprint 14 — IE5 후보 검수 (2026-08-20 신설, 2026-08-20 검수 완료)

산출물: `data/extracted/ie5_code_candidates.json` (`_status` = 초안, DB 미적재)
상세: `docs/sprints/sprint-14.md §6·§8`

> ✅ **검수 완료 — Claude 판정 (사용자 위임, 2026-08-20), 사용자 승인.** PDF 원문(p67·p110·
> p113·p117·p125·p126)을 직접 대조해 판정했다. 판정에 맞춰 `data/extract_ie5_codes.py` 에
> 재현 가능한 코드 변경(4건)을 반영했다 — 손편집이 아니라 재실행하면 같은 결과가 나온다.

- [x] ✅ **조인 5건 정확성 — 전건 원문 일치 확인.** `OCt 과전류`(p125, 원인·대책 5쌍) ·
      `IOL 인버터 과부하`(p125, 병합 셀) · `OHt 냉각핀 과열`(p125) · `Ovt 과전압`(p126) ·
      `Lvt 저전압`(p126) 모두 PDF 원문과 문장 단위로 일치한다.
- [x] ✅ **`IOLt` 이름 충돌 — `IOL` 채택 (사용자 결정, 2026-08-20).** 원문 대조 결과 매뉴얼
      자신이 절마다 다르게 표기한다 — 11.5절(p110)·12.6절(p113) 릴레이 기능 목록은 `IOL`
      **(2회 등장)**, 7절 기능 일람표(p67)는 `IOLt` **(1회)**. 다수결·사용자 지시 둘 다 `IOL`
      을 가리킨다. `IOLt` 를 지우지 않고 **`name_collision_with` 필드로 양방향 상호참조**하도록
      코드에 반영했다(`data/extract_ie5_codes.py::detect_name_collisions`,
      `spikes/ie5_extract_contract.py` C⑫ 로 회귀 고정) — 다음 사람이 `IOL` 만 보고
      확정으로 오독하지 않는다.
- [x] ✅ **대소문자 접기 페이지 — p117 검증 완료, 위양성 아님.** PDF p117(12.3 "사용자 선택
      고장 검출") 표에 `[COL]` 이 **대문자 그대로** 리터럴로 인쇄돼 있다(지락/결상 검출 조합
      선택 표의 열 라벨). reviewer 가 우려했던 "위양성 쪽으로 기운다"는 실측과 어긋난다 —
      실제로는 **exact 일치**(대소문자 그대로)다. `code_pages_exact`/`code_pages_case_folded`
      필드로 이 구분을 산출물에 구조적으로 드러내도록 코드에 반영했다
      (`spikes/ie5_extract_contract.py` C⑪).
- [x] ✅ **`토크부스트 양이 너무 크다` 귀속 — 현행 표현이 원문과 일치, 변경 불필요.** PDF p125
      원문 그대로 `인버터 과부하`·`과부하 트립` 두 보호기능이 원인·대책 셀 하나를 공유한다
      (매뉴얼 자신의 표 레이아웃). 현재 산출물의 `merged_with` 표기가 이를 정확히 반영하고
      있어 **판단 변경 없음**.
- [x] ✅ **`_unmatched` 4버킷 판단 — 승격 대상 없음.** `codes 24`·`codes_excluded_by_shape 43`
      은 전건 키패드/UI 라벨(RUN·SET·OFF·ON·drv 등) 또는 파라미터 코드(P15~P87 등)이고 에러
      트립 코드가 아니다. `codes_without_name 2`(`CoL`·`nOn`)은 §0-2 확정 12종에 이미 포함돼
      있어 별도 승격 판단 대상이 아니다(이름 없이 존재만 확인된 상태 유지, 절대규칙 6).
- [x] ✅ **P11(기종 확장) 착수 여부 — 2026-08-21 착수 결정, Sprint 15 로 완료.** 사용자가
      백로그 메뉴에서 명시 선택 → `/sprint 15` → 5스테이지 완주. 상세는 아래 "Sprint 15" 절.

## Sprint 15 — P11 기종 확장 (2026-08-21 완료)

산출물: `docs/10_DECISIONS.md` D109 · `error_codes` 65→70건(IE5 5건 병합) · `model` enum
3종(`iG5A`·`S100`·`IE5`). 상세: `docs/sprints/sprint-15.md`.

- [ ] **IE5 안전지침 페이지 사람 검증** — 완료되면 `backend/agent/prompts.py`의
      `SAFETY_BASELINE["pages"]`에 IE5 를 추가할 근거가 된다. 지금은 근거 미확보라 D109 가
      의도적으로 제외했다(절대규칙 3) — IE5 관련 안전 문구 요청은 안전 블록 대신
      "근거 문서를 확인하지 못해 안내할 수 없습니다"로 방어적 거부된다. 급하지 않음.
- [x] ✅ **IE5 매뉴얼 RAG 청킹 완료 — 2026-08-21, D110.** "별도 스프린트 규모"라는 추정이
      같은 날 재조사로 틀렸다고 드러나 바로 해소했다. 막힌 지점은
      `data/chunk_manual.py::verify()` 의 `assert r["model"] in ("iG5A","S100")` 하드코딩
      하나뿐이었다 — 이를 `MODELS = ("iG5A","S100","IE5")` 로 넓히자 코드 변경 없이 IE5 PDF 가
      194청크로 정상 처리됐다(총 4매뉴얼 1,229청크: iG5A 표준 342 + iG5A 트러블슈팅 44 +
      S100 649 + IE5 194). `rag_search_manual(model="IE5", ...)` 실 인덱스 질의 2건
      ("냉각핀 과열 원인"·"과전류 원인") 결과가 매뉴얼 p.122·p.125 원인·대책 표와 실제로
      일치함을 눈으로 확인. 회귀 `spikes/rag_contract.py ⑬` 신설(양성 축 포함, 13건 전건 PASS).
- [ ] **IE5 `print_page_offset` 재확인 (선택)** — 2026-08-21 실측으로 `offset=0`(iG5A 표준본과
      동일한 장-상대 쪽번호 규약, 선형 환산 축 없음)으로 확정했다. 여유가 되면 사람이 매뉴얼을
      직접 훑어 더 정확한 대응이 있는지 재확인해도 좋으나 급하지 않다.

## 결재 문서 문안 검수 — 01·02·03 (2026-09-04 신설)

**docx 다운로드가 붙었다** (D124). 이제 이 세 문서가 **실제 파일로 사람 손에 나간다** —
그전에는 화면 미리보기뿐이었다.

`data/doc_review.py` 기준 현재 상태:

| 문서 | 상수 | 상태 |
|---|---|---|
| 01 설비이상진단보고서 | `DIAGNOSIS_TEMPLATE_REVIEWED` | ❌ `False` |
| 02 정비부품발주요청서 | `PO_REQUEST_TEMPLATE_REVIEWED` | ❌ `False` |
| 03 자금집행요청서 | `FUND_EXECUTION_TEMPLATE_REVIEWED` | ❌ `False` |
| 05 처분승인서 · 06 진술및보장서 | `TEMPLATE_REVIEWED` | ✅ `True` (2026-08-13) |

**지금 당장 막히는 건 없다** — 세 문서 모두 마지막 줄에
`※ 문서 문안은 미검수 초안이다 (TODO_직접할일.md)` 가 **서류 안에** 찍힌다(2026-09-04
템플릿 보강 + 회귀 `docx_contract C②`). 즉 검수 전이라는 사실이 숨겨지지 않는다.

- [x] ~~**01 설비이상진단보고서 문안 검수**~~ — ✅ **2026-09-16 사용자 승인**
- [x] ~~**02 정비부품발주요청서 문안 검수**~~ — ✅ **2026-09-16 사용자 승인**
- [x] ~~**03 자금집행요청서 문안 검수**~~ — ✅ **2026-09-16 사용자 승인**

> ✅ **3종 전부 완료 (2026-09-16).** `data/doc_review.py` 의 `*_TEMPLATE_REVIEWED = True` ·
> `*_TEMPLATE_REVIEWED_AT = "2026-09-16"` 반영. 서류 마지막 줄이
> `※ 문서 문안은 미검수 초안이다` → `※ 문안 사람 검수 완료 (2026-09-16)` 로 바뀐다.
> **줄 자체는 지우지 않았다** — 법적 서류라 "언제 검수했는가"가 남아야 한다.
> 골든 스냅샷 3종을 재생성했는데 **차이가 그 한 줄뿐임을 diff 로 먼저 확인**했다(본문 무변경).
> `docx_contract` 63건 · `api_contract` 52건 · 문서 pytest 12건 전건 통과.

> 🔵 **2026-09-16 — 체크박스를 달았다.** 이 절은 신설(2026-09-04) 때부터 **산문으로만** 적혀
> 있어서 `grep '- \[ \]'` 로 남은 일을 세는 스캔에 **3건이 통째로 안 잡혔다.** 실제로
> `docs/README.md` 가 *"남은 사람 승인 1건"* 으로 적고 있었던 원인이 이것이다.
> 상태값 자체는 위 표와 코드(`data/doc_review.py:32~47`)가 일치하는 것을 확인했다.

검수하실 때: 문안을 읽고 이상 없으면 `data/doc_review.py` 의 해당 `*_REVIEWED = True` ·
`*_REVIEWED_AT = "YYYY-MM-DD"` 로 바꾸면 된다. **줄 자체는 지우지 않는다** — 그 자리는
"문안 사람 검수 완료 (날짜)" 로 바뀐다(`_notice()` docstring: *"침묵은 검수 여부를
알려주지 않는다"*).

⚠ Claude 가 대신 판단하지 않는다 — 법적 효력이 있는 서류의 문안이다.

## Sprint 19 — HV600 온보딩 사람 대기 (2026-09-24 신설, MQ-1902)

상세: `docs/sprints/sprint-19.md §5`(수동 체크리스트 원본) · 대상 결정 D154~D157(✅ 2026-09-24 확정,
`docs/10_DECISIONS.md`). **아래 표는 §5 를 그대로 옮긴 것**이다 — 이 절이 최신본이면 그쪽을
갱신하지 않고 이 표만 고친다(중복 관리 금지, `_notice()` 관행과 같은 이유).

- [x] **H0 (Stage 1 끝) — D154~D157 문안 확인·승인.** ✅ 2026-09-24 사용자 확정(추천안 그대로) 이 스프린트 계획이 제안한 결정 4건
      (`docs/10_DECISIONS.md` D154~D157, 확정 후 ✅ 표시)을 사람이 읽고 승인해야 **Stage 2 전체**가
      착수된다 — 온보딩 스테이징 테이블·역할·도구 프로필(D154)·에러코드 형식 확장(D155)·승격
      병합 규칙(D156)·안전 문구 런타임 원천(D157) 중 하나라도 다시 뒤집히면 Stage 2~4 가 그 위에서
      돌기 때문이다.
- [x] **H1 (Stage 1 중)** ✅ 불필요했음(NAT L0 에서 sudo 없이 완료) · — NAT 스파이크 중 `sudo`·게이트웨이 복구.** MQ-1901 진행 중 필요해지면
      수행(`docs/hackathon/day2.md §5` 절차). 막는 것: MQ-1901 L0(샌드박스 안 NAT) 달성.
- [x] ✅ 2026-09-25 데모 8코드 검수 완료(CE row #142 반려 — 추출 섞임) · **H2 (Stage 3 끝) — HV600 정규화 검수.** 최소 데모 코드(`GF`·`OC`·`OV`·`UV1`·`OH`·`CPF06`·
      `EF1`·`CE`)의 전 구역 행을 원문과 대조, `confidence=low` 행을 우선 확인. 막는 것: 승격(H3).
- [x] ✅ 2026-09-25 8코드 승격(promo #1~#8: CE·GF·OC·OV·UV1·OH·CPF06·EF1) · **H3 (H2 뒤) — 승격 클릭.** 화면(MQ-1911, 컷 후보) 또는 `curl`(`POST /api/onboarding/promote`,
      manager 권한)로 승격, `flags` 확인 체크를 반드시 포함한다. 막는 것: 데모 ④(승격 후 정의 응답).
- [x] **H4 (Stage 3 끝) — HV600 안전 문구 승인.** ✅ 2026-09-25 사용자 승인(mgr-01) — **SC-14 · p.29 · discharge_wait · 「최소 5분 이상」**(원문 명시값 5분. 한국어 문안은 Claude 초안을 사용자가 원문과 대조해 확정·입력). **HV600 은 매뉴얼 값 5분을 쓴다** — safety-guardrail 규칙 3 의 「10분 이상」은 iG5A·S100 확정값으로 읽는다(스킬 문구 개정 여부는 여전히 사람 결정, Claude 는 스킬을 고치지 않음). 원문 인용·페이지를 직접 대조하고 한국어 문안을
      **직접 작성**한다(자동 채우기 없음, D147). ⚠ 대기 시간이 원문에 숫자로 없고 "경고 라벨 표시
      시간"만 있으면 **숫자를 넣지 않는다** — API 가 `number_not_in_source` 로 거부한다. ⚠
      safety-guardrail 규칙 3 의 "10분 이상"은 iG5A·S100 확정값이다 — HV600 원문 값이 다르면
      **스킬 문구의 적용 범위를 기종별로 개정할지는 사람이 결정**한다(Claude 가 스킬을 고치지
      않는다). 막는 것: 데모 ⑤(승인 후 경로).
- [x] ✅ 2026-09-25 ⓐ 1회로 충분(H4 를 먼저 해서 ⓐ 설치분에 승인 문구가 이미 들어감, `--check` stale 0) · **H5 (두 번 — ⓐ H3 전: 데모 ① 녹화용 · ⓑ H3·H4 뒤: ④⑤ 녹화용, 2026-09-25 결정 ㉠) — `deploy/nemoclaw/workspace/build.py` 재생성본을 샌드박스 `maintq-agent`
      에 재설치.** 막는 것: OpenClaw 진단 흐름에서 HV600 안전 문구가 실제로 나오는 것.
      ✅ 2026-09-25 사용자 승인 — 아래 적용 범위 문장(build.py AGENTS.md · maintq-diagnose SKILL.md).
      ✅ 2026-09-25 사용자 승인(추가) — **웹 콘솔 시스템 프롬프트**(`backend/agent/prompts.py` 규칙 10·안전 절)의 「10분 이상」도 iG5A·S100 한정으로 좁히고,
      온보딩 기종은 시스템 블록의 승인 문구 수치를 따르며 본문에 다른 대기 시간을 쓰지 않는다(Stage 5 브라우저 검증에서 HV600 답 본문이 10분을 써 5분 블록과 충돌) 워크스페이스 재생성·업로드·스킬 설치도 사용자가 실행(H5ⓐ)
      ✅ 2026-09-25 사용자 승인(추가) — 웹 콘솔 프롬프트: 본문에서 **안전 경고(블록)의 유무를 말하지 않는다**
      (「안전 경고는 근거가 없어 드릴 수 없다」 를 쓰는데 바로 위에 승인 SAFETY 블록이 붙는 모순 — 블록 부착 판단은 시스템 몫)
      ✅ 2026-09-25 사용자 결정 (가) — HV600 프롬프트에는 **자격 작업자 문구(`QUALIFIED_WORKER_NOTE`)를 싣지 않는다**:
      그 근거가 iG5A p.7·S100 p.3 이라 HV600 매뉴얼 근거가 아니다(규칙 1). HV600 매뉴얼은 "approved personnel" 표현을 쓰며,
      필요하면 이후 HV600 후보로 따로 추출·승인한다(안전 후보 추출기 `qualified_worker` 는 현재 0건)
      ⚠ **ⓐ 전 선행 확인(safety-guardrail 규칙 5)**: `build.py` 가 만드는 AGENTS.md 의 「10분 이상」 확정 문구 **적용 기종을
      iG5A·S100 으로 좁힌 문장**과 `skills/maintq-diagnose/SKILL.md` 의 HV600 안전 적용 범위 문장(「시작 전」·「하지 않는 것」)을
      사람이 읽고 승인한다 — 안전 문구 본문은 바뀌지 않았고 적용 범위만 바뀌었다(Stage 3·4 리뷰 지적)
- [x] ✅ 2026-09-27 사용자 수용 판정(evals 합성 주입 문장은 거부가 정답인 공격 예시) · **H6 (Stage 4) — SkillSpector 결과(신규·수정 스킬) 수용 판정.** 막는 것: 제출물.
- [x] ✅ 2026-09-25 녹화 완료 — 장면 설명 `docs/memo/2026-09-25-hv600-onboarding-demo.md` · **H7 (Stage 4) — 데모 녹화** (과부하 O1 대비 — 라이브 시연보다 녹화 권장). 막는 것: 제출.
- [ ] **H8 (필요 시) — 웹 콘솔 샌드박스(`maintq`)에서 HV600 을 보이려면** 호스트 DB 덤프 →
      `Dockerfile.sandbox` 재빌드 → 샌드박스 재생성(`docs/hackathon/day1.md §6`). 막는 것: 웹 콘솔
      데모. ⚠ `--no-privileges` 덤프라 온보딩 역할·GRANT 가 옮겨지지 않는다 — 샌드박스 안에서
      온보딩을 다시 돌리지 않으므로 무관하다.
- [ ] **H9 (상시) — 데모 전 `data/seed.py` 재실행 금지.** 재실행은 `DROP SCHEMA public CASCADE`
      라 스테이징·승격분이 전부 사라진다. 실수로 재실행했다면 적재기(`mcp_server.onboarding_load`)·
      정규화(`onboarding/nat/run_normalize.py`)·승격(H3)·안전 승인(H4)을 처음부터 다시 한다.
- [ ] **H10 (잘못 승격 시) — 승격 취소 API 가 없다.** `error_codes`·`manual_chunks`(대상 `chunk_id`
      는 `onboarding_promotions.chunk_ids` 에서 확인)·`onboarding_promotions` 행을 삭제하고
      `onboarding_code_rows`/`onboarding_safety_candidates` 의 `state` 를 사람이 SQL 로 되돌린다.

### 제출 전 체크리스트 (2026-09-25 신설 — 마감 2026-09-28 23:59)

심사용 문서: `docs/hackathon/SUBMISSION.md`. H6 은 위 항목 그대로다(여기서 중복 관리하지 않는다 — 제출을 막는 항목이라 순서에만 넣었다).

- [x] ✅ 2026-09-27 수용 — `SUBMISSION.md` §3.8 반영 · **S1 — H6 SkillSpector 판정** (위 H6). `maintq-manual-onboarding` HIGH 1(evals 합성 주입 문장) 수용 여부.
      판정 결과를 `SUBMISSION.md` §3.8 「판정 대기, H6」 자리에 반영한다.
- [ ] **S2 — 데모 영상 링크 기입.** `SUBMISSION.md` §4 「(링크: 사람이 기입)」 과
      `docs/memo/2026-09-25-hv600-onboarding-demo.md` §1 「영상 파일 위치」. 링크를 넣기 전에 영상에
      대시보드 URL·토큰(`nemoclaw … dashboard-url` 출력)이 비치지 않는지, 중국어 「参照」 가 섞였는지 확인.
- [ ] 🟡 2026-09-27 `maintq-manual-onboarding/skill-card.md` 초안 작성(Claude) — 사람 검토 남음: Use Case 문구·`Requires API Key: [No]`·버전 SHA · **S3 — 스킬 카드 사람 검토** (`skills/maintq-diagnose/skill-card.md`). `day2.md` §8 은 「소유자 VERIFY 표시 1건으로
      `validate_submission.py` FAIL」 이라 적었으나 **2026-09-25 재실행은 OK(마커 0)** 다 — 표시는 이미 지워졌다.
      남은 일은 내용 확인: 소유자·라이선스·카드 안 GitHub 링크(`ttogle918/MaintQ-NemoClaw`)가 공개 후 실제로 열리는지,
      「Requires API Key: [Not Specified]」 가 맞는지. `maintq-manual-onboarding` 에는 스킬 카드가 없다(만들지 여부 결정).
- [x] ✅ 2026-09-27 재생성·업로드·`maintq-diagnose` 재설치, 샌드박스 안 4파일 sha256 이 로컬과 일치. 재부팅으로 NemoClaw 게이트웨이(8080)가 내려가 있어 `gateway.env` 그대로 `~/.local/bin/openshell-gateway` 를 nohup 기동(로그 `~/.local/state/nemoclaw/openshell-docker-gateway/gateway-manual.log`) → `nemoclaw … start` 는 Stopped 에 묶여 `openshell sandbox start maintq-agent` 로 Ready. MCP-HTTP #1(core, 127.0.0.1:8765, `MAINTQ_MCP_ALLOWED_HOSTS=host.openshell.internal,host.openshell.internal:*`)도 nohup 재기동(로그 `~/.local/state/maintq-mcp-http-8765.log`) — 샌드박스 안 node 로 `initialize` 200 확인. ⚠ 둘 다 재부팅하면 다시 내려간다 · **S4 — OpenClaw 워크스페이스·스킬 재설치.** 커밋 `4614b79`(에러코드 매번 lookup 재호출)·`1cf93e8` 이후
      `build.py --check` 가 의도된 stale 을 낸다 → `build.py` 재생성 → `nemoclaw maintq-agent upload …` →
      `skills/maintq-diagnose` 재설치 → `--check` stale 0 확인. 녹화본은 재설치 전 판이다(재녹화 여부는 사람 판단).
- [ ] 🟡 2026-09-27 공개 전 점검 완료(Claude): LICENSE Apache-2.0 · 추적 `.env` 는 example 2개뿐 · 매뉴얼 원본 미추적 · 키 모양 문자열은 NVIDIA 카탈로그 스킬 evals 의 가짜 키 2건뿐 · `.env` 실값 21종 히스토리 유출 0(모델명 2건 제외) · 커밋 이메일 전부 noreply · README clone URL 정정. 남은 것: `LAW_API_OC` 가 GitHub 아이디와 같음(알려진 오탐) · **공개 클릭은 사람** · **S5 — 레포 공개·라이선스.** `ttogle918/MaintQ-NemoClaw` 는 비공개 — 제출 직전 공개(`day2-prep.md` §8 #1).
      공개 전: `LICENSE`(Apache-2.0) 확인 · 매뉴얼 실데이터가 추적 파일에 없는지(D144) · `.env`·키 모양 문자열 0건 재확인
      (`day2-prep.md` §9 방식) · 복구 번들(`~/maintq-backup-*.bundle`)은 올리지 않는다 · README 「빠른 시작」 의 clone URL
      (`<YOUR_ID>/MaintQ`) 이 제출 레포와 다르다는 점 확인.
- [ ] 🟡 2026-09-27 수치 전수 실측 일치(spikes 41/1,387 · pytest 406 · seed 44 정적 · 라우트 27 · D158 · 온보딩 데모 수치). §1.1 기능 지도·§3.11~3.12·§6 A2A 행 추가 — 사람 최종 읽기 남음 · **S6 — `SUBMISSION.md` 최종 읽기.** 사실·수치(spikes 1,387 · pytest 406 · seed 44 · 라우트 27 · D1~D158)가
      제출 시점 실측과 맞는지, 「확인 안 됨」 으로 둔 항목(build.nvidia.com HTTP Skill API)이 여전히 그런지.
