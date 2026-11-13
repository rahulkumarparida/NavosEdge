import React, { useEffect, useState } from 'react';
import { Bell, PhoneCall, RefreshCw, RotateCcw, Send } from 'lucide-react';
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
  const [integrationStatus, setIntegrationStatus] = useState(null);
  const [testOpen, setTestOpen] = useState(false);
  const [testPhone, setTestPhone] = useState('');
  const [testSecondaryPhone, setTestSecondaryPhone] = useState('');
  const [testNote, setTestNote] = useState('');
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const loadNotifications = async () => {
    try {
      let query = '';
      if (filter.startsWith('DELIVERY:')) {
        query = `?delivery_status=${encodeURIComponent(filter.replace('DELIVERY:', ''))}`;
      } else if (filter.startsWith('ACK:')) {
        query = `?acknowledgement_status=${encodeURIComponent(filter.replace('ACK:', ''))}`;
      }
      const [data, statusData] = await Promise.all([
        apiFetch(`/api/v1/emergency/notifications${query}`),
        apiFetch('/api/v1/notifications/status').catch(() => null),
      ]);
      setNotifications(data || []);
      if (statusData) setIntegrationStatus(statusData);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadNotifications();
  }, [filter]);

  const handleRunTestWorkflow = async (e) => {
    e.preventDefault();
    setTestBusy(true);
    setTestResult(null);
    setError('');
    try {
      const body = {
        track_in_db: true,
        custom_message: testNote.trim() || undefined,
      };
      if (testPhone.trim()) body.phone_number = testPhone.trim();
      if (testSecondaryPhone.trim()) body.secondary_phone_number = testSecondaryPhone.trim();
      const res = await apiFetch('/api/v1/notifications/test-workflow', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setTestResult(res);
      await loadNotifications();
    } catch (err) {
      setError(err.message);
    } finally {
      setTestBusy(false);
    }
  };

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
            {integrationStatus && (
              <span
                className={`ml-1 px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                  integrationStatus.is_simulated
                    ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                    : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                }`}
              >
                {integrationStatus.mode}
                {integrationStatus.trial_mode ? ' · TRIAL' : ''} · {integrationStatus.dispatch_mode}
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-400">
            Delivery receipts and human acknowledgements are tracked independently
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setTestOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-xs text-cyan-300 font-semibold"
          >
            <PhoneCall className="w-3.5 h-3.5" /> Test Twilio Workflow
          </button>
          <button
            onClick={loadNotifications}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-cyan-300"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </div>

      {testOpen && (
        <form
          onSubmit={handleRunTestWorkflow}
          className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold text-slate-200">
              End-to-End Twilio Test Workflow (SMS + Automated Voice DTMF Call)
            </div>
            {integrationStatus && (
              <span className="text-[11px] text-slate-400">
                Mode: <strong className="text-slate-200">{integrationStatus.mode}</strong>
                {integrationStatus.is_simulated
                  ? ' (no external Twilio charges)'
                  : ' (live Twilio dispatch)'}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
            <input
              type="text"
              value={testPhone}
              onChange={(e) => setTestPhone(e.target.value)}
              placeholder={
                integrationStatus?.test_recipient_configured
                  ? 'Primary E.164 (optional: uses NAVOS_TWILIO_TEST_RECIPIENT)'
                  : 'Primary Recipient E.164 (e.g. +919876543210)'
              }
              className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
            />
            <input
              type="text"
              value={testSecondaryPhone}
              onChange={(e) => setTestSecondaryPhone(e.target.value)}
              placeholder="Secondary Escalation E.164 (optional)"
              className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
            />
            <input
              type="text"
              value={testNote}
              onChange={(e) => setTestNote(e.target.value)}
              placeholder="Optional verification note"
              className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] text-slate-400">
              Uses an isolated virtual test node so ESP32 alert hardware on UNO Q is not triggered.
            </p>
            <button
              type="submit"
              disabled={testBusy}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-500 text-slate-950 text-xs font-bold hover:bg-cyan-400 disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              {testBusy ? 'Dispatching...' : 'Trigger Test Workflow'}
            </button>
          </div>
          {testResult && (
            <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 text-[11px] text-slate-300 font-mono">
              Event {testResult.event_id} · Mode={testResult.mode} · Dispatch={testResult.dispatch_mode} · Dispatched={testResult.notifications?.length ?? 0} channel(s)
            </div>
          )}
        </form>
      )}

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

