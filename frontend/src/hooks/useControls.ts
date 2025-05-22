import { useEffect, useRef } from "react";
import { WSClient } from "../lib/ws";

interface Axes { throttle: number; yaw: number; pitch: number; roll: number; }

export function useControls(ws: WSClient) {
  const axes = useRef<Axes>({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });

  // ---------- keyboard ----------
  useEffect(() => {
    const map: Record<string, keyof Axes> = {
      w: "pitch", s: "pitch", a: "roll", d: "roll",
      ArrowUp: "throttle", ArrowDown: "throttle",
      ArrowLeft: "yaw", ArrowRight: "yaw",
    };
    function handler(e: KeyboardEvent, dir: number) {
      const key = map[e.key];
      if (!key) return;
      axes.current[key] = dir;
    }
    const down = (e: KeyboardEvent) => handler(e, +1);
    const up   = (e: KeyboardEvent) => handler(e, 0);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup",   up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);

  // ---------- gamepad ----------
  useEffect(() => {
    let rafId = 0;
    const poll = () => {
      const gp = navigator.getGamepads()[0];
      if (gp) {
        // typical game controller mapping
        axes.current.roll     =  gp.axes[0];           // left stick X
        axes.current.pitch    = -gp.axes[1];           // left stick Y inverted
        axes.current.yaw      =  gp.axes[2];           // right stick X
        axes.current.throttle = -gp.axes[3];           // right stick Y inverted
      }
      rafId = requestAnimationFrame(poll);
    };
    rafId = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(rafId);
  }, []);

  // ---------- send at 30 Hz ----------
  useEffect(() => {
    const id = setInterval(() => {
      ws.send({ type: "axes", ...axes.current });
    }, 1000 / 30);
    return () => clearInterval(id);
  }, [ws]);
}
