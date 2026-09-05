# 14. 결재 흐름의 동시성 — 이중 승인 사고 분석 (D126)

> **한 줄 요약.** `po_drafts`·`decisions`·`repair_records` 세 결재 흐름이 상태 확인과
> UPDATE 사이를 잠그지 않아, **두 결재자가 동시에 누르면 둘 다 200 을 받고 한쪽 결재가
> 조용히 사라졌다.** 2026-09-04 격리 스키마에서 재현·수정·검증 완료.

작성: 2026-09-04 · 상태: **해소됨** · 관련 결정: **D126**(신설) · D10 · D15 · D111

---

## 1. 이 코드가 하는 일

세 테이블은 사람의 결재를 기록하는 상태 기계다. 상태 전이의 **주체(역할)** 는 라우터가,
**순서(현재 상태)** 는 서비스 계층이 강제한다 — 이 문서가 다루는 것은 후자다.

| 흐름 | 테이블 | 전이 | 서비스 |
|---|---|---|---|
| 발주 | `po_drafts` | `draft→pending→approved→finance_approved` (+`rejected`·`finance_rejected`) | `backend/services/po.py` |
| 처분 | `decisions` | `draft→pending→signed` (+`rejected`) | `backend/services/decisions.py` |
| 수리증빙 | `repair_records` | `draft→pending→signed` (+`rejected`) | `backend/services/repairs.py` |

세 서비스의 전이 함수는 **모양이 똑같다**:

```python
with connect(db_path) as con:
    r = con.execute("SELECT state FROM po_drafts WHERE po_id = ?", (po_id,)).fetchone()  # ①
    if r is None:
        raise KeyError(po_id)                                    # → 404
    if r["state"] != ALLOWED_FROM[target]:
        raise TransitionError(po_id, r["state"], target)         # → 409  ②
    con.execute("UPDATE po_drafts SET state = ?, ... WHERE po_id = ?", ...)  # ③
```

①에서 읽고 ②에서 판정하고 ③에서 쓴다. 의도는 *"pending 인 발주만 approved 로 갈 수 있다"* 이고,
단일 요청에서는 정확히 그렇게 동작한다.

---

## 2. 문제의 내용

**①과 ③ 사이가 원자적이지 않다.** 두 요청이 겹치면 둘 다 ②를 통과한다.

격리 스키마에서 `pending` 상태 발주 하나를 두고, 팀장 A 의 **승인**과 팀장 B 의 **반려**를
`threading.Barrier` 로 같은 순간에 출발시킨 실측 결과:

```
준비: PO-RACE state=pending

  팀장B-반려  -> 성공(200)
  팀장A-승인  -> 성공(200)

최종 DB 상태: state='approved' decided_by='mgr-01' note='팀장A-승인 note'

[재현됨] — 두 전이가 모두 200 을 받았고 한쪽이 조용히 덮였다.
```

두 번 돌리면 **승자가 바뀐다**(1차 `rejected`, 2차 `approved`) — 비결정적 경쟁이라는 증거다.

관측되는 증상은 셋이다.

1. **결재가 사라진다.** 팀장 B 는 화면에서 "반려됨"을 보고 자리를 뜨는데 DB 는 `approved` 다.
   발주는 그대로 재무부로 넘어간다.
2. **감사 추적이 거짓이 된다.** `decided_by`·`decided_at`·`decision_note` 는 이긴 쪽 값만
   남는다. 진 쪽의 결재는 로그에도 흔적이 없다 — 나중에 "누가 반려했었나"를 물으면 답이 없다.
3. **아무도 에러를 못 본다.** 양쪽 다 HTTP 200 이라 클라이언트·서버 로그 어디에도 신호가 없다.

`decisions.sign()` 에서 더 나쁘다. 이 함수는 ③ 근거 재산출·해시 대조 → ④ BLOCKING 판정 →
⑤ override 사유 게이트를 **순서대로** 통과해야 서명되는데(D84), 그 여섯 단계 전체가 잠기지
않은 창 안에 있다. 두 결재자가 동시에 서명하면 둘 다 게이트를 통과한다.

