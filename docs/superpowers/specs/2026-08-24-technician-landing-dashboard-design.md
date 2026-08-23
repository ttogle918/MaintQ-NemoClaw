# 정비사 랜딩 화면 전환 — 챗봇 → 설비 대시보드 — 설계

**작성일**: 2026-08-24 · **브레인스토밍 세션**: 같은 날 대화 · **상태**: 사용자 승인 완료

## 0. 배경

지금까지 정비사 콘솔(`/technician`)의 첫 화면은 진단 챗봇(`DiagnosticConsole`)이었다. 사용자 요청으로 앱
진입 시 첫 화면을 설비 대시보드로 바꾸고, 챗봇은 우측 하단 원형 플로팅 버튼으로 옮긴다.

조사 결과 `/technician/equipment-status`(Sprint 10 브레인스토밍 C, `2026-08-17-equipment-highlight-
dashboard-design.md`)가 이미 요청과 매우 가까운 화면이었다 — 설비별 카드 목록 + 🔴🟠🔵 하이라이트
배지 + 상세 드릴다운. 두 안(알림 목록형 vs 카드 그리드형) 중 **기존 화면 확장**으로 방향을 정했다 —
새 백엔드·새 API 없이 라우팅과 기존 화면만 손대면 된다.

## 1. 범위

**포함**: 랜딩 라우팅 전환 · 대시보드 카드에 모델 이미지·인용문구·모델명 추가 · 챗 플로팅 버튼(FAB) 신설

**제외** (이번 세션 스코프 밖, 사용자 요청대로):
- doc3(자금집행요청서) 렌더 — 별도 논의 필요(D118 참고)
- `/technician/asset`(처분 사전판정 목록)·`/technician/po/new` 등 다른 정비사 서브 화면 변경 없음
- 백엔드·DB·API 신설 없음 — 전부 기존 엔드포인트(`getAssets`·`getHotspotStatus`·`getPoQueue`) 재사용

## 2. 랜딩 라우팅 전환

`frontend/lib/role.ts`:
```ts
export const ROLE_HOME: Record<Role, string> = {
  technician: "/technician/equipment-status",  // 기존 "/technician"
  manager: "/manager",
};
```

- 루트(`/`, `app/page.tsx`)는 이미 `redirect(ROLE_HOME.technician)`이므로 **코드 변경 없이** 새
  타깃을 따라간다.
- `AppBar`의 "정비사" 탭(`RoleTabs.tsx`)도 같은 상수(`ROLE_HOME[role]`)를 링크로 쓰므로 자동 반영.
- `/technician`(챗봇 전체화면, `?scenario=s1|s3`·`?replay=s1`·`?prefill=`·`?equipment=` 데모/딥링크
  파라미터 포함)은 **URL·코드 모두 무변경**. `docs/demo_script.md`·`frontend/README.md`가 이 경로를
  직접 참조하므로 깨지지 않아야 한다(grep으로 두 문서가 리터럴 `/technician?...` 경로를 쓰는 것
  확인 완료, `ROLE_HOME`을 거치지 않음).

## 3. 대시보드 카드 확장 (`/technician/equipment-status`, 기존 화면)

기존 `EquipmentStatusListPage`(`frontend/app/(console)/technician/equipment-status/page.tsx`)의
`EquipmentRow`에 다음을 추가한다. **새 API 호출 없음** — 이미 병렬로 fetch 중인
`getHotspotStatus` 응답(`ApiHotspotStatus.model`)을 그대로 쓴다.

### 3-1. 모델 이미지 + 인용문구
`frontend/lib/hotspots.ts`의 `MODEL_BASE_IMAGE`·`MODEL_CITATION`(iG5A·S100, 매뉴얼 도면 원본,
라이선스 인용 의무 있음, spec §4-2 선례)을 카드 좌측 썸네일로 재사용한다:
- 이미지 아래 인용문구를 **작은 글자 한 줄**로 붙인다(카드마다, 인용 의무 준수).
- IE5는 `MODEL_BASE_IMAGE`에 항목이 없다(D109 — model enum 은 3종으로 확장됐지만 안전 문구·RAG
  청킹·이 하이라이트 좌표는 iG5A·S100만 커버) → **폴백**: 인용문구 없는 중립 아이콘(예: 단순 기어
  글리프) 표시. 현재 시드 데이터에는 `equipment.model = 'IE5'` 인스턴스가 없어(CHECK 제약이 여전히
  2종) 실사용에서 이 분기를 만날 일은 없지만, 방어적으로 둔다.
