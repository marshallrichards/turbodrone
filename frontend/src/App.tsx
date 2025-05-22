import { WSClient } from "./lib/ws";
import { useControls } from "./hooks/useControls";
import VideoFeed from "./components/VideoFeed";

function App() {
  const ws = new WSClient();
  useControls(ws);

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col gap-4 p-4">
      <h1 className="text-2xl font-bold">Turbodrone Web Client</h1>
      <VideoFeed />
      <p className="opacity-70">
        Control with: WASD / arrow keys or gamepad controller.  q to quit video window (desktop build).
      </p>
    </div>
  );
}

export default App;