`_finance_transition()` 은 **돈이 실제로 나가는 단계**다. 이중 승인이 그대로
`dispatch_a2a_withdrawal_request()` 로 이어질 수 있는 자리다.

### 2-b. 같은 뿌리의 두 번째 증상 — 채번

식별자 발급도 같은 구조였다. `MAX+1` 을 읽고 INSERT 하는데 그 사이가 잠기지 않는다:

```python
def next_po_id(con):
    row = con.execute(
        "SELECT po_id FROM po_drafts WHERE po_id LIKE 'PO-%' ORDER BY po_id DESC LIMIT 1"
    ).fetchone()
    n = int(row["po_id"].split("-")[1]) + 1 if row else 1
    return f"PO-{n:04d}"
```

같은 코드가 **세 벌** 있었다(`data/po_draft.py` · `data/repair_record.py` ·
`backend/services/decisions.py`) — 그리고 `mcp_server/tools/generate_disposal_document.py` 에
네 번째 사본이 있었다. 실측:

```
발급된 ID: ['PO-0121']
에러: ['IntegrityError: duplicate key value violates unique constraint "po_drafts_pkey"
        DETAIL: Key (po_id)=(PO-0121) already exists.']
```

전이 경쟁보다는 **덜 위험하다** — PK 제약이 데이터 정합성은 지켜준다. 대신 한쪽 사용자가
500 을 받는다. 정합성 사고가 아니라 가용성 사고다.

---

## 3. 왜 실패하는가 — 근본 원인

**Postgres 기본 격리수준이 READ COMMITTED 이기 때문이다.**

이 수준에서 각 statement 는 *"그 statement 가 시작된 시점에 커밋돼 있던 스냅샷"* 을 본다.
트랜잭션 전체가 아니라 **statement 단위**다. 그래서:

| 시각 | 트랜잭션 A (승인) | 트랜잭션 B (반려) |
|---|---|---|
| t1 | `SELECT state` → `'pending'` | |
| t2 | | `SELECT state` → `'pending'` ← A 가 아직 커밋 안 함 |
| t3 | 판정 통과 (pending == pending) | 판정 통과 (pending == pending) |
| t4 | `UPDATE ... state='approved'` (행 잠금 획득) | |
| t5 | | `UPDATE ...` → **A 의 COMMIT 까지 대기** |
| t6 | `COMMIT` | |
| t7 | | 대기 해제 → **WHERE `po_id = ?` 를 재평가** → 여전히 매칭 → 덮어씀 |

t7 이 핵심이다. Postgres 는 UPDATE 대기가 풀리면 WHERE 절을 다시 평가하는데,
**여기 WHERE 절에는 `state` 조건이 없다.** `po_id` 만 보므로 항상 매칭된다. 즉
"pending 이어야 한다"는 판정은 t3 에서 **한 번 하고 버려졌고**, 실제 쓰기 시점에는
아무도 그 조건을 다시 확인하지 않는다.

**왜 그동안 안 잡혔나.** 회귀 스위트가 이 경로를 검사하지 않는다.
`spikes/db_concurrency.py` 는 동시성을 다루지만 **서로 다른 테이블에 대한 INSERT 끼리**만
본다(④' — `traces` 쓰기 중 `po_drafts` INSERT 가 대기 없이 성공하는가). *"같은 행에 대한
두 전이"* 를 세우는 검사는 34스위트 어디에도 없었다. 단일 요청 계약(`api_contract` 52건,
`disposal_sign_contract` 26건)은 전부 통과하는데, 그 검사들은 **요청을 하나씩** 보낸다.

**이름이 사고를 가렸다.** `decisions.py`·`repairs.py` 는 이 헬퍼를 `_locked_row()` 라고
불렀다:

```python
def _locked_row(con, decision_id):
    r = con.execute("SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
    ...
```

