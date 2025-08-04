import { useOverlays } from "../hooks/useOverlays";
import { useVideoSizing } from "../hooks/useVideoSizing";

function DrawingOverlay() {
  const overlays = useOverlays();
  const { videoRect } = useVideoSizing();

  const style: React.CSSProperties = {
    position: "absolute",
    left: videoRect.x,
    top: videoRect.y,
    width: videoRect.width,
    height: videoRect.height,
    pointerEvents: "none",
  };

  return (
    <div style={style} className="z-10">
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
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          ) : null
        )}
      </svg>
    </div>
  );
}

// Making the component available as both a default and named export
// to resolve the import issue in App.tsx.
export { DrawingOverlay };
export default DrawingOverlay;
