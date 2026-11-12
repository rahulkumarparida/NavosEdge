import React, { useEffect, useState } from 'react';
import {
  ShieldAlert,
  Bell,
  Cpu,
  Radio,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  Eye,
} from 'lucide-react';
import { apiFetch } from '../../api/emergencyApi';
import { IncidentDetailModal } from './IncidentDetailModal';

const SEVERITY_BADGE = {
  EMERGENCY: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  CRITICAL: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  HIGH: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  WARNING: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  MEDIUM: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  LOW: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  NORMAL: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
};

export function EmergencyPanel() {
  const [overview, setOverview] = useState(null);
  const [events, setEvents] = useState([]);
  const [sseLive, setSseLive] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [error, setError] = useState('');
  const [simBusy, setSimBusy] = useState(false);
  const [simNote, setSimNote] = useState('');

  const refreshData = async () => {
    try {
      const [ov, evs] = await Promise.all([
        apiFetch('/api/v1/emergency/overview'),
        apiFetch('/api/v1/emergency/events'),
      ]);
      setOverview(ov);
      setEvents(evs || []);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    refreshData();

    let es = null;
    let reconnectTimer = null;

    const connectSse = () => {
      try {
        es = new EventSource('/api/v1/emergency/stream');
        es.onopen = () => setSseLive(true);
        es.addEventListener('emergency_update', (e) => {
          try {
            const payload = JSON.parse(e.data);
            if (payload.overview) setOverview(payload.overview);
            if (payload.events) setEvents(payload.events);
          } catch (_) {}
        });
        es.onerror = () => {
          setSseLive(false);
          if (es) es.close();
          reconnectTimer = setTimeout(connectSse, 4000);
        };
      } catch (_) {
        setSseLive(false);
      }
    };

    connectSse();
    return () => {
      if (es) es.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, []);

  const handleSimulateDemo = async () => {
    setSimBusy(true);
    setSimNote('');
    try {
      const res = await apiFetch('/api/v1/emergency/demo/simulate-event', {
        method: 'POST',
        body: JSON.stringify({
          node_id: 'node-01',
          pm2_5: 195.0,
          pm10: 280.0,
        }),
      });
      setSimNote(
        `Synthetic Demo Event (${res.provider_mode}): Event ${res.decision?.active_event_id || 'created'} • ${res.notifications_dispatched?.length || 0} simulated notification(s) queued.`
      );
      await refreshData();
    } catch (err) {
      setError(`Synthetic demo failed: ${err.message}`);
    } finally {
      setSimBusy(false);
    }
  };

  const statCards = [
    {
      label: 'Active Emergencies',
      value: overview?.active_emergency_count ?? '—',
      accent: 'text-rose-400',
      icon: ShieldAlert,
    },
    {
      label: 'Critical / Emergency',
      value: overview?.critical_emergency_count ?? '—',
      accent: 'text-rose-300',
      icon: AlertTriangle,
    },
    {
      label: 'Warning Events',
      value: overview?.warning_count ?? '—',
      accent: 'text-amber-400',
      icon: AlertTriangle,
    },
    {
      label: 'Unacknowledged',
      value: overview?.unacknowledged_count ?? '—',
      accent: 'text-amber-300',
      icon: Bell,
    },
    {
      label: 'Escalation In Progress',
      value: overview?.escalation_in_progress_count ?? '—',
      accent: 'text-orange-400',
      icon: Bell,
    },
    {
      label: 'UNO Q Nodes (On / Off)',
      value: overview ? `${overview.online_nodes} / ${overview.offline_nodes}` : '—',
      accent: 'text-cyan-400',
      icon: Radio,
    },
    {
      label: 'ESP32 Actuators (On / Off)',
      value: overview ? `${overview.online_actuators} / ${overview.offline_actuators}` : '—',
      accent: 'text-emerald-400',
      icon: Cpu,
    },
    {
      label: 'Pending Notifications',
      value: overview?.pending_caregiver_notifications ?? '—',
      accent: 'text-amber-300',
      icon: Bell,
    },
    {
      label: 'Recently Resolved',
      value: overview?.recently_resolved_count ?? '—',
      accent: 'text-emerald-400',
      icon: CheckCircle2,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header & SSE + Synthetic Demo */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            Emergency Overview & Live Incidents
          </h2>
          <p className="text-xs text-slate-400">
            Real-time Phase 2 hazard decisions, Phase 3 actuator state, and Phase 4 caregiver escalation
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
              sseLive
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            }`}
          >
            <Radio className={`w-3.5 h-3.5 ${sseLive ? 'animate-pulse' : ''}`} />
            {sseLive ? 'Emergency SSE Live' : 'Reconnecting SSE'}
          </span>

          <button
            disabled={simBusy}
            onClick={handleSimulateDemo}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold transition"
            title="Runs a clearly-labeled synthetic pollution event in SIMULATED mode"
          >
            <PlayCircle className="w-4 h-4" />
            {simBusy ? 'Simulating...' : 'Run Synthetic Demo Event'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs">
          {error}
        </div>
      )}
      {simNote && (
        <div className="p-3 rounded-lg bg-cyan-950/50 border border-cyan-800 text-cyan-200 text-xs">
          {simNote}
        </div>
      )}

      {/* Overview Stat Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {statCards.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.label}
              className="bg-slate-900/70 border border-slate-800 rounded-xl p-3.5"
            >
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span>{c.label}</span>
                <Icon className={`w-4 h-4 ${c.accent}`} />
              </div>
              <div className={`text-xl font-black ${c.accent}`}>{c.value}</div>
            </div>
          );
        })}
      </div>

      {/* Live Emergency Event Panel */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100">
            Emergency Incidents ({events.length})
          </h3>
          <button
            onClick={refreshData}
            className="text-xs text-cyan-400 hover:text-cyan-300"
          >
            Refresh
          </button>
        </div>

        {events.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No emergency events recorded. System is monitoring normally.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-4">Event ID</th>
                  <th className="py-2.5 px-3">Node / Resident</th>
                  <th className="py-2.5 px-3">Hazard</th>
                  <th className="py-2.5 px-3">Severity</th>
                  <th className="py-2.5 px-3">PM2.5 / PM10</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Esc. Level</th>
                  <th className="py-2.5 px-3">Detected</th>
                  <th className="py-2.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {events.map((ev) => {
                  const supp = ev.supporting_measurements || {};
                  const badge =
                    SEVERITY_BADGE[ev.severity] ||
                    'bg-slate-800 text-slate-300 border-slate-700';
                  return (
                    <tr key={ev.event_id} className="hover:bg-slate-800/40">
                      <td className="py-2.5 px-4 font-mono text-cyan-300">{ev.event_id}</td>
                      <td className="py-2.5 px-3">
                        <span className="font-mono text-slate-200">{ev.associated_node_id}</span>
                        {ev.resident_id && (
                          <span className="block text-[11px] text-slate-400">
                            Resident: {ev.resident_id}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-200">{ev.event_type}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded border text-[11px] font-bold ${badge}`}>
                          {ev.severity}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-300">
                        {supp.pm2_5 != null ? `${Number(supp.pm2_5).toFixed(1)}` : '—'} /{' '}
                        {supp.pm10 != null ? `${Number(supp.pm10).toFixed(1)}` : '—'}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-200">{ev.event_status}</td>
                      <td className="py-2.5 px-3 font-mono text-amber-300">L{ev.escalation_level}</td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {new Date(ev.detected_at).toLocaleString()}
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <button
                          onClick={() => setSelectedEventId(ev.event_id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 text-[11px] font-semibold"
                        >
                          <Eye className="w-3.5 h-3.5" /> Detail
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedEventId && (
        <IncidentDetailModal
          eventId={selectedEventId}
          onClose={() => setSelectedEventId(null)}
          onUpdated={refreshData}
        />
      )}
    </div>
  );
}

