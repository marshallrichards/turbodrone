interface CommandButtonsProps {
  onTakeoff: () => void;
  onLand: () => void;
  // Add other command handlers here in the future, e.g., onToggleRecord
}

export default function CommandButtons({ onTakeoff, onLand }: CommandButtonsProps) {
  return (
    <div className="flex gap-4 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-xl p-3">
      <button
        onClick={onTakeoff}
        className="px-5 py-2.5 bg-green-600 hover:bg-green-700 active:bg-green-800 active:scale-95 text-white font-semibold rounded-lg shadow-md transition-all duration-150 ease-in-out border border-green-500/60 focus:outline-none"
      >
        Takeoff
      </button>
      <button
        onClick={onLand}
        className="px-5 py-2.5 bg-red-600 hover:bg-red-700 active:bg-red-800 active:scale-95 text-white font-semibold rounded-lg shadow-md transition-all duration-150 ease-in-out border border-red-500/60 focus:outline-none"
      >
        Land
      </button>
      {/* Example for a future button:
      <button
        // onClick={onToggleRecord}
        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 active:scale-95 text-white font-semibold rounded-lg shadow-md transition-all duration-150 ease-in-out border border-blue-500/60 focus:outline-none"
      >
        Record
      </button>
      */}
    </div>
  );
} 