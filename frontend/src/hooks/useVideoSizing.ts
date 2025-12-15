import { useState, useLayoutEffect, useCallback } from "react";

const ZERO_RECT = { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };

export function useVideoSizing() {
  const [videoRect, setVideoRect] = useState(ZERO_RECT);
  const [containerRect, setContainerRect] = useState(ZERO_RECT);

  const recalculate = useCallback(() => {
    const img = document.querySelector('img[alt="Drone video feed"]') as HTMLImageElement;
    if (!img || !img.parentElement) return;
    if (img.naturalWidth === 0 || img.naturalHeight === 0) return;

    const container = img.parentElement;
    if (container.clientWidth === 0 || container.clientHeight === 0) return;
    const containerAR = container.clientWidth / container.clientHeight;
    const videoAR = img.naturalWidth / img.naturalHeight;

    let newWidth, newHeight, newX, newY;

    if (containerAR > videoAR) {
      // Container is wider than video (letterboxed)
      newHeight = container.clientHeight;
      newWidth = newHeight * videoAR;
      newX = (container.clientWidth - newWidth) / 2;
      newY = 0;
    } else {
      // Container is taller than video (pillarboxed)
      newWidth = container.clientWidth;
      newHeight = newWidth / videoAR;
      newY = (container.clientHeight - newHeight) / 2;
      newX = 0;
    }
    
    setVideoRect({
      x: newX,
      y: newY,
      width: newWidth,
      height: newHeight,
      top: newY,
      left: newX,
      right: newX + newWidth,
      bottom: newY + newHeight,
    });
    setContainerRect(container.getBoundingClientRect());
  }, []);

  useLayoutEffect(() => {
    const img = document.querySelector('img[alt="Drone video feed"]') as HTMLImageElement;
    if (!img) return;

    const ro = new ResizeObserver(recalculate);
    ro.observe(img.parentElement!);

    img.addEventListener('load', recalculate);
    
    // Initial calculation in case image is already loaded
    if (img.complete && img.naturalWidth > 0) {
      recalculate();
    }

    return () => {
      ro.disconnect();
      img.removeEventListener('load', recalculate);
    };
  }, [recalculate]);

  return { videoRect, containerRect };
}
