import React, { useEffect, useState } from 'react';
import {
  X,
  ShieldAlert,
  Cpu,
  Bell,
  Clock,
  CheckCircle2,
  AlertTriangle,
  CheckSquare,
} from 'lucide-react';
import { apiFetch } from '../../api/emergencyApi';

export function IncidentDetailModal({ eventId, onClose, onUpdated }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState('');
  const [actionBusy, setActionBusy] = useState(false);

  const loadDetail = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch(`/api/v1/emergency/events/${encodeURIComponent(eventId)}`);
      setDetail(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (eventId) loadDetail();
  }, [eventId]);

  const handleAcknowledge = async () => {
    setActionBusy(true);
    try {
      await apiFetch(`/api/v1/emergency/events/${encodeURIComponent(eventId)}/acknowledge`, {
        method: 'POST',
        body: JSON.stringify({ notes: notes || null }),
      });
      await loadDetail();
      if (onUpdated) onUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleResolve = async () => {
    if (!window.confirm('Manually mark this emergency incident as RESOLVED?')) return;
    setActionBusy(true);
    try {
      await apiFetch(`/api/v1/emergency/events/${encodeURIComponent(eventId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ notes: notes || null }),
      });
      await loadDetail();
      if (onUpdated) onUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  if (!eventId) return null;

  const ev = detail?.event;
  const supp = ev?.supporting_measurements || {};

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="sticky top-0 bg-slate-900/95 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            <div>
              <h3 className="text-base font-bold text-slate-100">
                Incident Detail — {eventId}
              </h3>
              {ev && (
                <p className="text-xs text-slate-400">
                  {ev.event_type} • Severity: {ev.severity} • Status: {ev.event_status}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {loading && <p className="text-sm text-slate-400">Loading incident details...</p>}
          {error && (
            <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs">
              {error}
            </div>
          )}

          {detail && ev && (
            <>
              {/* Environmental Information */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-3">
                  Environmental Information & AI/ML Evidence
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block">PM1.0</span>
                    <span className="font-mono text-slate-100">
                      {supp.pm1_0 != null ? `${Number(supp.pm1_0).toFixed(1)} µg/m³` : 'Unavailable'}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block">PM2.5</span>
                    <span className="font-mono text-slate-100">
                      {supp.pm2_5 != null ? `${Number(supp.pm2_5).toFixed(1)} µg/m³` : 'Unavailable'}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block">PM10</span>
                    <span className="font-mono text-slate-100">
                      {supp.pm10 != null ? `${Number(supp.pm10).toFixed(1)} µg/m³` : 'Unavailable'}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block">Gas Speciation</span>
                    <span className="font-mono text-amber-300">
                      {supp.gas_identity_candidate || 'UNESTABLISHED'}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-slate-300">
                  <span className="text-slate-400">Detection Reason:</span>{' '}
                  {ev.decision_reason || 'N/A'}
                </p>
              </div>

              {/* System Response: Recommended vs Confirmed Execution */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 mb-3 flex items-center gap-2">
                  <Cpu className="w-4 h-4" /> System Response (Recommended vs. Confirmed State)
                </h4>
                <div className="text-xs space-y-2">
                  <div>
                    <span className="text-slate-400">Policy Recommended Actions:</span>{' '}
                    <span className="text-slate-200 font-mono">
                      {(ev.recommended_actions || []).join(', ') || 'NONE'}
                    </span>
                  </div>
                  {detail.actuators?.length === 0 ? (
                    <p className="text-slate-400">No ESP32 actuator registered for this node.</p>
                  ) : (
                    <div className="space-y-2 mt-2">
                      {detail.actuators.map((act) => (
                        <div
                          key={act.actuator_id}
                          className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-2"
                        >
                          <div>
                            <span className="font-semibold text-slate-200">{act.device_name}</span>{' '}
                            <span className="text-slate-400 font-mono">({act.actuator_type})</span>
                          </div>
                          <div className="flex items-center gap-2 font-mono text-[11px]">
                            <span
                              className={`px-2 py-0.5 rounded ${
                                act.connection_status === 'ONLINE'
                                  ? 'bg-emerald-500/15 text-emerald-300'
                                  : 'bg-rose-500/15 text-rose-300'
                              }`}
                            >
                              {act.connection_status}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200">
                              Reported Output: {act.current_state}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {detail.command_logs?.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <span className="text-slate-400 block">Command History:</span>
                      {detail.command_logs.map((c) => (
                        <div key={c.command_id} className="text-[11px] font-mono text-slate-300 bg-slate-900/80 px-2.5 py-1.5 rounded">
                          {c.command_id}: {c.command} → [{c.execution_status}] {c.error_details ? `— ${c.error_details}` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Notifications & Escalation */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-400 mb-3 flex items-center gap-2">
                  <Bell className="w-4 h-4" /> Caregiver Notifications & Escalation (Level {detail.escalation?.current_level})
                </h4>
                {detail.escalation?.all_contacts_exhausted && (
                  <div className="mb-3 p-2.5 rounded-lg bg-rose-950/60 border border-rose-700 text-rose-200 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    All registered caregiver contacts have been exhausted without human acknowledgement.
                  </div>
                )}
                {detail.notifications?.length === 0 ? (
                  <p className="text-xs text-slate-400">No caregiver notifications dispatched for this incident.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="py-1.5 pr-3">Recipient</th>
                          <th className="py-1.5 pr-3">Channel</th>
                          <th className="py-1.5 pr-3">Delivery</th>
                          <th className="py-1.5 pr-3">Human Ack</th>
                          <th className="py-1.5">Provider Note</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/70">
                        {detail.notifications.map((n) => (
                          <tr key={n.notification_id}>
                            <td className="py-2 pr-3 text-slate-200">
                              {n.contact_name || n.contact_id} (P{n.contact_priority ?? '?'})
                            </td>
                            <td className="py-2 pr-3 font-mono">{n.notification_channel}</td>
                            <td className="py-2 pr-3 font-mono">{n.delivery_status}</td>
                            <td className="py-2 pr-3 font-mono">
                              <span
                                className={
                                  n.acknowledgement_status === 'ACKNOWLEDGED'
                                    ? 'text-emerald-400'
                                    : 'text-amber-400'
                                }
                              >
                                {n.acknowledgement_status}
                              </span>
                            </td>
                            <td className="py-2 text-slate-400">{n.failure_reason || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Chronological Timeline */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3 flex items-center gap-2">
                  <Clock className="w-4 h-4" /> Chronological Incident Timeline
                </h4>
                <div className="space-y-2">
                  {(detail.timeline || []).map((item, idx) => (
                    <div key={idx} className="flex items-start gap-3 text-xs border-l-2 border-slate-700 pl-3">
                      <span className="font-mono text-[11px] text-slate-500 shrink-0">
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      <div>
                        <p className="font-semibold text-slate-200">{item.title}</p>
                        <p className="text-slate-400">{item.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Manual Operator Actions */}
              {ev.event_status !== 'RESOLVED' && (
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                  <label className="block text-xs text-slate-400">
                    Operator Notes (attributed to current operator)
                  </label>
                  <input
                    type="text"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="e.g. Called caregiver, resident confirmed safe"
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100"
                  />
                  <div className="flex flex-wrap gap-3">
                    {ev.event_status !== 'ACKNOWLEDGED' && (
                      <button
                        disabled={actionBusy}
                        onClick={handleAcknowledge}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition"
                      >
                        <CheckSquare className="w-4 h-4" /> Acknowledge Incident
                      </button>
                    )}
                    <button
                      disabled={actionBusy}
                      onClick={handleResolve}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition"
                    >
                      <CheckCircle2 className="w-4 h-4" /> Manually Resolve Incident
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

