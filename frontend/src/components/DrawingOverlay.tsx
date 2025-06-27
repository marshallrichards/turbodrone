import { useOverlays } from '../hooks/useOverlays';
import { useState, useEffect } from 'react';

export function DrawingOverlay() {
  const overlays = useOverlays();
  const [style, setStyle] = useState<React.CSSProperties>({});

  // --- ⭑⭑⭑ DEBUG LOG ⭑⭑⭑ ---
  // This will log every time the component re-renders.
  // We should see it log when new overlay data arrives.
  console.log('[DrawingOverlay] Re-rendering with overlays:', overlays);

  useEffect(() => {
    // This function will be responsible for finding the video element and setting up the observer.
    const setupObserver = () => {
      const videoElement = document.querySelector('img[alt="Drone video feed"]');

      if (!videoElement) {
        // If the video element isn't found, try again in a moment.
        // This is the key fix to handle the race condition.
        requestAnimationFrame(setupObserver);
        return;
      }

      const observer = new ResizeObserver(() => {
        const img = videoElement as HTMLImageElement;
        const rect = img.getBoundingClientRect(); // viewport-relative

        const natW  = img.naturalWidth  || 1;
        const natH  = img.naturalHeight || 1;
        const imgAR = natW / natH;
        const boxAR = rect.width / rect.height;

        let visW: number, visH: number, padX = 0, padY = 0;
        if (boxAR > imgAR) {
          // container is wider: pillar-boxing → bars on the sides
          visH = rect.height;
          visW = rect.height * imgAR;
          padX = (rect.width - visW) / 2;
        } else {
          // container is narrower (or equal): letter-boxing → bars top/bottom
          visW = rect.width;
          visH = rect.width / imgAR;
          padY = (rect.height - visH) / 2;
        }

        // --- ⭑⭑⭑ NEW DEBUG LOG ⭑⭑⭑ ---
        console.log(
          `[Overlay] visible ${Math.round(visW)}×${Math.round(visH)}, ` +
          `padX ${padX}px padY ${padY}px`
        );

        // ---- position SVG over that exact area ------------------------------
        setStyle({
          position: "absolute",
          width:    visW,
          height:   visH,
          top:      rect.top  + padY + window.scrollY,
          left:     rect.left + padX + window.scrollX,
          pointerEvents: "none",
        });
      });

      observer.observe(videoElement);

      // Return a cleanup function to disconnect the observer when the component unmounts.
      return () => {
        observer.disconnect();
      };
    };

    // Start the process.
    const cleanup = setupObserver();

    // The returned function from useEffect will be called on unmount.
    return cleanup;
  }, []); // The empty dependency array is correct; we handle retries internally.

  return (
    <div className="absolute inset-0 w-full h-full pointer-events-none flex items-center justify-center z-10">
      <svg
        className="max-w-full max-h-full"
        style={style}
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
      >
        {overlays.map((item, index) => {
          if (item.type === 'rect') {
            let [x1, y1, x2, y2] = item.coords;

            // Clamp to view-box (0‥1) so nothing renders outside
            const clamp = (v: number) => Math.min(1, Math.max(0, v));
            x1 = clamp(x1);
            y1 = clamp(y1);
            x2 = clamp(x2);
            y2 = clamp(y2);

            // Skip degenerate / fully-clipped boxes
            if (x2 <= x1 || y2 <= y1) return null;

            return (
              <rect
                key={index}
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                fill="none"
                stroke={item.color || "lime"}
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            );
          }
          return null;
        })}
      </svg>
    </div>
  );
} 