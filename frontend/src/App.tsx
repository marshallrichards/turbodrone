import { useControls } from './hooks/useControls';
import { VideoFeed } from './components/VideoFeed';
import ControlsOverlay from './components/ControlsOverlay';
import { PluginControls } from './components/PluginControls';
import { DrawingOverlay } from './components/DrawingOverlay';

function App() {
  const { axes, takeOff, land } = useControls();

  return (
    <div className="relative w-screen h-screen bg-black">
      <VideoFeed src="http://localhost:8000/mjpeg" />
      <DrawingOverlay />
      <ControlsOverlay axes={axes} onTakeoff={takeOff} onLand={land} />
      <PluginControls />
    </div>
  );
}

export default App;
