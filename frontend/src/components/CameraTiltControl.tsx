import type { PointerEvent } from "react";
import type { CameraTiltDirection } from "../hooks/useControls";

interface CameraTiltControlProps {
  activeDirection: CameraTiltDirection;
  onTiltChange: (direction: CameraTiltDirection) => void;
}

const baseButtonClasses =
  "min-w-[92px] px-4 py-2 text-xs font-semibold uppercase tracking-wider rounded-md border transition-all duration-150 ease-in-out focus:outline-none select-none";

export default function CameraTiltControl({
  activeDirection,
  onTiltChange,
}: CameraTiltControlProps) {
  const bindHold = (direction: CameraTiltDirection) => ({
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      event.currentTarget.setPointerCapture(event.pointerId);
      onTiltChange(direction);
    },
    onPointerUp: () => onTiltChange(0),
    onPointerCancel: () => onTiltChange(0),
    onPointerLeave: () => onTiltChange(0),
    onBlur: () => onTiltChange(0),
  });

  const buttonClasses = (direction: CameraTiltDirection) =>
    `${baseButtonClasses} ${
      activeDirection === direction
        ? "bg-purple-600 text-white border-purple-300 active:scale-95"
        : "bg-gray-800/80 text-gray-200 border-gray-600/70 hover:bg-gray-700/80 active:bg-purple-700 active:scale-95"
    }`;

  return (
    <div
      className="flex items-center gap-2 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-md px-3 py-2"
      title="Hold a button or PageUp/PageDown to tilt the camera servo"
    >
      <span className="text-[10px] tracking-[0.18em] uppercase text-gray-300 select-none">
        Camera Tilt
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className={buttonClasses(1)}
          title="Hold to tilt camera up (PageUp)"
          aria-pressed={activeDirection === 1}
          {...bindHold(1)}
        >
          Up
        </button>
        <button
          type="button"
          className={buttonClasses(-1)}
          title="Hold to tilt camera down (PageDown)"
          aria-pressed={activeDirection === -1}
          {...bindHold(-1)}
        >
          Down
        </button>
      </div>
    </div>
  );
}
