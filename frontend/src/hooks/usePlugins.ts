import { useState, useEffect, useCallback } from 'react';

// Assuming your backend runs on port 8000
const API_BASE_URL = 'http://localhost:8000';

interface PluginState {
  available: string[];
  running: string[];
}

export function usePlugins() {
  const [pluginsEnabled, setPluginsEnabled] = useState<boolean>(false);
  const [availablePlugins, setAvailablePlugins] = useState<string[]>([]);
  const [runningPlugins, setRunningPlugins] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Function to fetch the current state of plugins from the backend
  const fetchPluginState = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/plugins`);
      if (!response.ok) {
        // Backend returns 404 when plugins are disabled.
        if (response.status === 404) {
          setPluginsEnabled(false);
          setAvailablePlugins([]);
          setRunningPlugins(new Set());
          setError(null);
          return;
        }
        throw new Error('Failed to fetch plugin status');
      }
      setPluginsEnabled(true);
      const data: PluginState = await response.json();
      setAvailablePlugins(data.available);
      setRunningPlugins(new Set(data.running));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'An unknown error occurred');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Function to toggle a plugin on or off
  const togglePlugin = useCallback(async (name: string) => {
    if (!pluginsEnabled) return;
    const isRunning = runningPlugins.has(name);
    const endpoint = isRunning ? 'stop' : 'start';

    try {
      const response = await fetch(`${API_BASE_URL}/plugins/${name}/${endpoint}`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Failed to ${endpoint} plugin ${name}`);
      }
      // After toggling, refresh the state to ensure UI is in sync
      await fetchPluginState();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'An unknown error occurred');
    }
  }, [pluginsEnabled, runningPlugins, fetchPluginState]);

  // Fetch the initial state when the hook is first used
  useEffect(() => {
    fetchPluginState();
    return () => {};
  }, [fetchPluginState]);

  // Keep UI in sync when other parts of the app start/stop plugins
  useEffect(() => {
    const handler = () => { fetchPluginState(); };
    window.addEventListener('plugin:running', handler as EventListener);
    window.addEventListener('plugin:stopped', handler as EventListener);
    return () => {
      window.removeEventListener('plugin:running', handler as EventListener);
      window.removeEventListener('plugin:stopped', handler as EventListener);
    };
  }, [fetchPluginState]);

  return {
    pluginsEnabled,
    availablePlugins,
    runningPlugins,
    isLoading,
    error,
    togglePlugin,
  };
} 