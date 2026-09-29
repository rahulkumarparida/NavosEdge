import React from 'react';
import { MapPin, ArrowUpRight, BarChart3 } from 'lucide-react';

function getAqiColor(aqi) {
  if (aqi === null || aqi === undefined) return 'bg-slate-700';
  if (aqi <= 50) return 'bg-emerald-500';
  if (aqi <= 100) return 'bg-yellow-500';
  if (aqi <= 150) return 'bg-amber-500';
  if (aqi <= 200) return 'bg-orange-500';
  if (aqi <= 300) return 'bg-red-500';
  return 'bg-purple-500';
}

export function LocationComparison({ nodes }) {
  if (!nodes || nodes.length === 0) return null;

  // Sort nodes by AQI descending (highest pollution first)
  const sorted = [...nodes].sort((a, b) => (b.aqi ?? 0) - (a.aqi ?? 0));
  const maxAqi = Math.max(...sorted.map(n => n.aqi ?? 0), 200);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg mb-8 backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-cyan-400" />
            Location Air Quality Comparison
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time comparative pollution levels across all monitored geographic nodes
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {sorted.map((node, idx) => {
          const aqi = node.aqi ?? 0;
          const pct = Math.min(100, Math.max(5, (aqi / maxAqi) * 100));
          const colorClass = getAqiColor(node.aqi);

          return (
            <div key={node.node_id} className="bg-slate-950/50 p-4 rounded-lg border border-slate-800/60">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-slate-500 w-4">#{idx + 1}</span>
                  <div>
                    <span className="font-bold text-slate-200 text-sm">{node.location}</span>
                    <span className="text-xs text-slate-400 ml-2">({node.node_id})</span>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs">
                  <span className="text-slate-400">
                    PM2.5: <strong className="text-slate-200">{node.pm?.PM2_5 ?? 0} µg/m³</strong>
                  </span>
                  <span className="text-slate-400">
                    PM10: <strong className="text-slate-200">{node.pm?.PM10 ?? 0} µg/m³</strong>
                  </span>
                  <div className="flex items-baseline gap-1.5 ml-2">
                    <span className="text-xs text-slate-400">AQI</span>
                    <span className="text-base font-extrabold text-slate-100">{node.aqi ?? 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden flex items-center">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
                  style={{ width: `${pct}%` }}
                ></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
