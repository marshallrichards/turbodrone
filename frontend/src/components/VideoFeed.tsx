export default function VideoFeed() {
  return (
    <img
      src="http://localhost:8000/mjpeg"
      className="absolute inset-0 w-full h-full object-contain select-none bg-black"
      alt="drone video feed"
    />
  );
}