import { useState, useEffect } from 'react';

interface VideoFeedProps {
  src: string;
}

export function VideoFeed({ src }: VideoFeedProps) {
  const [isFeedAvailable, setIsFeedAvailable] = useState(true);

  // This effect resets the feed status if the source URL ever changes.
  useEffect(() => {
    setIsFeedAvailable(true);
  }, [src]);

  const handleError = () => {
    // This is triggered if the browser fails to load the image source.
    console.error("Video feed failed to load.");
    setIsFeedAvailable(false);
  };

  const handleLoad = () => {
    // This will be called once the first frame is successfully loaded.
    // If we were previously in an error state, this will recover the feed.
    setIsFeedAvailable(true);
  };

  return (
    <>
      {isFeedAvailable ? (
        <img
          src={src}
          alt="Drone video feed"
          className="absolute inset-0 w-full h-full object-contain"
          onError={handleError}
          onLoad={handleLoad}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-gray-400 text-2xl font-semibold">
            Video Feed Unavailable
          </p>
        </div>
      )}
    </>
  );
}