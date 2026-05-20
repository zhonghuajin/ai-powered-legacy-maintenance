import CallTreeVisualizer from './CallTreeVisualizer';

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Global Navigation Bar */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-slate-900 text-white shadow-lg">
        <div className="mx-auto max-w-screen-2xl px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500">
                <span className="text-lg font-bold">RT</span>
              </div>
              <div>
                <h1 className="font-bold text-lg">Runtime Context Visualizer</h1>
                <p className="text-xs text-slate-400">Runtime Context Visualization Toolset</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area - Add top spacing for navigation bar */}
      <div className="pt-16">
        <CallTreeVisualizer />
      </div>
    </div>
  );
}