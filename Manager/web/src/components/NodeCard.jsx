import React from 'react';
import { MapPin, Cpu, ShieldAlert, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';

function getAqiBadge(aqi) {
  if (aqi === null || aqi === undefined) return { label: 'N/A', color: 'bg-slate-700 text-slate-300 border-slate-600' };
  if (aqi <= 50) return { label: 'Good', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' };
  if (aqi <= 100) return { label: 'Moderate', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40' };
  if (aqi <= 150) return { label: 'Unhealthy for Sensitive', color: 'bg-amber-500/20 text-amber-400 border-amber-500/40' };
  if (aqi <= 200) return { label: 'Unhealthy', color: 'bg-orange-500/20 text-orange-400 border-orange-500/40' };
  if (aqi <= 300) return { label: 'Very Unhealthy', color: 'bg-red-500/20 text-red-400 border-red-500/40' };
  return { label: 'Hazardous', color: 'bg-purple-500/20 text-purple-400 border-purple-500/40' };
}

export function NodeCard({ node }) {
  const isActive = node.status === 'active';
  const aqiValue = node.aqi ?? node.AQI ?? null;
  const aqiBadge = getAqiBadge(aqiValue);
  const displayAqi = typeof aqiValue === 'number' ? Math.round(aqiValue * 10) / 10 : (aqiValue ?? 'N/A');
  const confidencePct = node.source_confidence != null ? Math.round(node.source_confidence * 100) : null;

  const pm25 = node.pm?.PM2_5 ?? node.pm?.pm2_5 ?? node.pm?.['PM2.5'] ?? node.pm?.pm25 ?? node.PM2_5 ?? 0;
  const pm10 = node.pm?.PM10 ?? node.pm?.pm10 ?? node.PM10 ?? 0;
  const pm1_0 = node.pm?.PM1_0 ?? node.pm?.pm1_0 ?? node.pm?.['PM1.0'] ?? node.pm?.pm1 ?? node.PM1_0 ?? 0;
  const temp = node.temperature_C ?? node.temperature ?? 0;
  const hum = node.humidity_pct ?? node.humidity ?? 0;

  const advisory = node.advisory || {};
  const advisorySeverity = advisory.severity || 'NORMAL';
  const adviceText = advisory.advice || advisory.summary || 'Environmental levels within nominal thresholds.';

  return (
    <div className={`rounded-xl border transition-all duration-300 shadow-lg ${
      isActive
        ? 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
        : 'bg-slate-950/60 border-slate-900/80 opacity-75 grayscale-[20%]'
    }`}>
      {/* Header */}
      <div className="p-5 border-b border-slate-800/80 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <h3 className="font-bold text-lg text-slate-100 tracking-wide">{node.node_id}</h3>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-1">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
            <span>{node.location}</span>
          </div>
        </div>

        {/* Status Badge */}
        <div className="flex flex-col items-end gap-1.5">
          <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-semibold border ${
            isActive
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`}></span>
            {isActive ? 'ACTIVE' : 'INACTIVE'}
          </span>
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>{node.last_updated_seconds_ago ?? 0}s ago</span>
          </div>
        </div>
      </div>

      {/* Main Body */}
      <div className="p-5 space-y-4">
        {/* AQI & Primary Telemetry */}
        <div className="grid grid-cols-2 gap-3 bg-slate-950/50 p-3.5 rounded-lg border border-slate-800/60">
          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">AQI Index</div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-slate-100">{displayAqi}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${aqiBadge.color}`}>
                {aqiBadge.label}
              </span>
            </div>
          </div>

          <div className="space-y-1 text-xs justify-center flex flex-col">
            <div className="flex justify-between text-slate-300">
              <span className="text-slate-400">PM2.5:</span>
              <span className="font-semibold text-slate-200">{pm25} µg/m³</span>
            </div>
            <div className="flex justify-between text-slate-300">
              <span className="text-slate-400">PM10:</span>
              <span className="font-semibold text-slate-200">{pm10} µg/m³</span>
            </div>
            <div className="flex justify-between text-slate-300">
              <span className="text-slate-400">PM1.0:</span>
              <span className="font-semibold text-slate-200">{pm1_0} µg/m³</span>
            </div>
          </div>
        </div>

        {/* Environmental Indicators */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/40 flex justify-between items-center">
            <span className="text-slate-400">Temperature</span>
            <span className="font-bold text-slate-200">{temp}°C</span>
          </div>
          <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/40 flex justify-between items-center">
            <span className="text-slate-400">Humidity</span>
            <span className="font-bold text-slate-200">{hum}%</span>
          </div>
        </div>

        {/* Source Classification */}
        <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800/40 flex justify-between items-center text-xs">
          <div>
            <span className="text-slate-400 block text-[11px] font-medium">Source Classifier</span>
            <span className="font-semibold text-cyan-300 text-sm capitalize">{node.source_prediction || 'Unknown'}</span>
          </div>
          {confidencePct !== null && (
            <div className="text-right">
              <span className="text-slate-400 block text-[11px]">Confidence</span>
              <span className="font-bold text-slate-200">{confidencePct}%</span>
            </div>
          )}
        </div>

        {/* Advisory Box */}
        <div className={`p-3 rounded-lg border text-xs ${
          advisorySeverity === 'HIGH' || advisorySeverity === 'WARNING'
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
            : advisorySeverity === 'CRITICAL'
            ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
            : 'bg-slate-950/40 border-slate-800/40 text-slate-300'
        }`}>
          <div className="flex items-center gap-1.5 font-semibold mb-1 text-[11px] uppercase tracking-wider">
            {advisorySeverity !== 'NORMAL' ? (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            )}
            <span>Advisory ({advisorySeverity})</span>
          </div>
          <p className="text-slate-300 leading-relaxed text-[11px]">{adviceText}</p>
        </div>
      </div>
    </div>
  );
}
