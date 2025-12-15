import { useOverlays } from "../hooks/useOverlays";

/**
 * A simple overlay that assumes its parent container is correctly sized
 * with the same aspect ratio as the video feed. It uses a normalized
 * (0-1) coordinate system.
 */
export default function StaticDrawingOverlay() {
  const overlays = useOverlays();

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none z-10"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
    >
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
            strokeWidth="0.005"
          />
        ) : null
      )}
    </svg>
  );
} 