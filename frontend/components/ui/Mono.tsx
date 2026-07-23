import { sx } from "@/lib/sx";

/** 코드·품번·에러코드·설비 ID 는 항상 모노스페이스 (08_DESIGN_BRIEF 타이포 규칙). */
export function Mono({
  children,
  size = 12,
}: {
  children: React.ReactNode;
  size?: number;
}) {
  return (
    <span style={sx(`font-family:'JetBrains Mono',monospace;font-size:${size}px`)}>
      {children}
    </span>
  );
}
