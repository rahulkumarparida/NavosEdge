import React, { useEffect, useState } from 'react';
import { Cpu, Radio, ShieldAlert, Play, Square, AlertOctagon } from 'lucide-react';
import { apiFetch } from '../../api/emergencyApi';

export function ActuatorsPanel() {
  const [nodes, setNodes] = useState([]);
  const [actuators, setActuators] = useState([]);
  const [commandHistory, setCommandHistory] = useState({});
  const [error, setError] = useState('');
  const [statusNote, setStatusNote] = useState('');

  const loadDevices = async () => {
    try {
      const [nodeList, actList] = await Promise.all([
        apiFetch('/api/v1/emergency/nodes'),
        apiFetch('/api/v1/actuators'),
      ]);
      setNodes(nodeList || []);
      setActuators(actList || []);

      const historyMap = {};
      await Promise.all(
        (actList || []).map(async (act) => {
          try {
            const cmds = await apiFetch(
              `/api/v1/actuators/${encodeURIComponent(act.actuator_id)}/commands`
            );
            historyMap[act.actuator_id] = cmds || [];
          } catch (_) {
            historyMap[act.actuator_id] = [];
          }
        })
      );
      setCommandHistory(historyMap);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadDevices();
  }, []);

  const handleManualCommand = async (actuator, command) => {
    const isTurnOn = command === 'FAN_ON' || command === 'LIGHT_ON';
    if (isTurnOn) {
      const safetyNote =
        actuator.actuator_type === 'ESP32_ALERT_LIGHT'
          ? 'This will drive GPIO25 HIGH on the ESP32 alert light LED circuit until cleared or stopped.'
          : 'Note: Unfiltered 5V fans are NEVER air purifiers, and GPIO25 remains hardware-locked LOW if PHYSICAL_DRIVER_VERIFIED=false.';
      const confirmed = window.confirm(
        `EXPLICIT DEMO CONFIRMATION REQUIRED:\n\nSend ${command} in DEMO_MODE to ${actuator.actuator_id} (${actuator.actuator_type})?\n\n${safetyNote}`
      );
      if (!confirmed) return;
    }

    setStatusNote('');
    setError('');
    try {
      const res = await apiFetch(
        `/api/v1/actuators/${encodeURIComponent(actuator.actuator_id)}/command`,
        {
          method: 'POST',
          body: JSON.stringify({
            command,
            control_mode: 'DEMO_MODE',
            reason: 'Manager Dashboard explicit operator test',
          }),
        }
      );
      const ackStatus = res.acknowledgement?.status || res.command_log?.execution_status || 'SENT';
      const outState = res.acknowledgement?.output_state || res.actuator?.current_state || 'UNKNOWN';
      setStatusNote(
        `Command ${command} -> ${actuator.actuator_id}: Dispatched=${res.dispatched}, Ack=${ackStatus}, Reported Output=${outState}`
      );
      await loadDevices();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            Registered UNO Q Nodes & ESP32 Actuators
          </h2>
          <p className="text-xs text-slate-400">
            Explicitly distinguishes connection state, command receipt, execution, and hardware safety lock
          </p>
        </div>
        <button
          onClick={loadDevices}
          className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-cyan-300 hover:border-slate-700"
        >
          Refresh Devices
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs">
          {error}
        </div>
      )}
      {statusNote && (
        <div className="p-3 rounded-lg bg-cyan-950/50 border border-cyan-800 text-cyan-200 text-xs">
          {statusNote}
        </div>
      )}

      {/* UNO Q Nodes */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
        <h3 className="text-sm font-bold text-slate-100 mb-3 flex items-center gap-2">
          <Radio className="w-4 h-4 text-cyan-400" /> Registered UNO Q Nodes ({nodes.length})
        </h3>
        {nodes.length === 0 ? (
          <p className="text-xs text-slate-400">No UNO Q nodes registered in EmergencyDatabase.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {nodes.map((n) => (
              <div key={n.node_id} className="bg-slate-950/60 border border-slate-800 rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">{n.node_id}</span>
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-mono text-[10px]">
                    {n.runtime_status || n.operational_status}
                  </span>
                </div>
                <div className="text-slate-300">{n.node_name} — {n.location}</div>
                <div className="text-slate-400">Resident: {n.resident_id || 'Unassigned'}</div>
                <div className="text-slate-500 text-[11px]">
                  Last telemetry: {n.last_seen ? new Date(n.last_seen).toLocaleString() : 'N/A'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ESP32 Actuators */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
        <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-emerald-400" /> ESP32 Wireless Actuators ({actuators.length})
        </h3>
        {actuators.length === 0 ? (
          <p className="text-xs text-slate-400">No ESP32 actuators registered yet.</p>
        ) : (
          actuators.map((act) => {
            const cmds = commandHistory[act.actuator_id] || [];
            const lastCmd = cmds[0];
            const isAlertLight = act.actuator_type === 'ESP32_ALERT_LIGHT';
            const isUnfiltered = act.actuator_type === 'ESP32_FAN_5V_UNFILTERED';
            const onCommand = isAlertLight ? 'LIGHT_ON' : 'FAN_ON';
            const offCommand = isAlertLight ? 'LIGHT_OFF' : 'FAN_OFF';
            return (
              <div key={act.actuator_id} className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-bold text-slate-100">
                      {act.device_name}{' '}
                      <span className="font-mono text-xs text-cyan-300">({act.actuator_id})</span>
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      Node: {act.associated_node_id} • Type: {act.actuator_type} • IP: {act.ip_address || 'Unknown'}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span
                      className={`px-2.5 py-1 rounded-full border ${
                        act.connection_status === 'ONLINE'
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                      }`}
                    >
                      {act.connection_status === 'ONLINE' ? 'Connected' : 'Disconnected'}
                    </span>
                    <span className="px-2.5 py-1 rounded-full bg-slate-800 text-slate-200 border border-slate-700">
                      Output State: {act.current_state}
                    </span>
                  </div>
                </div>

                {isUnfiltered && (
                  <div className="p-2.5 rounded-lg bg-amber-950/40 border border-amber-700/50 text-amber-200 text-xs flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 shrink-0" />
                    Unfiltered 5V fan — blocked from automated activation in real Protection Mode (not an air purifier).
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-slate-400 block">Last Heartbeat</span>
                    <span className="font-mono text-slate-200">
                      {act.last_heartbeat ? new Date(act.last_heartbeat).toLocaleString() : 'Never'}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-slate-400 block">Last Command</span>
                    <span className="font-mono text-slate-200">
                      {lastCmd ? `${lastCmd.command} (${lastCmd.command_id})` : 'None'}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-slate-400 block">Command Ack / Status</span>
                    <span className="font-mono text-slate-200">
                      {lastCmd ? lastCmd.execution_status : 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    onClick={() => handleManualCommand(act, onCommand)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold"
                  >
                    <Play className="w-3.5 h-3.5" /> Test {onCommand} (Demo Mode)
                  </button>
                  <button
                    onClick={() => handleManualCommand(act, offCommand)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold"
                  >
                    <Square className="w-3.5 h-3.5" /> {offCommand}
                  </button>
                  <button
                    onClick={() => handleManualCommand(act, 'EMERGENCY_STOP')}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-300 text-xs font-semibold"
                  >
                    <AlertOctagon className="w-3.5 h-3.5" /> EMERGENCY_STOP
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

