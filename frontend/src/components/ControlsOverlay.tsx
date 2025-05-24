import AxisIndicator from "./AxisIndicator";
import type { Axes } from "../hooks/useControls";
import CommandButtons from "./CommandButtons";

interface ControlsOverlayProps {
  axes: Axes;
  onTakeoff: () => void;
  onLand: () => void;
}

export default function ControlsOverlay({ axes, onTakeoff, onLand }: ControlsOverlayProps) {
  const left   = { x: axes.roll,     y: axes.pitch };
  const right  = { x: axes.yaw,      y: axes.throttle };

  return (
    <div className="absolute inset-0 pointer-events-none z-10">
      {/* title bar */}
      <div className="absolute top-0 left-0 right-0 flex justify-center py-6 bg-black/60 backdrop-blur-sm border-b border-white/10">
        <h1 
          className="font-heading font-bold text-white drop-shadow-lg select-none"
          style={{ 
            fontSize: '2rem', 
            letterSpacing: '0.1em',
            lineHeight: '1.2',
            margin: 0,
            padding: 0
          }}
        >
          TURBORONE WEB
        </h1>
      </div>

      {/* Controls Area: Buttons and Sticks */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-5 z-20 pointer-events-auto">
        {/* Command Buttons Cluster */}
        <CommandButtons onTakeoff={onTakeoff} onLand={onLand} />

        {/* Sticks */}
        <div className="flex gap-10">
          <AxisIndicator {...left}  label="PITCH / ROLL" />
          <AxisIndicator {...right} label="YAW / THROTTLE" />
        </div>
      </div>
    </div>
  );
} 