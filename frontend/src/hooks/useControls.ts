import { useCallback, useEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────── */
/*  Shared types                                               */
export type ControlMode = "inc" | "abs" | "mouse";

export interface Axes {
  throttle: number;  // -1 … +1  (down / up)
  yaw:      number;  // -1 … +1  (left / right)
  pitch:    number;  // -1 … +1  (back / fwd)
  roll:     number;  // -1 … +1  (left / right)
}
/* ─────────────────────────────────────────────────────────── */

export function useControls() {
  /* ------- state refs (mutable) ------- */
  const axesRef = useRef<Axes>({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });
  const modeRef = useRef<ControlMode>("inc");

  /* ------- NEW: websocket ref & lifecycle ------- */
  const ws = useRef<WebSocket | null>(null);
  
  /* ------- Plugin state (event-driven) ------- */
  const pluginRunningRef = useRef<boolean>(false);
  const suppressNeutralTxRef = useRef<boolean>(true);     // gate 0,0,0,0 when plugin active
  const stoppedPluginOnceRef = useRef<boolean>(false);    // rate-limit stop calls per burst

  // Open WS once on mount, close on unmount
  useEffect(() => {
    ws.current = new WebSocket("ws://localhost:8000/ws");
    return () => {
      ws.current?.close();
      ws.current = null;
    };
  }, []);

  // Listen for plugin start/stop events (dispatched from usePlugins and auto-stop)
  useEffect(() => {
    const onStart = () => { pluginRunningRef.current = true; };
    const onStop  = () => { pluginRunningRef.current = false; stoppedPluginOnceRef.current = false; };
    window.addEventListener('plugin:running', onStart as EventListener);
    window.addEventListener('plugin:stopped', onStop as EventListener);
    return () => {
      window.removeEventListener('plugin:running', onStart as EventListener);
      window.removeEventListener('plugin:stopped', onStop as EventListener);
    };
  }, []);

  /* ------- state that triggers re-renders ------- */
  const [axes,  setAxes]  = useState<Axes>(axesRef.current);
  const [mode,  setModeSt] = useState<ControlMode>("inc");
  const [gamepadConnected, setGamepadConnected] = useState<boolean>(false);

  // Track previous gamepad status to avoid spam
  const prevGamepadStatus = useRef<boolean>(false);

  /* make setMode update both the ref (for hooks) and the state (for UI) */
  const setMode = useCallback((m: ControlMode) => {
    modeRef.current = m;
    setModeSt(m);
  }, []);

  /* --------------- gamepad detection --------------- */
  useEffect(() => {
    const checkGamepad = () => {
      const gamepads = navigator.getGamepads();
      const hasGamepad = Array.from(gamepads).some(gp => gp !== null && gp.connected);
      
      // Only log when status changes
      if (hasGamepad !== prevGamepadStatus.current) {
        console.log(`Gamepad ${hasGamepad ? 'connected' : 'disconnected'}`);
        if (hasGamepad) {
          const connectedGamepads = Array.from(gamepads).filter(gp => gp !== null);
          console.log('Connected gamepads:', connectedGamepads.map(gp => gp?.id));
        }
        prevGamepadStatus.current = hasGamepad;
      }
      
      setGamepadConnected(hasGamepad);
    };

    // Check initially
    checkGamepad();

    // Listen for gamepad connect/disconnect events
    const handleGamepadConnected = () => checkGamepad();
    const handleGamepadDisconnected = () => checkGamepad();

    window.addEventListener('gamepadconnected', handleGamepadConnected);
    window.addEventListener('gamepaddisconnected', handleGamepadDisconnected);

    // Also poll periodically since some browsers don't fire events reliably
    const pollInterval = setInterval(checkGamepad, 1000);

    return () => {
      window.removeEventListener('gamepadconnected', handleGamepadConnected);
      window.removeEventListener('gamepaddisconnected', handleGamepadDisconnected);
      clearInterval(pollInterval);
    };
  }, []);

  /* --------------- keyboard (incremental) --------------- */
  useEffect(() => {
    if (modeRef.current !== "inc") return;           // ignore when in abs mode

    const map: Record<string, { axis: keyof Axes; dir: -1 | 1 }> = {
      w:          { axis: "pitch",    dir: +1 },
      s:          { axis: "pitch",    dir: -1 },
      a:          { axis: "roll",     dir: -1 },
      d:          { axis: "roll",     dir: +1 },
      ArrowUp:    { axis: "throttle", dir: +1 },
      ArrowDown:  { axis: "throttle", dir: -1 },
      ArrowLeft:  { axis: "yaw",      dir: -1 },
      ArrowRight: { axis: "yaw",      dir: +1 },
    };

    const down = (e: KeyboardEvent) => {
      const m = map[e.key];
      if (!m) return;
      axesRef.current[m.axis] = m.dir;
      setAxes({ ...axesRef.current });

      // If any plugin is running and user provides input → stop plugin once
      maybeStopPluginOnUserInput();
    };

    const up = (e: KeyboardEvent) => {
      const m = map[e.key];
      if (!m) return;
      if (axesRef.current[m.axis] === m.dir) {
        axesRef.current[m.axis] = 0;
        setAxes({ ...axesRef.current });
      }
    };

    window.addEventListener("keydown", down);
    window.addEventListener("keyup",   up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup",   up);
    };
  }, [mode]);      // re-run effect when mode flips

  /* --------------- Xbox-360 game-pad (absolute) --------- */
  useEffect(() => {
    if (modeRef.current !== "abs") return;          // ignore when in inc mode

    const DEADZONE = 0.15; // Adjust this value as needed
    let raf = 0;

    const applyDeadzone = (value: number): number => {
      return Math.abs(value) < DEADZONE ? 0 : value;
    };

    const poll = () => {
      const gp = navigator.getGamepads()[0] as Gamepad | null;
      if (gp) {
        /* Xbox-360 / Chrome mapping -------------------------------------
           Left  stick: axes[0] (X)  axes[1] (Y)
           Right stick: axes[2] (X)  axes[3] (Y)
           Positive Y is *down*  → invert for throttle / pitch
        ------------------------------------------------------------------*/
        axesRef.current.roll     = applyDeadzone(gp.axes[0]);     // left X
        axesRef.current.pitch    = applyDeadzone(-gp.axes[1]);    // left Y  (forward == -1)
        axesRef.current.yaw      = applyDeadzone(gp.axes[2]);     // right X
        axesRef.current.throttle = applyDeadzone(-gp.axes[3]);    // right Y (up == +1)
        setAxes({ ...axesRef.current });

        // Stop plugin when the first non-zero user sticks are detected
        if (Math.abs(axesRef.current.roll) > 0 || Math.abs(axesRef.current.pitch) > 0 ||
            Math.abs(axesRef.current.yaw)  > 0 || Math.abs(axesRef.current.throttle) > 0) {
          maybeStopPluginOnUserInput();
        }
      }
      raf = requestAnimationFrame(poll);
    };
    raf = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(raf);
  }, [mode]);

  /* ---------- TrackPoint / Mouse (relative) ------------------ */
  useEffect(() => {
    if (modeRef.current !== "mouse") return;

    const sensitivity = 0.015;      // tune to taste for TrackPoint
    const decay       = 0.90;       // spring-back to centre when idle
    let rafId = 0;

    /* convert mouse deltas → roll / pitch  (-y = pitch forward) */
    const onMove = (e: MouseEvent) => {
      axesRef.current.roll  = Math.max(-1, Math.min(1, axesRef.current.roll  +  e.movementX * sensitivity));
      axesRef.current.pitch = Math.max(-1, Math.min(1, axesRef.current.pitch - e.movementY * sensitivity));
      setAxes({ ...axesRef.current });
    };

    /* gentle recentre so sticks don't stay deflected forever */
    const tick = () => {
      axesRef.current.roll  *= decay;
      axesRef.current.pitch *= decay;
      if (Math.abs(axesRef.current.roll)  < 0.001) axesRef.current.roll  = 0;
      if (Math.abs(axesRef.current.pitch) < 0.001) axesRef.current.pitch = 0;
      setAxes({ ...axesRef.current });
      rafId = requestAnimationFrame(tick);
    };

    /* when we lose pointer-lock (Esc, window blur, etc.) fall back to keyboard */
    const onLockChange = () => {
      if (document.pointerLockElement === null) {
        setMode("inc");
      }
    };

    window.addEventListener("mousemove",        onMove);
    document.addEventListener("pointerlockchange", onLockChange);
    rafId = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("pointerlockchange", onLockChange);
      cancelAnimationFrame(rafId);
      axesRef.current.roll = axesRef.current.pitch = 0;
      setAxes({ ...axesRef.current });
    };
  }, [mode, setMode]);

  /* ----------- network TX 30 Hz (treat mouse as "abs") ------- */
  useEffect(() => {
    const interval = setInterval(() => {
      if (ws.current?.readyState !== WebSocket.OPEN) return;

      // Suppress neutral transmissions when any plugin is running
      const allZero = axesRef.current.throttle === 0 && axesRef.current.yaw === 0 &&
                      axesRef.current.pitch === 0 && axesRef.current.roll === 0;
      if (suppressNeutralTxRef.current && pluginRunningRef.current && allZero) return;

      ws.current.send(JSON.stringify({
        type: "axes",
        mode: modeRef.current,
        ...axesRef.current,
      }));
    }, 1000 / 30);
    return () => clearInterval(interval);
  }, []);

  /* ------------- helpers / commands ------------------------- */
  const sendCommand = (type: string, payload = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, ...payload }));
    } else {
      console.warn("Cannot send command, WebSocket not open.");
    }
  };

  const maybeStopPluginOnUserInput = async () => {
    if (!pluginRunningRef.current || stoppedPluginOnceRef.current) return;
    try {
      // Stop all running plugins for simplicity
      const res = await fetch("http://localhost:8000/plugins");
      if (!res.ok) return;
      const data = await res.json();
      const running: string[] = data?.running ?? [];
      await Promise.all(running.map((name) => fetch(`http://localhost:8000/plugins/${name}/stop`, { method: 'POST' })));
      stoppedPluginOnceRef.current = true;
      pluginRunningRef.current = false;
      // notify UI to flip OFF without polling
      window.dispatchEvent(new CustomEvent('plugin:stopped'));
    } catch {}
  };

  const takeOff = () => sendCommand("takeoff");
  const land    = () => sendCommand("land");

  /* ------------- hook return ------------------------------- */
  return {
    axes,
    mode,
    setMode,
    gamepadConnected,
    takeOff,
    land,
  };
}
