import { useOverlays } from '../hooks/useOverlays';

export function DrawingOverlay() {
  const overlays = useOverlays();

  return (
    <div className="absolute inset-0 w-full h-full pointer-events-none flex items-center justify-center">
      <svg
        className="max-w-full max-h-full"
        viewBox="0 0 1 1"
        preserveAspectRatio="xMidYMid meet"
      >
        {overlays.map((item, index) => {
          if (item.type === 'rect') {
            const [x1, y1, x2, y2] = item.coords;
            return (
              <rect
                key={index}
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                fill="none"
                stroke={item.color || 'lime'}
                strokeWidth="0.005"
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