import type { CommandCapabilities } from "../hooks/useControls";

interface CommandButtonsProps {
  droneType: string;
  capabilities: CommandCapabilities;
  onTakeoff: () => void;
  onLand: () => void;
  onEstop: () => void;
}

const disabledButtonClasses =
  "bg-gray-700/80 border border-gray-500/40 text-gray-400 cursor-not-allowed opacity-70";

const baseButtonClasses =
  "min-w-[112px] px-5 py-2.5 font-semibold rounded-lg shadow-md transition-all duration-150 ease-in-out border focus:outline-none";

export default function CommandButtons({
  droneType,
  capabilities,
  onTakeoff,
  onLand,
  onEstop,
}: CommandButtonsProps) {
  return (
    <div className="flex flex-col items-center gap-2 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-xl p-3">
      <div className="text-[11px] tracking-[0.18em] uppercase text-gray-300 select-none">
        {droneType} Controls
      </div>
      <div className="flex gap-4">
        <button
          onClick={onTakeoff}
          disabled={!capabilities.takeoff}
          className={`${baseButtonClasses} ${
            capabilities.takeoff
              ? "bg-green-600 hover:bg-green-700 active:bg-green-800 active:scale-95 text-white border-green-500/60"
              : disabledButtonClasses
          }`}
          title={capabilities.takeoff ? "Trigger takeoff" : "Takeoff is unavailable for this implementation"}
        >
          Takeoff
        </button>
        <button
          onClick={onLand}
          disabled={!capabilities.land}
          className={`${baseButtonClasses} ${
            capabilities.land
              ? "bg-orange-600 hover:bg-orange-700 active:bg-orange-800 active:scale-95 text-white border-orange-400/70"
              : disabledButtonClasses
          }`}
          title={capabilities.land ? "Trigger land / descend" : "Land is unavailable for this implementation"}
        >
          Land
        </button>
        <button
          onClick={onEstop}
          disabled={!capabilities.estop}
          className={`${baseButtonClasses} ${
            capabilities.estop
              ? "bg-red-700 hover:bg-red-800 active:bg-red-900 active:scale-95 text-yellow-200 border-yellow-300/60"
              : disabledButtonClasses
          }`}
          title={capabilities.estop ? "Emergency stop" : "Emergency stop is unavailable for this implementation"}
        >
          E-STOP
        </button>
      </div>
    </div>
  );
}