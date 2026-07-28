/**
 * 매뉴얼 인용 표기 (D26 · D32).
 *
 * - `page`      : PDF 물리 페이지. 저장·평가 검증의 단일 기준 (D26). 절대 변환하지 않는다.
 * - `printPage` : manifest.print_page_offset 을 적용한 인쇄 페이지 (iG5A 0, S100 16).
 * - `label`     : 백엔드가 조립한 표시 라벨. 있으면 그대로 쓴다 — 조립은 백엔드 1곳 (D32).
 *
 * 오프셋 변환·라벨 조립은 백엔드 렌더 1곳(`backend.sse.citation_data`)에서만 하고,
 * 프론트는 받은 값을 표시만 한다. 평가 코드는 계속 `page` 만 본다 —
 * D26 의 목적(검증 단순화)이 유지된다.
 */
export interface Citation {
  /**
   * "iG5A 매뉴얼", "iG5A 트러블슈팅", "S100 매뉴얼".
   *
   * **optional 인 이유**: SSE 인용 payload 는 `{page, print_page, label}` **뿐**이다
   * (backend/sse.py `citation_data` — manual·section 필드 없음). required 로 두면
   * SSE 리듀서가 값을 지어내야 한다. label 있으면 생략 가능.
   */
  manual?: string;
  /** PDF 물리 페이지 — 불변 (D26) */
  page: number;
  /** 인쇄 페이지. 생략 = 인쇄 페이지 미상 (같다는 뜻이 아니다 — 라벨이 "PDF p." 로 정직 표기) */
  printPage?: number;
  /** "12.2 고장 대책" 같은 절 표기 */
  section?: string;
  /** 백엔드가 조립한 표시 라벨 (sse.citation_data). 있으면 재조립 금지 (D32) */
  label?: string;
}

/**
 * 표시용 라벨.
 *
 * 1. `label` 이 있으면 **그대로 반환** — 라벨 조립은 백엔드 렌더 1곳 (D32). 재조립 금지.
 * 2. label 없고 `printPage` 도 없으면(= `/api/po/{id}` evidence 경로, 인쇄 페이지 미상) →
 *    `"{manual} PDF p.{page}"`. 프론트는 offset 을 모르므로 "PDF" 표기가 유일하게 정직하다
 *    (W-6 의 계약-무변경 해소). manual 도 없으면 `"매뉴얼 PDF p.{page}"` 폴백 — 빈 라벨 금지.
 * 3. label 없고 `printPage` 있으면 기존 규칙: 인쇄 페이지를 앞에 두고,
 *    물리 페이지와 다를 때만 PDF 쪽수를 병기한다.
 *
 *   SSE 경로            → label 그대로 (예: "S100 매뉴얼 p.400 (PDF p.416)")
 *   iG5A (offset 0)     → "iG5A 매뉴얼 p.202"
 *   S100 (offset 16)    → "S100 매뉴얼 p.400 (PDF p.416)"
 *   인쇄 페이지 미상    → "iG5A 매뉴얼 PDF p.202"
 */
export function citationLabel(c: Citation): string {
  if (c.label) return c.label;

  const manual = c.manual ?? "매뉴얼";
  const head =
    c.printPage === undefined
      ? `${manual} PDF p.${c.page}`
      : c.printPage === c.page
        ? `${manual} p.${c.printPage}`
        : `${manual} p.${c.printPage} (PDF p.${c.page})`;
  return c.section ? `${head} · ${c.section}` : head;
}
