import React from "react";
import type { ControlMode } from "../hooks/useControls";

interface Props {
  mode: ControlMode;
  setMode: (m: ControlMode) => void;
  gamepadConnected: boolean;
}

export const ControlSchemeToggle: React.FC<Props> = ({ mode, setMode, gamepadConnected }) => {
  /* helpers ensure Pointer-Lock is requested inside the user gesture */
  const toKeyboard = () => setMode("inc");

  const toGamepad = () => {
    if (gamepadConnected) setMode("abs");
  };

  const toTrackPoint = () => {
    /* must be called from a user-generated event */
    document.body.requestPointerLock();
    setMode("mouse");
  };

  return (
    <div className="absolute bottom-4 left-4 z-30 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-xl p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={toKeyboard}
            className={`px-3 py-1.5 rounded text-sm font-medium ${
              mode === "inc" ? "bg-sky-600" : "bg-gray-600 hover:bg-gray-500"
            }`}
          >
            Keyboard
          </button>

          <button
            onClick={toGamepad}
            disabled={!gamepadConnected}
            className={`px-3 py-1.5 rounded text-sm font-medium ${
              mode === "abs"
                ? "bg-green-600"
                : gamepadConnected
                  ? "bg-gray-600 hover:bg-gray-500"
                  : "bg-gray-700 cursor-not-allowed opacity-60"
            }`}
          >
            Gamepad
          </button>

          <button
            onClick={toTrackPoint}
            className={`px-3 py-1.5 rounded text-sm font-medium ${
              mode === "mouse"
                ? "bg-red-600"
                : "bg-gray-600 hover:bg-gray-500"
            }`}
          >
            TrackPoint
          </button>
        </div>

        {/* status / hints */}
        <div className="text-xs text-gray-400 text-center">
          Current&nbsp;
          <span className="font-semibold text-gray-200">
            {mode === "inc" ? "Keyboard"
              : mode === "abs" ? "Gamepad"
              : "TrackPoint"}
          </span>
          {mode === "mouse" && <span>&nbsp;(Esc to release)</span>}
        </div>
      </div>
    </div>
  );
}; 