/**
 * 매뉴얼 인용 표기 (D26 · D32).
 *
 * - `page`      : PDF 물리 페이지. 저장·평가 검증의 단일 기준 (D26). 절대 변환하지 않는다.
 * - `printPage` : manifest.print_page_offset 을 적용한 인쇄 페이지 (iG5A 0, S100 16).
 *
 * 오프셋 변환은 백엔드 렌더 1곳에서만 하고, 프론트는 받은 값을 표시만 한다.
 * 평가 코드는 계속 `page` 만 본다 — D26 의 목적(검증 단순화)이 유지된다.
 */
export interface Citation {
  /** "iG5A 매뉴얼", "iG5A 트러블슈팅", "S100 매뉴얼" */
  manual: string;
  /** PDF 물리 페이지 */
  page: number;
  /** 인쇄 페이지. 생략 시 물리 페이지와 동일한 것으로 본다 */
  printPage?: number;
  /** "12.2 고장 대책" 같은 절 표기 */
  section?: string;
}

/**
 * 표시용 라벨을 만든다. 인쇄 페이지를 앞에 두고, 물리 페이지와 다를 때만 PDF 쪽수를 병기한다.
 *
 *   iG5A (offset 0)  → "iG5A 매뉴얼 p.202"
 *   S100 (offset 16) → "S100 매뉴얼 p.400 (PDF p.416)"
 */
export function citationLabel(c: Citation): string {
  const print = c.printPage ?? c.page;
  const head = `${c.manual} p.${print}`;
  const withPdf = print === c.page ? head : `${head} (PDF p.${c.page})`;
  return c.section ? `${withPdf} · ${c.section}` : withPdf;
}
