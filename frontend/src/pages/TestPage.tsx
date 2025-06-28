import StaticDrawingOverlay from "../components/StaticDrawingOverlay";
import { VideoFeed } from "../components/VideoFeed";

export default function TestPage() {
  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center bg-gray-900">
      <h1 className="text-2xl font-bold text-white mb-4">
        Static Video Feed (640×480)
      </h1>
      <div
        className="relative border-2 border-dashed border-gray-600"
        style={{ width: 640, height: 480 }}
      >
        <VideoFeed src="http://localhost:8000/mjpeg" />
        <StaticDrawingOverlay />
      </div>
    </div>
  );
} 