- `model`이 `undefined`(hotspot-status 조회 실패/아직 로딩 중)인 동안은 이미지 자리에 스켈레톤/빈
  자리만 두고 조회 실패를 지어내지 않는다.

### 3-2. 모델명 표시
카드에 모델명 텍스트(`iG5A`/`S100`/`IE5`)를 라인 위치 옆에 추가.

### 3-3. 기존 유지
🔴🟠🔵 배지, 라인 위치, "확인 중…"/"상태 미상" 분기는 그대로.

## 4. 챗 플로팅 버튼 (신규 `frontend/components/layout/ChatFab.tsx`)

### 4-1. 배치
`frontend/app/(console)/layout.tsx`의 `Shell`에 삽입 — 정비사·매니저 공용 셸이므로 컴포넌트
내부에서 노출 조건을 건다:
```
roleFromPath(pathname) === "technician" && pathname !== "/technician"
```
→ 정비사 콘솔의 모든 화면(대시보드·설비 상세·자산 목록·발주 상세 등)에 뜨고, 챗 페이지 자체와
매니저 화면에는 숨는다.

### 4-2. 동작
우측 하단 고정 원형 버튼. 클릭 시 `/technician`으로 `Link` 이동(오버레이/드로어 아님 — SSE 세션은
매번 새로 시작). 레이아웃은 라우트 이동 시 리마운트되지 않으므로 버튼은 정비사 콘솔 내 이동 중에도
같은 자리에 고정되어 보인다.

### 4-3. 배지 — "미해결 draft 발주 수"
```ts
getPoQueue("technician", "draft").length
```
`draft`는 에이전트/화면이 만들었지만 정비사가 아직 승인 요청(`submitPo`)을 하지 않은 발주 상태다 —
"정비사의 다음 조치를 기다리는 건수"로 정직하게 해석 가능한 **실측값**이다(D62 — 챗 "미읽음
메시지"는 백엔드에 그런 개념 자체가 없으므로(D41, SSE 대화 미저장) 지어내지 않는다).

- `Shell` 마운트 시 1회 fetch. 폴링 없음(과설계 방지 — 필요해지면 다음 세션에서 논의).
- 0건이면 배지를 그리지 않는다(다른 화면의 "null 이면 배지를 만들지 않는다" 관례와 동일,
  예: `AssetRow`의 `category`/`status` 태그).
- 조회 실패 시 배지를 숨긴다(에러를 숫자 0으로 위장하지 않는다).

## 5. 영향 없음 확인

- 백엔드 코드·API·DB 스키마 변경 0건
- 프론트 라우트 수 무변화(21개 그대로 — 새 페이지 파일 없음, 컴포넌트·상수 변경뿐)
- 기존 회귀 스위트(`ui_honesty_contract` 등)에 영향 줄 소지가 있는 부분: `EquipmentStatusListPage`
  수정이 `ui_honesty_contract`의 `app/(console)/**/*.tsx` 글롭에 이미 편입돼 있어 L2 검사(6항목)를
  다시 통과하는지 확인 필요(신규 위반 없어야 함) — `next build`·`tsc --noEmit`로 정적 검증.

## 6. 알려진 제약

라이브 서버(`backend.main:app`)가 이번 세션에도 DB 조회 엔드포인트에서 hang 하는 상태라(재부팅
후에도 재현, `docs/sessions/2026-08-24.md` 트러블슈팅 절 참고) 구현 후 브라우저 실사용 검증이
막혀 있을 가능성이 높다. 정적 검증(`tsc --noEmit`·`next build`)으로 대체하고, hang 이 해소되면
사람이 브라우저로 직접 확인할 것을 권장한다.
