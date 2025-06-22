import React from "react";
import { WSClient } from "./lib/ws";
import { useControls } from "./hooks/useControls";
import { ControlSchemeToggle } from "./components/ControlSchemeToggle";
import VideoFeed from "./components/VideoFeed";
import ControlsOverlay from "./components/ControlsOverlay";
import { PluginControls } from './components/PluginControls';

const ws = new WSClient("ws://localhost:8000/ws");

export default function App() {
  const { axes, mode, setMode, gamepadConnected } = useControls(ws);

  const handleTakeoff = () => {
    ws.send({ type: "takeoff" });
  };

  const handleLand = () => {
    ws.send({ type: "land" });
  };

  return (
    <div className="relative min-h-screen bg-black text-white">
      <ControlSchemeToggle 
        mode={mode} 
        setMode={setMode} 
        gamepadConnected={gamepadConnected}
      />
      <VideoFeed />
      <ControlsOverlay axes={axes} onTakeoff={handleTakeoff} onLand={handleLand} />
      <PluginControls />
    </div>
  );
}
