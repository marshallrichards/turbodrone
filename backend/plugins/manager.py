import importlib
import inspect
import pkgutil
import queue
import threading
from typing import Dict, Iterator, Type
from services.flight_controller import FlightController
from .base import Plugin

class PluginManager:
    def __init__(self,
                 flight_controller: FlightController,
                 frame_queue: queue.Queue,
                 overlay_queue: queue.Queue):
        self._fc      = flight_controller
        self._frames_q  = frame_queue
        self._overlay_q = overlay_queue
        self._registry: Dict[str, Type[Plugin]] = {}
        self._pool: Dict[str, Plugin] = {}
        self._frame_stop_events: Dict[str, threading.Event] = {}
        self._discover_plugins()

    def available(self) -> list[str]:
        return list(self._registry.keys())

    def running(self) -> list[str]:
        return list(self._pool.keys())

    def clear_overlays(self) -> None:
        """
        Clears any currently displayed overlays (frontend will render none).
        """
        if not self._overlay_q:
            return
        try:
            self._overlay_q.put_nowait([])
        except Exception:
            pass

    def start(self, name: str) -> bool:
        """
        Starts a plugin by name.

        Returns True if started, False if already running.
        Raises ValueError if the plugin is unknown.
        """
        if name not in self._registry:
            raise ValueError(f"Unknown plugin: {name}")
        if name in self._pool:
            return False
        
        print(f"[PluginManager] Starting plugin: {name}")
        cls = self._registry[name]

        stop_event = threading.Event()
        self._frame_stop_events[name] = stop_event

        def frame_iterator() -> Iterator:
            """
            Yield frames from the shared queue, but remain stoppable.

            Important: do NOT block indefinitely on Queue.get() or plugin threads
            consuming this iterator can hang forever during shutdown.
            """
            while not stop_event.is_set():
                try:
                    # Keep the block bounded so we can observe stop_event.
                    yield self._frames_q.get(timeout=0.2)
                except queue.Empty:
                    continue

        try:
            # Pass a new, unique generator instance and the overlay queue to the plugin
            inst = cls(name=name,
                       flight_controller=self._fc,
                       frame_source=frame_iterator(),
                       overlay_queue=self._overlay_q)
            inst.start()
            self._pool[name] = inst
            return True
        except Exception as e:
            print(f"[PluginManager] Error starting plugin {name}: {e}")
            # Ensure we don't leak stop events on failed startup.
            self._frame_stop_events.pop(name, None)
            raise

    def stop(self, name: str) -> bool:
        """
        Stops a plugin by name.

        Returns True if stopped, False if it wasn't running.
        Raises ValueError if the plugin is unknown.
        """
        if name not in self._registry:
            raise ValueError(f"Unknown plugin: {name}")

        inst = self._pool.pop(name, None)
        if not inst:
            return False

        print(f"[PluginManager] Stopping plugin: {name}")

        # Unblock any plugin thread currently waiting on the frame iterator.
        stop_evt = self._frame_stop_events.pop(name, None)
        if stop_evt:
            stop_evt.set()

        inst.stop()

        # If we just stopped the last plugin, clear overlays so stale UI doesn't linger.
        if not self._pool:
            self.clear_overlays()
        return True

    def stop_all(self):
        for name in list(self._pool.keys()):
            self.stop(name)

    def _discover_plugins(self):
        """Finds all Plugin subclasses in the 'plugins' package."""
        import plugins
        
        plugin_pkg_path = plugins.__path__
        plugin_pkg_name = plugins.__name__

        for _, mod_name, _ in pkgutil.walk_packages(path=plugin_pkg_path, prefix=f"{plugin_pkg_name}."):
            module = importlib.import_module(mod_name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                # Ensure it's a direct subclass of Plugin and not Plugin itself
                if issubclass(obj, Plugin) and obj is not Plugin:
                    self._registry[obj.__name__] = obj
                    print(f"[PluginManager] Discovered plugin: {obj.__name__}") 