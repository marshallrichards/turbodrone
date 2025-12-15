import { usePlugins } from '../hooks/usePlugins';

export function PluginControls() {
  const { pluginsEnabled, availablePlugins, runningPlugins, isLoading, error, togglePlugin } = usePlugins();

  // Feature-flagged off by backend (PLUGINS_ENABLED=false)
  if (!pluginsEnabled && !isLoading) {
    return null;
  }

  if (isLoading) {
    return <div className="text-white">Loading plugins...</div>;
  }

  if (error) {
    return <div className="text-red-500">Error: {error}</div>;
  }

  return (
    <div className="absolute bottom-4 right-4 bg-gray-800 bg-opacity-70 p-4 rounded-lg shadow-lg text-white">
      <h3 className="text-lg font-bold mb-2">Plugins</h3>
      {availablePlugins.length === 0 ? (
        <p className="text-sm">No plugins available.</p>
      ) : (
        <ul className="space-y-2">
          {availablePlugins.map((name) => {
            const isRunning = runningPlugins.has(name);
            return (
              <li key={name} className="flex items-center justify-between">
                <span className="mr-4">{name}</span>
                <button
                  onClick={async () => {
                    await togglePlugin(name);
                    // Dispatch events so other hooks (e.g. controls) know without polling
                    const running = runningPlugins.has(name);
                    window.dispatchEvent(new CustomEvent(running ? 'plugin:stopped' : 'plugin:running'));
                  }}
                  className={`px-4 py-1 rounded-full text-sm font-semibold transition-colors
                    ${isRunning
                      ? 'bg-green-500 hover:bg-green-600'
                      : 'bg-red-500 hover:bg-red-600'
                    }`}
                >
                  {isRunning ? 'ON' : 'OFF'}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
} 