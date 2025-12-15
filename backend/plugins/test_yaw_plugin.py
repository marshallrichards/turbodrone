import threading
import time
import os

from .base import Plugin
from control.strategies import DirectStrategy


class TestYawPlugin(Plugin):
    """
    Simple plugin to apply a small absolute yaw deflection using DirectStrategy
    for a short, fixed duration. Intended for isolating yaw behaviour on S2x.

    Behaviour:
    - Switch model to DirectStrategy (do NOT change expo)
    - Apply yaw = TEST_YAW_PCT (default +0.30), others 0
    - Maintain for TEST_YAW_DURATION_S seconds (default 5s) or until stopped
    - Then stop sending and restore previous strategy
    """

    def _on_start(self):
        # Read tunables from environment
        try:
            self._yaw_pct = float(os.getenv("TEST_YAW_PCT", "0.30"))
        except Exception:
            self._yaw_pct = 0.30
        try:
            self._duration_s = float(os.getenv("TEST_YAW_DURATION_S", "5.0"))
        except Exception:
            self._duration_s = 5.0

        # Remember previous strategy to restore on stop
        self._prev_strategy = getattr(self.fc.model, "strategy", None)

        # Force DirectStrategy for absolute mapping; keep expo as-is
        try:
            self.fc.model.set_strategy(DirectStrategy())
            print(f"[TestYawPlugin] Using DirectStrategy, yaw={self._yaw_pct:+.2f} for {self._duration_s:.1f}s")
        except Exception as e:
            print(f"[TestYawPlugin] Failed to set DirectStrategy: {e}")

        # Start worker thread
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _on_stop(self):
        # Stop worker
        if hasattr(self, "_thread") and self._thread:
            # Let the run loop exit naturally by checking self.running.
            # If stop() is called from inside the worker thread (auto-stop),
            # do NOT join ourselves.
            try:
                if threading.current_thread() is not self._thread:
                    self._thread.join(timeout=1.0)
            except RuntimeError:
                # Defensive: joining current thread raises at runtime.
                pass

        # Send zeros once
        try:
            self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
        except Exception:
            pass

        # Restore previous strategy
        try:
            if hasattr(self, "_prev_strategy") and self._prev_strategy is not None:
                self.fc.model.set_strategy(self._prev_strategy)
        except Exception:
            pass

    def _run(self):
        start = time.time()
        # Send commands at ~30 Hz; FC loop will sample the latest values
        interval = 1.0 / 30.0

        while self.running:
            now = time.time()
            elapsed = now - start
            if elapsed >= self._duration_s:
                # Auto-stop after duration
                try:
                    print("[TestYawPlugin] Duration elapsed; stopping")
                finally:
                    # Route through stop() so _on_stop() runs (zeros + restore strategy)
                    self.stop()
                    return

            # Apply yaw deflection only
            try:
                self.fc.set_axes_from("test_yaw", throttle=0.0, yaw=self._yaw_pct, pitch=0.0, roll=0.0)
            except Exception:
                pass

            time.sleep(interval)


