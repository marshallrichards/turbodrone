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
    // This function attempts to connect.
    const connect = () => {
      ws.current = new WebSocket(OVERLAY_WS_URL);
      
      ws.current.onopen = () => console.log('%c[Overlays] WebSocket Connected', 'color: green');
      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // --- ⭑⭑⭑ DEBUG LOG ⭑⭑⭑ ---
          console.log('[Overlays] Received data:', data); 
          if (Array.isArray(data)) {
            setOverlays(data);
          }
        } catch (e) {
          console.error('[Overlays] Failed to parse data:', e);
        }
      };

      ws.current.onclose = () => {
        console.log('%c[Overlays] WebSocket Disconnected. Reconnecting...', 'color: orange');
        // Automatically try to reconnect after a delay.
        setTimeout(connect, 3000); 
      };

      ws.current.onerror = (err) => {
        console.error('%c[Overlays] WebSocket Error', 'color: red', err);
        // Ensure the socket is closed before the next reconnect attempt.
        ws.current?.close();
      };
    };

    connect();

    // Cleanup function to run when the component unmounts.
    return () => {
      if (ws.current) {
        // Prevent the onclose handler from firing the reconnect logic
        // when we are intentionally closing the connection.
        ws.current.onclose = null; 
        ws.current.close();
      }
    };
  }, []); // Empty dependency array ensures this runs only once per component mount.

  return overlays;
} 