**잠그지 않는다.** 이름이 거짓이면 호출부는 안전하다고 *믿고* 검토를 건너뛴다 —
이 코드를 읽은 사람이 여럿이었는데 아무도 멈추지 않은 이유가 그것이라고 본다.
`po.py` 는 그 헬퍼조차 없이 인라인 SELECT 였다(세 흐름 중 가장 노출이 큰 쪽인데).

---

## 4. 에지 케이스

수정하면서 함께 확인한 것들. **③④는 원본에도 있던 결함이고 이번에 함께 막았다.**

| # | 상황 | 수정 전 | 수정 후 |
|---|---|---|---|
| ① | 동시 승인 + 반려 | 둘 다 200, 한쪽 소실 | 1건 200 · 1건 409 |
| ② | 동시 승인 + 승인(같은 목표) | 둘 다 200 | 1건 200 · 1건 409 |
| ③ | `PO-%` 인데 접미가 숫자가 아닌 행 존재 (`PO-V1`) | `int()` ValueError → **그 테이블 채번 영구 마비** | 무시하고 정상 발급 |
| ④ | `PO-9999` 다음 채번 | 사전순 정렬이라 `PO-10000` 이 뒤로 밀림 → PK 충돌 무한 반복 | `PO-10000` 으로 전진 |
| ⑤ | 없는 ID 전이 | `KeyError` → 404 | 동일(잠금은 행이 있을 때만) |
| ⑥ | 이미 최종 상태인 건 재전이 | 409 | 동일 |
| ⑦ | 잠금 대기 중 상대가 롤백 | — | 대기 해제 후 원래 상태를 보고 정상 진행 |

③이 특히 고약하다. 마이그레이션 잔재·수동 보정·테스트 찌꺼기가 **한 건만** 섞여도
그 테이블의 발주 생성이 통째로 죽고, 에러 메시지(`invalid literal for int()`)는
원인을 전혀 가리키지 않는다. 실제로 이 문서의 검증 스크립트가 `PO-V1` 을 남겨서
우연히 드러났다.

④는 `%04d` 폭 고정 + 사전순 `ORDER BY` 의 조합에서 온다. 현재 발주는 121건이라 당장은
먼 얘기지만, 자릿수가 넘는 순간 **복구 불가능한 무한 PK 충돌**이 된다.

### 다루지 않은 것

- **분산 배포.** 자문 잠금·행 잠금은 같은 Postgres 인스턴스를 보는 프로세스 사이에서만
  유효하다. 지금 구조(단일 DB)에서는 충분하다.
- **낙관적 잠금(`If-Match`/버전 컬럼).** 사용자에게 "누가 먼저 눌렀다"를 보여주려면
  이쪽이 낫지만 스키마 변경 + API 계약 변경이 따른다. 지금은 409 로 충분하다 —
  `07_BACKLOG.md` 로 넘긴다.
- **MCP 도구의 draft INSERT.** 도구는 UPDATE 를 못 하므로(D10) 전이 경쟁의 당사자가
  아니다. 채번만 공유 계층으로 함께 옮겼다.

---

## 5. 수정 — 프로덕션 준비 코드

동시성 원시를 **한 곳**(`data/txn.py`)이 소유하게 하고 네 사본을 그리로 모았다.
`data/` 에 둔 이유는 `backend` 와 `mcp_server` 가 서로를 import 하지 않기 때문이다(D15) —
`data/po_draft.py`·`data/repair_record.py` 와 같은 규약이다.

### 5-1. 행 잠금

```python
def locked_row(con, table: str, pk_col: str, pk_value: str):
    """상태 전이의 대상 행을 **잠근 채** 읽는다."""
    r = con.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ? FOR UPDATE", (pk_value,)
    ).fetchone()
    if r is None:
        raise KeyError(pk_value)
    return r
```

