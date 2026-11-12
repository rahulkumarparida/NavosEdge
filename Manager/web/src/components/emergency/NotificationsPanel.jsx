import React, { useEffect, useState } from 'react';
import { Bell, RefreshCw, RotateCcw } from 'lucide-react';
import { apiFetch } from '../../api/emergencyApi';

const FILTER_OPTIONS = [
  { label: 'All', value: 'ALL' },
  { label: 'Pending', value: 'DELIVERY:QUEUED' },
  { label: 'Sent', value: 'DELIVERY:SENT' },
  { label: 'Delivered', value: 'DELIVERY:DELIVERED' },
  { label: 'Failed', value: 'DELIVERY:FAILED' },
  { label: 'Acknowledged', value: 'ACK:ACKNOWLEDGED' },
  { label: 'Unacknowledged', value: 'ACK:PENDING' },
];

export function NotificationsPanel() {
  const [notifications, setNotifications] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);

  const loadNotifications = async () => {
    try {
      let query = '';
      if (filter.startsWith('DELIVERY:')) {
        query = `?delivery_status=${encodeURIComponent(filter.replace('DELIVERY:', ''))}`;
      } else if (filter.startsWith('ACK:')) {
        query = `?acknowledgement_status=${encodeURIComponent(filter.replace('ACK:', ''))}`;
      }
      const data = await apiFetch(`/api/v1/emergency/notifications${query}`);
      setNotifications(data || []);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadNotifications();
  }, [filter]);

  const handleRetry = async (notificationId) => {
    setBusyId(notificationId);
    try {
      await apiFetch(
        `/api/v1/emergency/notifications/${encodeURIComponent(notificationId)}/retry`,
        { method: 'POST' }
      );
      await loadNotifications();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-400" />
            Notification Centre & Escalation Log
          </h2>
          <p className="text-xs text-slate-400">
            Delivery receipts and human acknowledgements are tracked independently
          </p>
        </div>

        <button
          onClick={loadNotifications}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-cyan-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`px-3 py-1 rounded-full text-xs font-semibold border transition ${
              filter === opt.value
                ? 'bg-cyan-500 text-slate-950 border-cyan-400'
                : 'bg-slate-900 text-slate-300 border-slate-800 hover:border-slate-700'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs">
          {error}
        </div>
      )}

      <div className="bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden">
        {notifications.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No notifications match the selected filter.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-4">Notification ID</th>
                  <th className="py-2.5 px-3">Event / Resident</th>
                  <th className="py-2.5 px-3">Recipient</th>
                  <th className="py-2.5 px-3">Channel</th>
                  <th className="py-2.5 px-3">Delivery</th>
                  <th className="py-2.5 px-3">Human Ack</th>
                  <th className="py-2.5 px-3">Esc.</th>
                  <th className="py-2.5 px-3">Error</th>
                  <th className="py-2.5 px-4 text-right">Retry</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {notifications.map((n) => (
                  <tr key={n.notification_id} className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-4 font-mono text-cyan-300">{n.notification_id}</td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-slate-200">{n.event_id}</span>
                      {n.resident_name && (
                        <span className="block text-[11px] text-slate-400">{n.resident_name}</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-slate-200">{n.recipient_name || n.contact_id}</td>
                    <td className="py-2.5 px-3 font-mono">{n.notification_channel}</td>
                    <td className="py-2.5 px-3 font-mono">{n.delivery_status}</td>
                    <td className="py-2.5 px-3 font-mono">
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
                    <td className="py-2.5 px-3 font-mono">L{n.escalation_level}</td>
                    <td className="py-2.5 px-3 text-rose-300">{n.failure_reason || '—'}</td>
                    <td className="py-2.5 px-4 text-right">
                      {(n.delivery_status === 'FAILED' || n.delivery_status === 'UNDELIVERED') && (
                        <button
                          disabled={busyId === n.notification_id}
                          onClick={() => handleRetry(n.notification_id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-[11px]"
                        >
                          <RotateCcw className="w-3 h-3" /> Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

