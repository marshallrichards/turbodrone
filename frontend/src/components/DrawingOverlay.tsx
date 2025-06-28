import { useEffect, useRef, useState } from "react";
import { useOverlays } from "../hooks/useOverlays";

interface Box { x: number; y: number; w: number; h: number; color: string }

export default function DrawingOverlay() {
  const overlays = useOverlays();
  const [style, setStyle] = useState<React.CSSProperties>({});
  const overlayRef = useRef<HTMLDivElement>(null);

  /* ───────────────────────────
   * Track the visible video rect
   * ─────────────────────────── */
  useEffect(() => {
    const img = document.querySelector(
      'img[alt="Drone video feed"]'
    ) as HTMLImageElement | null;
    if (!img) return;

    const calc = () => {
      if (!img.naturalWidth) return;           // wait until frame arrived
      const rect  = img.getBoundingClientRect();
      const arImg = (img.naturalWidth || 1) / (img.naturalHeight || 1);
      const arBox = rect.width / rect.height;

      let w: number, h: number, x: number, y: number;

      if (arBox > arImg) {
        // bars left / right
        h = rect.height;
        w = h * arImg;
        x = rect.left + (rect.width - w) / 2;
        y = rect.top;
      } else {
        // bars top / bottom
        w = rect.width;
        h = w / arImg;
        x = rect.left;
        y = rect.top + (rect.height - h) / 2;
      }

      setStyle({
        position: "absolute",
        width: w,
        height: h,
        left: x + window.scrollX,
        top: y + window.scrollY,
        pointerEvents: "none",
      });
    };

    // call once when the first frame arrives
    if (img.complete) {
      calc();
    } else {
      img.onload = calc;
    }

    const ro = new ResizeObserver(calc);
    ro.observe(img);

    return () => ro.disconnect();
  }, []);

  /* ───────────────────────────
   * Render
   * ─────────────────────────── */
  return (
    <div ref={overlayRef} style={style} className="z-10">
      <svg viewBox="0 0 1 1" width="100%" height="100%">
        {overlays.map((o, i) =>
          o.type === "rect" ? (
            <rect
              key={i}
              x={o.coords[0]}
              y={o.coords[1]}
              width={o.coords[2] - o.coords[0]}
              height={o.coords[3] - o.coords[1]}
              fill="none"
              stroke={o.color || "lime"}
              strokeWidth={2}                  // 2-px outline
              vectorEffect="non-scaling-stroke"
            />
          ) : null
        )}
      </svg>
    </div>
  );
}

// Make the component available both as default *and* named export
export { DrawingOverlay }; 