`FOR UPDATE` 가 전부다. 두 번째 트랜잭션을 첫 번째의 COMMIT 까지 대기시키고,
**대기가 풀린 뒤 `state` 를 다시 읽게** 한다. 그래서 §3 표의 t7 에서 두 번째 요청은
이미 바뀐 상태를 보고 호출부의 판정에서 정상적으로 409 가 된다.

전제 하나: **UPDATE 와 같은 트랜잭션 안**이어야 한다. 여기서 읽고 커넥션을 닫은 뒤
다른 커넥션에서 쓰면 아무것도 막지 못한다.

### 5-2. 채번

```python
def next_sequential_id(con, table: str, col: str, prefix: str) -> str:
    con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"maintq.seq.{table}",))
    row = con.execute(
        f"SELECT {col} AS v FROM {table} WHERE {col} ~ ?"
        f" ORDER BY (substring({col} from '[0-9]+$'))::bigint DESC LIMIT 1",
        (f"^{prefix}-[0-9]+$",),
    ).fetchone()
    n = int(row["v"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}-{n:04d}"
```

세 가지가 함께 들어 있다.

- **`pg_advisory_xact_lock`** — 잠글 **행이 아직 없으므로** `FOR UPDATE` 를 쓸 수 없다.
  자문 잠금은 임의의 키에 걸고 **트랜잭션 종료 시 자동 해제**된다(`_xact_` 가 그 뜻) —
  해제를 잊어 잠금이 새는 경로가 없다. `LOCK TABLE` 보다 좁다: 같은 테이블의
  **채번끼리만** 직렬화되고 일반 읽기·수정은 막지 않는다.
- **정규식 필터** — 에지 케이스 ③. 형식에 맞는 행만 후보로 본다.
- **수치 정렬** — 에지 케이스 ④. `substring(...)::bigint` 로 정렬해 자릿수가 넘어도 맞다.

**시퀀스(`SERIAL`)를 쓰지 않은 이유**: `PO-%04d` 는 화면·문서·감사 로그에 그대로 찍히는
표시 규약이고 스파이크가 이 형식을 문자열로 대조한다. 시퀀스로 바꾸면 스키마 마이그레이션 +
그 계약 전부를 건드려야 한다. 이 함수는 **형식을 그대로 두고 경쟁만** 없앤다.

### 5-3. 호출부 (6곳)

| 파일 | 변경 |
|---|---|
| `backend/services/po.py` | `transition()`·`_finance_transition()` 인라인 SELECT → `txn.locked_row()` |
| `backend/services/decisions.py` | `_locked_row()`(이름값 회복)·`_next_decision_id()` 위임 |
| `backend/services/repairs.py` | `_locked_row()` 위임 |
| `data/po_draft.py` | `next_po_id()` 위임 |
| `data/repair_record.py` | `next_repair_id()` 위임 |
| `mcp_server/tools/generate_disposal_document.py` | `_next_decision_id()` 위임 (네 번째 사본 제거) |

`decisions.submit/sign/reject` 와 `repairs.submit/sign/reject` 는 이미 `_locked_row()` 를
부르고 있었으므로 **그 함수 하나가 진짜로 잠그게 되면서 6개 전이가 한꺼번에 고쳐졌다.**
호출부 코드는 한 줄도 바뀌지 않았다.

---

## 6. 검증

수정 후 실제 서비스 코드 경로(`po_svc.transition`·`po_draft.next_po_id`)로 재측정:

```
① 동시 승인/반려
    팀장A-승인  -> TransitionError(409) — 'rejected' 상태라 'approved' 로 전이할 수 없습니다
    팀장B-반려  -> 성공(200)
    => [해결됨] 정확히 1건만 통과

② 동시 채번 4건 (이물질 행 PO-V1/PO-V2 존재 상태)
    발급 ID: ['PO-0121','PO-0122','PO-0123','PO-0124'] · 에러: []
    => [해결됨] 4건 전부 고유

②-b 자릿수 넘침: PO-9999 → 'PO-10000'  => [정상]

③ 기능 불변: draft→pending→approved 정상 · 재승인 409 · 없는 PO KeyError(404)
```

