import React from 'react';
import { Activity, Wind, Cloud, Thermometer, Droplets, Server } from 'lucide-react';

function getAqiBadge(aqi) {
  if (aqi === null || aqi === undefined) return { label: 'N/A', color: 'bg-slate-700 text-slate-300' };
  if (aqi <= 50) return { label: 'Good', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' };
  if (aqi <= 100) return { label: 'Moderate', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40' };
  if (aqi <= 150) return { label: 'Unhealthy for Sensitive', color: 'bg-amber-500/20 text-amber-400 border-amber-500/40' };
  if (aqi <= 200) return { label: 'Unhealthy', color: 'bg-orange-500/20 text-orange-400 border-orange-500/40' };
  if (aqi <= 300) return { label: 'Very Unhealthy', color: 'bg-red-500/20 text-red-400 border-red-500/40' };
  return { label: 'Hazardous', color: 'bg-purple-500/20 text-purple-400 border-purple-500/40' };
}

export function OverviewCards({ data }) {
  const overall = data?.overall || {};
  const activeCount = data?.active_nodes ?? 0;
  const inactiveCount = data?.inactive_nodes ?? 0;
  const totalCount = data?.total_nodes ?? 0;

  const aqiBadge = getAqiBadge(overall.aqi);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4 mb-8">
      {/* Active Nodes Card */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Active Nodes</span>
          <Server className="w-4 h-4 text-cyan-400" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-slate-5">{activeCount}</span>
          <span className="text-xs text-slate-400">/ {totalCount} total</span>
        </div>
        <div className="mt-2 text-xs text-slate-400 flex gap-2">
          <span className="text-emerald-400">{activeCount} active</span>
          <span>•</span>
          <span className={inactiveCount > 0 ? "text-amber-400 font-semibold" : "text-slate-500"}>{inactiveCount} inactive</span>
        </div>
      </div>

      {/* Overall AQI Card */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Overall AQI</span>
          <Activity className="w-4 h-4 text-amber-400" />
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-3xl font-bold text-slate-5">{overall.aqi ?? 'N/A'}</span>
          <span className={`text-xs px-2 py-0.5 rounded border ${aqiBadge.color}`}>
            {aqiBadge.label}
          </span>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Regional max active node index</p>
      </div>

      {/* Overall PM2.5 */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Overall PM2.5</span>
          <Wind className="w-4 h-4 text-sky-400" />
        </div>
        <div className="text-3xl font-bold text-slate-5">
          {overall.PM2_5 ?? 0.0} <span className="text-xs font-normal text-slate-400">µg/m³</span>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Active average</p>
      </div>

      {/* Overall PM10 */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Overall PM10</span>
          <Cloud className="w-4 h-4 text-indigo-400" />
        </div>
        <div className="text-3xl font-bold text-slate-5">
          {overall.PM10 ?? 0.0} <span className="text-xs font-normal text-slate-400">µg/m³</span>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Active average</p>
      </div>

      {/* Avg Temp */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Avg Temperature</span>
          <Thermometer className="w-4 h-4 text-rose-400" />
        </div>
        <div className="text-3xl font-bold text-slate-5">
          {overall.temperature_C ?? 0.0}<span className="text-xl font-normal text-slate-400">°C</span>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Active average</p>
      </div>

      {/* Avg Humidity */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <span>Avg Humidity</span>
          <Droplets className="w-4 h-4 text-teal-400" />
        </div>
        <div className="text-3xl font-bold text-slate-5">
          {overall.humidity_pct ?? 0.0}<span className="text-xl font-normal text-slate-400">%</span>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Active average</p>
      </div>
    </div>
  );
}
