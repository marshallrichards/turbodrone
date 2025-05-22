
export default function VideoFeed() {
  return (
    <div className="w-full h-auto">
      <img
        src="http://localhost:8000/mjpeg"
        className="object-contain mx-auto"
        alt="drone video"
      />
    </div>
  );
}