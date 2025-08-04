export function VideoFeed({ src }: { src: string }) {
  return (
    <img
      src={src}
      alt="Drone video feed"
      className="absolute inset-0 w-full h-full object-contain"
    />
  );
}