**회귀 — 기준선과 전건 일치(기능 불변 증거):**

| 스위트 | 기준선 | 실측 |
|---|---|---|
| `write_tool_contract` | 30 | **30** |
| `repair_flow_contract` | 28 | **28** |
| `disposal_api_contract` | 36 | **36** |
| `api_contract` | 52 | **52** |
| `approvals_contract` | 26 | **26** |
| `disposal_sign_contract` | 26 | **26** |
| `bundle_integrity` | 26 | **26** |
| `db_concurrency` | 7 | **10** (D126 축 3건 신설) |
| `tools_profile_contract` | 7 | **7** |
| pytest 7파일 | 128 | **128** |
| pytest A2A 8파일 | 88(표기) | **107** ⚠ |

⚠ 마지막 줄은 **이 변경과 무관한 문서 낡음**이다 — 이 작업은 테스트를 추가하지 않았다.
`CLAUDE.md` 의 88 이 낡은 값으로 보인다(같은 계열 정정이 반복돼 왔다). 다음 세션에서 확인할 것.

---

## 7. 남은 일

- ✅ **회귀 축 신설 완료** — `spikes/db_concurrency.py` ⑭⑮⑯ (7 → **10건**).
  세 테이블 각각에 *"`locked_row()` 가 두 번째 읽기를 대기시키는가"* 를 세웠다.

  ⚠ **처음에는 두 스레드를 경쟁시켜 "둘 다 성공하는가"를 보게 짰다가 폐기했다.**
  뮤턴트(`FOR UPDATE` 제거)를 **놓치는 것을 실측했다** — SELECT→UPDATE 간격이 짧아
  잠금이 없어도 두 스레드가 우연히 어긋나면 그냥 통과한다. 경쟁 검사는 실패를
  *가끔* 잡으므로 회귀 가드가 될 수 없다. 대신 잠금의 **정의**를 직접 측정한다:
  한 트랜잭션이 행을 잡은 동안 두 번째 `locked_row()` 의 대기 시간을 잰다.

  뮤턴트로 실증했다 — `FOR UPDATE` 를 지우면 **3건 전부 FAIL** 한다:

  | | 수정본 | 뮤턴트(`FOR UPDATE` 제거) |
  |---|---|---|
  | 두 번째 읽기 대기 | **0.82s** (보유 0.8s) | **0.02s** |
  | 판정 | PASS ×3 | FAIL ×3 |
- ✅ **D127·D130 가드도 세웠다 (2026-09-05, `db_concurrency` 10→14)** — ⑰ 기본 대상은
  풀을 쓴다(양성 축) · ⑱ 격리 DSN 3경로가 풀을 타지 않는다 · ⑲ `DATABASE_URL` 부재 시
  3경로가 명시적으로 실패한다 · ⑳ `MAINTQ_DB` 설정·조회 0건.
  뮤턴트 4종으로 전부 실증했다.

  🔴 **그 과정에서 오라클을 한 번 잘못 만들었다** — ⑳의 탐지기 생존 검사를 스캐너와
  **같은 토큰**으로 조립했더니, 토큰을 망가뜨리는 뮤턴트에서 정규식과 probes 가 함께
  바뀌며 **자기충족적으로 통과**했다. 오라클 토큰을 독립적으로 조립(`"MAINT"+"Q_DB"` vs
  `"MAINTQ"+"_DB"`)해 해소. *부재 검사의 liveness 앵커는 검사 대상과 독립이어야 한다.*
