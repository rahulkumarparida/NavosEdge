import React, { useState, useEffect } from 'react';
import { Network, Wifi, Globe, Check, AlertCircle, RefreshCw, Edit3, Save, X } from 'lucide-react';

export function IpConfigCard({ ipConfig, onConfigUpdated, initialEditNode = null }) {
  const [ip, setIp] = useState(ipConfig?.current_ip || '');
  const [port, setPort] = useState(ipConfig?.port || 8420);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);

  useEffect(() => {
    if (ipConfig?.current_ip) {
      setIp(ipConfig.current_ip);
    }
    if (ipConfig?.port) {
      setPort(ipConfig.port);
    }
  }, [ipConfig]);

  useEffect(() => {
    if (initialEditNode) {
      setIsEditing(true);
      if (initialEditNode.ip) {
        setIp(initialEditNode.ip);
      }
      if (initialEditNode.port) {
        setPort(initialEditNode.port);
      }
    }
  }, [initialEditNode]);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    if (!ip.trim()) {
      setStatusMessage({ type: 'error', text: 'Please enter a valid IP address or hostname.' });
      return;
    }

    setLoading(true);
    setStatusMessage(null);

    try {
      const endpoint = initialEditNode?.node_id
        ? `/api/v1/nodes/${encodeURIComponent(initialEditNode.node_id)}/ip`
        : '/api/v1/config/ip';

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip: ip.trim(),
          port: parseInt(port, 10) || 8420,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setStatusMessage({
          type: 'success',
          text: data.reachable
            ? `Successfully connected to ${data.current_ip}:${data.port}`
            : `Saved IP ${data.current_ip}:${data.port}. Node is currently offline / awaiting next poll.`,
        });
        if (onConfigUpdated) {
          onConfigUpdated(data);
        }
        setTimeout(() => {
          setIsEditing(false);
        }, 2000);
      } else {
        setStatusMessage({
          type: 'error',
          text: data.detail || 'Failed to update IP configuration.',
        });
      }
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: `Network error: ${err.message}`,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUseDetected = () => {
    if (ipConfig?.detected_local_ip) {
      setIp(ipConfig.detected_local_ip);
    }
  };

  const isConnected = ipConfig?.reachable || (ipConfig?.active_nodes && ipConfig.active_nodes > 0);
  const currentTarget = ipConfig?.base_url || (ipConfig?.current_ip ? `http://${ipConfig.current_ip}:${ipConfig.port || 8420}` : 'Not configured');

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 mb-8 shadow-lg">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Left Side: Summary & Status */}
        <div className="flex items-start sm:items-center gap-3.5">
          <div className="bg-cyan-500/10 p-2.5 rounded-xl border border-cyan-500/20 text-cyan-400 shrink-0">
            <Network className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100 tracking-wide">
                Edge Node IP Configuration
              </h3>
              <span
                className={`inline-flex items-center gap-1.5 text-[11px] px-2.5 py-0.5 rounded-full font-semibold border ${
                  isConnected
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`}></span>
                {isConnected ? 'Reachable' : 'Offline / Awaiting Node'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-400">
              <span>Target:</span>
              <code className="text-cyan-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 font-mono text-[11px]">
                {currentTarget}
              </code>
              {ipConfig?.detected_local_ip && (
                <span className="text-slate-500 hidden sm:inline">• Network IP: {ipConfig.detected_local_ip}</span>
              )}
            </div>
          </div>
        </div>

        {/* Right Side: Action Button */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          {!isEditing ? (
            <button
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/30 transition shadow-sm"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Change IP</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setIsEditing(false);
                setStatusMessage(null);
              }}
              className="p-1.5 text-slate-400 hover:text-slate-200 transition"
              title="Close edit form"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Expandable IP Edit Form */}
      {isEditing && (
        <form onSubmit={handleSave} className="mt-5 pt-4 border-t border-slate-800/80">
          {initialEditNode?.node_id && (
            <div className="mb-3 flex items-center justify-between bg-cyan-950/40 border border-cyan-800/50 px-3 py-1.5 rounded-lg text-xs">
              <span className="text-slate-300">
                Configuring IP for Node: <strong className="font-mono text-cyan-300 font-bold">{initialEditNode.node_id}</strong>
              </span>
              <button
                type="button"
                onClick={() => setIp(ipConfig?.detected_local_ip || '')}
                className="text-[11px] text-cyan-400 hover:text-cyan-200 underline font-medium"
              >
                Reset to local
              </button>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
            {/* IP Input */}
            <div className="sm:col-span-6">
              <label className="block text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                UNO Q / Edge IP Address
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={ip}
                  onChange={(e) => setIp(e.target.value)}
                  placeholder="e.g. 10.103.68.72 or 192.168.1.50"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Port Input */}
            <div className="sm:col-span-2">
              <label className="block text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Port
              </label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                placeholder="8420"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition"
                disabled={loading}
              />
            </div>

            {/* Action Buttons */}
            <div className="sm:col-span-4 flex items-center gap-2">
              <button
                type="submit"
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Connecting...</span>
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    <span>Save & Connect</span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                  setStatusMessage(null);
                }}
                disabled={loading}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
              >
                Cancel
              </button>
            </div>
          </div>

          {/* Quick Auto-Detect Helper */}
          {ipConfig?.detected_local_ip && (
            <div className="mt-2.5 flex items-center gap-2 text-[11px] text-slate-400">
              <Wifi className="w-3 h-3 text-cyan-400" />
              <span>Detected Network IP:</span>
              <button
                type="button"
                onClick={handleUseDetected}
                className="text-cyan-400 hover:text-cyan-300 underline font-mono font-semibold"
                title="Click to fill with auto-detected IP"
              >
                {ipConfig.detected_local_ip} (Click to use)
              </button>
            </div>
          )}

          {/* Status Feedback Message */}
          {statusMessage && (
            <div
              className={`mt-3 p-2.5 rounded-lg text-xs flex items-center gap-2 border ${
                statusMessage.type === 'success'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
              }`}
            >
              {statusMessage.type === 'success' ? (
                <Check className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              )}
              <span>{statusMessage.text}</span>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
