import { WSClient } from "./lib/ws";
import { useControls } from "./hooks/useControls";
import VideoFeed from "./components/VideoFeed";
import ControlsOverlay from "./components/ControlsOverlay";

export default function App() {
  const ws = new WSClient();
  const axes = useControls(ws);      // <- now returns live axes

  return (
    <div className="relative min-h-screen bg-black text-white">
      <VideoFeed />
      <ControlsOverlay axes={axes} />
    </div>
  );
}
