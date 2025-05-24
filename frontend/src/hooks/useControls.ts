import { useEffect, useRef, useState } from "react";
import { WSClient } from "../lib/ws";

/* ──────────────────────────────────────────────────────────────────────────── */
/*  Small shared type (local to the file – export it if other modules need it) */
export interface Axes {
  throttle: number;  // -1 … +1  (down / up)
  yaw:      number;  // -1 … +1  (left / right)
  pitch:    number;  // -1 … +1  (back / fwd)
  roll:     number;  // -1 … +1  (left / right)
}
/* ──────────────────────────────────────────────────────────────────────────── */

export function useControls(ws: WSClient): Axes {
  const axesRef = useRef<Axes>({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });
  const [axes, setAxes] = useState<Axes>(axesRef.current);   // <- observable

  /* --------------- keyboard --------------- */
  useEffect(() => {
    // map key ➜ axis + signed direction
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
    };

    const up = (e: KeyboardEvent) => {
      const m = map[e.key];
      if (!m) return;
      // only reset if the key that just lifted is the one that set the dir
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
  }, []);

  /* --------------- game-pad --------------- */
  useEffect(() => {
    let raf = 0;
    const poll = () => {
      const gp = navigator.getGamepads()[0];
      if (gp) {
        axesRef.current.roll     =  gp.axes[0];   // left X
        axesRef.current.pitch    = -gp.axes[1];   // left Y (invert)
        axesRef.current.yaw      =  gp.axes[2];   // right X
        axesRef.current.throttle = -gp.axes[3];   // right Y (invert)
        setAxes({ ...axesRef.current });
      }
      raf = requestAnimationFrame(poll);
    };
    raf = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(raf);
  }, []);

  /* --------------- network TX 30 Hz --------------- */
  useEffect(() => {
    const id = setInterval(() => {
      ws.send({ type: "axes", ...axesRef.current });
    }, 1000 / 30);
    return () => clearInterval(id);
  }, [ws]);

  return axes;
}
