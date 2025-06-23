import importlib
import inspect
import pkgutil
import queue
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
        self._discover_plugins()

    def available(self) -> list[str]:
        return list(self._registry.keys())

    def running(self) -> list[str]:
        return list(self._pool.keys())

    def start(self, name: str):
        if name in self._pool or name not in self._registry:
            return
        
        print(f"[PluginManager] Starting plugin: {name}")
        cls = self._registry[name]

        def frame_iterator():
            while True:
                # This will block until a frame is available in the queue
                yield self._frames_q.get()

        try:
            # Pass a new, unique generator instance and the overlay queue to the plugin
            inst = cls(name=name,
                       flight_controller=self._fc,
                       frame_source=frame_iterator(),
                       overlay_queue=self._overlay_q)
            inst.start()
            self._pool[name] = inst
        except Exception as e:
            print(f"[PluginManager] Error starting plugin {name}: {e}")

    def stop(self, name: str):
        inst = self._pool.pop(name, None)
        if inst:
            print(f"[PluginManager] Stopping plugin: {name}")
            inst.stop()

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