/**
 * 설비 하이라이트 대시보드 — 매뉴얼 도면 좌표 (Sprint 10 브레인스토밍 C, spec §4-3).
 *
 * DB 가 아니라 정적 상수다 — 실물 도면과 1:1 매칭이라 좌표가 바뀔 이유가 없다.
 * 좌표는 크롭된 이미지(`frontend/public/manuals/*.png`) 기준 %(좌상단 원점)다.
 *
 * ⚠ 라이선스: LS ELECTRIC 매뉴얼 도면 원본. 비상업적 학습·포트폴리오 목적으로만 사용 —
 *   화면에 `citation` 을 항상 표시할 것(spec §4-2, 사용자 승인 완료).
 */

export interface Hotspot {
  partNo: string; // parts.part_no 와 매칭 — 있으면 실 데이터 조회 가능
  label: string;
  x: number; // 기본 도면 이미지 폭에 대한 % (0-100)
  y: number; // 기본 도면 이미지 높이에 대한 % (0-100)
  /** true 면 도면에 정확한 라벨이 없는 근사 배치 — 화면에 고지 필요 */
  approximate?: boolean;
  /** 있으면 클릭 시 이 실제 근접 이미지로 전환. 없으면 기본 도면을 이 좌표 중심으로 CSS 확대한다 */
  detailImage?: string;
}

export const IG5A_HOTSPOTS: Hotspot[] = [
  {
    partNo: "FAN-IG5-01",
    label: "냉각팬",
    x: 45,
    y: 72,
    detailImage: "/manuals/ig5a_fan_detail.png",
  },
  { partNo: "KPD-IG5-01", label: "키패드", x: 47, y: 25 },
  { partNo: "PCB-IG5-CTRL", label: "제어보드", x: 50, y: 48, approximate: true },
];

export const S100_HOTSPOTS: Hotspot[] = [
  { partNo: "FAN-S100-01", label: "냉각팬", x: 63, y: 28 },
  { partNo: "KPD-S100-01", label: "키패드", x: 51, y: 48 },
  { partNo: "PCB-S100-CTRL", label: "제어보드", x: 53, y: 54, approximate: true },
];

export const MODEL_HOTSPOTS: Record<string, Hotspot[]> = {
  iG5A: IG5A_HOTSPOTS,
  S100: S100_HOTSPOTS,
};

export const MODEL_BASE_IMAGE: Record<string, string> = {
  iG5A: "/manuals/ig5a_hotspot_base.png",
  S100: "/manuals/s100_hotspot_base.png",
};

/** 화면에 항상 표시할 출처 고지 (spec §4-2 라이선스 조항). */
export const MODEL_CITATION: Record<string, string> = {
  iG5A: "LS ELECTRIC iG5A 사용설명서 물리 p.22 (그림 1-2, 전면 덮개 제거 시)",
  S100: "LS ELECTRIC S100 사용설명서 인쇄 p.3 · PDF p.19 (1.2.1 분해도)",
};

export const FAN_DETAIL_CITATION =
  "LS ELECTRIC iG5A 사용설명서 물리 p.23 (그림 1-4, 인버터 냉각 팬을 교체할 때)";
