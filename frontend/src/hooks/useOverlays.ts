import { useState, useEffect, useRef } from 'react';

const OVERLAY_WS_URL = 'ws://localhost:8000/ws/overlays';

export interface OverlayObject {
  type: 'rect';
  coords: [number, number, number, number]; // [x1, y1, x2, y2]
  color: string;
}

export function useOverlays() {
  const [overlays, setOverlays] = useState<OverlayObject[]>([]);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    ws.current = new WebSocket(OVERLAY_WS_URL);
    
    ws.current.onopen = () => console.log('Overlay WebSocket connected');
    ws.current.onclose = () => console.log('Overlay WebSocket disconnected');
    ws.current.onerror = (err) => console.error('Overlay WebSocket error:', err);

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data)) {
          setOverlays(data);
        }
      } catch (e) {
        console.error('Failed to parse overlay data:', e);
      }
    };

    return () => {
      ws.current?.close();
    };
  }, []);

  return overlays;
} 