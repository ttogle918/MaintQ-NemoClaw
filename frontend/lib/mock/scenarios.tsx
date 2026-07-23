import { Mono } from "@/components/ui/Mono";
import type { Citation } from "../citation";
import type { ChatItem } from "../types";

export type Scenario = "s1" | "s3";

/* 인용 — 저장·검증은 물리 페이지, 표시는 인쇄 우선 (D26·D32).
   iG5A 는 오프셋 0 이라 물리 = 인쇄. S100 은 물리 = 인쇄 + 16. */
const IG5A = (page: number, section?: string): Citation => ({
  manual: "iG5A 매뉴얼",
  page,
  printPage: page,
  section,
});
const IG5A_TS = (page: number): Citation => ({
  manual: "iG5A 트러블슈팅",
  page,
  printPage: page,
});

/** S1 — 순차 실행 (진단 → 재고 → 견적 → 발주 초안) */
export const CHAT_S1: ChatItem[] = [
  {
    kind: "user",
    id: "s1-u1",
    content: (
      <>
        iG5A 인버터에 <Mono>OHt</Mono> 에러 떴어
      </>
    ),
  },
  {
    kind: "agent",
    id: "s1-a1",
    citations: [IG5A(202)],
    content: (
      <>
        <b>
          <Mono>OHt</Mono> — 인버터 과열
        </b>
        입니다. 유력 원인은 냉각팬 고장·주위 온도 초과. 냉각팬 상태 점검을 권장합니다.
      </>
    ),
  },
  {
    kind: "safety",
    id: "s1-safety",
    title: "SAFETY · 감전 위험",
    citation: IG5A(4),
    body: (
      <>
        커버 개방 전 전원 차단 후 <b>10분 이상 대기</b>, 테스터로 직류 전압 방전 확인. 활선 상태
        접촉·측정 금지.
      </>
    ),
  },
  {
    kind: "error_log",
    id: "s1-log",
    equipmentId: "INV-L1-01",
    code: "OHt",
  },
  {
    kind: "po_draft",
    id: "s1-po",
    po: {
      poId: "PO-0117",
      partName: "냉각팬",
      partNo: "FAN-IG5-01",
      qty: 2,
      qtyNote: "부족분 포함",
      supplierName: "A사",
      leadDays: 3,
      unitPrice: 38000,
      state: "draft",
    },
  },
];

/** S3 — 이력 기반 판단 + 가드레일 (발주 보류) */
export const CHAT_S3: ChatItem[] = [
  {
    kind: "user",
    id: "s3-u1",
    content: (
      <>
        3번 라인 인버터 <b>또</b> <Mono>OCt</Mono> 떴어
      </>
    ),
  },
  {
    kind: "agent",
    id: "s3-a1",
    citations: [IG5A(204, "12.2 고장 대책")],
    content: (
      <>
        <b>
          <Mono>OCt</Mono> — 인버터 과전류
        </b>
        입니다. 다만 이 설비는 <b>30일 내 3회 반복 발생</b>(매번 리셋만 수행)으로, 단순 조치 대신{" "}
        <b>근본원인 점검 모드</b>로 전환합니다.
      </>
    ),
  },
  {
    kind: "repeat_banner",
    id: "s3-banner",
    badge: "3×",
    content: (
      <>
        <b>반복 고장 감지</b> — 3번 라인 <Mono>INV-L3-01</Mono> · 최근 30일 <Mono>OCt</Mono> 3회
        (07-01·07-11·07-19)
      </>
    ),
  },
  {
    kind: "error_log",
    id: "s3-log",
    equipmentId: "INV-L3-01",
    code: "OCt",
    recordedAt: "2026-07-19 14:20",
  },
  {
    kind: "safety",
    id: "s3-safety",
    title: "SAFETY · 감전 위험",
    citation: IG5A_TS(6),
    body: (
      <>
        절연저항 측정 전 전원 차단 후 <b>10분 이상 대기</b>, 테스터로 직류 전압 방전 확인. 활선
        상태 절연 측정 금지.
      </>
    ),
  },
  {
    kind: "po_hold",
    id: "s3-hold",
    hold: {
      reason: (
        <>
          반복 고장은 부품 교체만으로 재발할 수 있어,{" "}
          <b>근본원인이 확정되기 전에는 발주서를 생성하지 않습니다.</b> 아래 점검을 먼저
          진행하세요.
        </>
      ),
      checklist: [
        { label: "출력측 지락(단락) 점검", citation: IG5A(204) },
        { label: "모터 절연저항 측정 (권선 절연 저하)", citation: IG5A(205) },
        { label: "부하 이상·가감속 시간 과다 확인", citation: IG5A(206) },
      ],
    },
  },
];

export const CHAT_BY_SCENARIO: Record<Scenario, ChatItem[]> = {
  s1: CHAT_S1,
  s3: CHAT_S3,
};