- ✅ **`_next_*_id` 사본 재발 방지 정적 검사 완료 (2026-09-05, `db_concurrency` 14→16)** —
  ㉑ `MAX+1` 채번 사본이 `data/txn.py` 밖에 0건 · ㉒ 세 결재 흐름이 전부
  `txn.next_sequential_id()` 를 거친다(양성 축).

  🔴 **세우자마자 살아남은 사본 하나를 잡았다.** D126 은 *"네 벌이 한 곳으로 모였다"* 고
  적었지만 실제로 모인 것은 **셋**이었다 —
  `mcp_server/tools/create_repair_record.py::_next_repair_id` 가 남아 있었다.
  호출부(203행)는 이미 `repair_record.next_repair_id()`(→ `txn`)로 옮겨 갔고
  **참조는 0곳**이었다. 즉 사고를 내고 있던 활성 경로가 아니라 **죽은 코드**였다 —
  그래도 지운 이유는, 그것이 옛 패턴의 두 결함을 그대로 담은 채
  *다음 사람이 복사해 갈 자리*에 놓여 있었기 때문이다:

  | 옛 사본의 결함 | 결과 |
  |---|---|
  | `LIKE 'RPR-%'` 가 비숫자 접미 행(`RPR-V1` 등)까지 후보로 잡는다 | `int()` 가 죽어 그 테이블의 채번이 **영구 마비** |
  | `ORDER BY repair_id DESC` 가 **사전순** | `RPR-9999` 다음이 `RPR-10000` 으로 되돌아가 PK 충돌 **무한 반복** |
  | 자문 잠금 없음 | 동시 생성 시 두 요청이 같은 번호 → 한쪽 500 |

  **판정 방식** — 정규식 한 줄로 "MAX+1" 을 찾으면 오탐·미탐이 둘 다 심하다
  (`SELECT MAX(seq)` 는 정상이고 `PO-%04d` 는 설명문에도 나온다). 결함의 **정의**를
  두 축의 **곱**으로 세웠다: 한 함수 안에서 ⓐ 가장 큰 기존 식별자를 SQL 로 읽고
  ⓑ `PREFIX-NNNN` 표시 형식을 조립한다. 실측상 축A만 9곳·축B만 5곳이 있고 **전부 정상**이다.
  docstring 은 AST 에서 걷어낸다 — 위임 래퍼들이 형식을 설명문에 적고 있다.
  판정 단위는 **함수**다(모듈로 넓히면 `data/seed.py` 에서 무관한 두 구문이 만나 오탐한다).

  **뮤턴트 8종으로 실증했다.** 처음 7종을 돌렸을 때 **2종이 살아남았고, 둘 다 오라클 결함이었다**:

  | 뮤턴트 | 결과 |
  |---|---|
  | M0 삭제한 사본 복원 | ㉑ FAIL ✅ (사본 1건) |
  | M1 축A `MAX(` 갈래 실명 | 처음 **생존** → probe ㉣(MAX()+`%`-포맷 사본) 추가 후 FAIL ✅ |
  | M1b 축A `ORDER BY` 갈래 실명 | ㉑ FAIL ✅ (탐지기 3/4) |
  | M2 축B 형식 스펙 실명 | ㉑ FAIL ✅ (탐지기 3/4) |
  | M3 docstring 제외 제거 | 처음 **생존** → probe ㉡ 을 고친 뒤 FAIL ✅ |
  | M4 두 축의 곱 → 합 | ㉑ FAIL ✅ (사본 10건 오탐) |
  | M5 위임 탐지 실명 | ㉒ FAIL ✅ (위임 0곳) |
  | M6 스캔 대상 0개 | ㉑㉒ 둘 다 FAIL ✅ |

  🔴 **M3 이 살아남은 이유가 ⑳의 교훈과 같은 계열이다.** probe ㉡(위임 래퍼)의 설명문에
  형식(`PO-%04d`)만 넣었더니, docstring 제외를 걷어내도 **축A 가 꺼져 있어** 판정이
  안 바뀌었다 — probe 가 자기가 지킨다고 주장하는 것을 실제로는 안 지킨 것이다.
  설명문에 옛 SQL 과 형식을 **둘 다** 넣어 해소했다.
  *부재 검사의 liveness 픽스처는 "그럴듯한 모양"이 아니라 **판정을 실제로 뒤집는 것**이어야 한다.*
- 🟡 낙관적 잠금(`If-Match`)은 `07_BACKLOG.md` 로.
