import React from "react";
import type { ControlMode } from "../hooks/useControls";

interface Props {
  mode: ControlMode;
  setMode: (m: ControlMode) => void;
  gamepadConnected: boolean;
}

export const ControlSchemeToggle: React.FC<Props> = ({ mode, setMode, gamepadConnected }) => {
  const toggle = () => {
    if (mode === "inc" && !gamepadConnected) return; // Don't allow switching to gamepad if none connected
    setMode(mode === "inc" ? "abs" : "inc");
  };

  const isDisabled = mode === "inc" && !gamepadConnected;
  const isGamepadMode = mode === "abs";

  return (
    <div className="absolute bottom-4 left-4 z-30 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-xl p-4">
      <div className="flex flex-col items-start gap-3">
        {/* Toggle Switch */}
        <div className="flex items-center gap-3">
          <span 
            className={`text-sm font-medium transition-colors duration-200 ${
              !isGamepadMode && !isDisabled ? 'text-sky-400' : 'text-gray-400'
            }`}
          >
            Keyboard
          </span>
          
          <button
            onClick={toggle}
            disabled={isDisabled}
            aria-pressed={isGamepadMode}
            aria-label={`Switch to ${isGamepadMode ? "Keyboard" : "Gamepad"} controls`}
            className={`
              relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-200 ease-in-out
              focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-gray-900/70
              ${isDisabled 
                ? 'bg-gray-700 cursor-not-allowed opacity-60' 
                : isGamepadMode 
                  ? 'bg-green-500 hover:bg-green-400' 
                  : 'bg-gray-600 hover:bg-gray-500'
              }
            `}
          >
            <span
              className={`
                inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-1 ring-gray-900/5 transition-transform duration-200 ease-in-out
                ${isGamepadMode ? 'translate-x-[22px]' : 'translate-x-1'}
              `}
            />
          </button>
          
          <span 
            className={`text-sm font-medium transition-colors duration-200 ${
              isGamepadMode && gamepadConnected && !isDisabled ? 'text-green-400' : 
              !gamepadConnected ? 'text-gray-600' : 'text-gray-400'
            }`}
          >
            Gamepad
          </span>
        </div>

        {/* Status Labels */}
        <div className="text-xs text-center w-full pt-1">
          <div className="text-gray-400 mb-1">
            Current: <span className="font-semibold text-gray-200">
              {mode === "inc" ? "Keyboard" : "Gamepad"}
            </span>
          </div>
        </div>
        
        {/* Gamepad status indicator */}
        <div className="flex items-center gap-2 text-xs w-full justify-center border-t border-gray-700/80 pt-2">
          <div 
            className={`w-2.5 h-2.5 rounded-full transition-colors duration-200 ${
              gamepadConnected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span 
            className={`transition-colors duration-200 ${
              gamepadConnected ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {gamepadConnected ? 'Gamepad Connected' : 'No Gamepad Detected'}
          </span>
        </div>
      </div>
    </div>
  );
}; 