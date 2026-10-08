import React, { useEffect, useState } from 'react';
import { OverviewCards } from './components/OverviewCard';
import { NodeCard } from './components/NodeCard';
import { LocationComparison } from './components/LocationComparison';
import { IpConfigCard } from './components/IpConfigCard';
import { Activity, Radio, RefreshCw, Layers, Globe } from 'lucide-react';

export default function App() {
  const [data, setData] = useState({
    active_nodes: 0,
    inactive_nodes: 0,
    total_nodes: 0,
    overall: {},
    nodes: []
  });

  const [ipConfig, setIpConfig] = useState({
    current_ip: '',
    port: 8420,
    base_url: '',
    detected_local_ip: '',
    poll_enabled: true,
    poll_interval_s: 36.0,
    reachable: false,
    active_nodes: 0,
  });

  const [editTargetNode, setEditTargetNode] = useState(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(new Date().toLocaleTimeString());

  // Function to manually fetch overview JSON
  const fetchOverview = async () => {
    try {
      const res = await fetch('/api/v1/overview');
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastFetchTime(new Date().toLocaleTimeString());
      }
    } catch (err) {
      console.error('Failed to fetch overview:', err);
    }
  };

  // Function to fetch IP configuration
  const fetchIpConfig = async () => {
    try {
      const res = await fetch('/api/v1/config/ip');
      if (res.ok) {
        const json = await res.json();
        setIpConfig(json);
      }
    } catch (err) {
      console.error('Failed to fetch IP config:', err);
    }
  };

  useEffect(() => {
    // Initial fetches
    fetchOverview();
    fetchIpConfig();

    // Setup SSE connection
    let eventSource;
    try {
      eventSource = new EventSource('/stream');

      eventSource.onopen = () => {
        setSseConnected(true);
      };

      const handleEvent = (event) => {
        try {
          const json = JSON.parse(event.data);
          if (json.nodes) {
            setData(json);
            setLastFetchTime(new Date().toLocaleTimeString());
          }
        } catch (e) {
          console.error('Error parsing SSE event:', e);
        }
      };

      const handleConfigEvent = (event) => {
        try {
          const json = JSON.parse(event.data);
          setIpConfig(json);
        } catch (e) {
          console.error('Error parsing config SSE event:', e);
        }
      };

      eventSource.addEventListener('overview', handleEvent);
      eventSource.addEventListener('telemetry_update', handleEvent);
      eventSource.addEventListener('node_status_change', handleEvent);
      eventSource.addEventListener('node_registered', handleEvent);
      eventSource.addEventListener('config_update', handleConfigEvent);

      eventSource.onerror = () => {
        setSseConnected(false);
        // Fallback polling if SSE fails
        fetchOverview();
        fetchIpConfig();
      };
    } catch (e) {
      console.error('Failed to connect to SSE stream:', e);
    }

    // Polling fallback interval every 4s
    const pollInterval = setInterval(() => {
      fetchOverview();
      fetchIpConfig();
    }, 4000);

    return () => {
      if (eventSource) eventSource.close();
      clearInterval(pollInterval);
    };
  }, []);

  const handleEditNodeIp = (nodeInfo) => {
    setEditTargetNode(nodeInfo);
    // Smooth scroll up to IP configuration card
    const ipSection = document.getElementById('ip-config-section');
    if (ipSection) {
      ipSection.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-8">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800/80 mb-8">
        <div>
          <div className="flex items-center gap-3">
            <div className="bg-cyan-500/10 p-2.5 rounded-xl border border-cyan-500/20 text-cyan-400">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-100">
                NavosEdge <span className="text-cyan-400 font-medium text-lg">Parent Manager</span>
              </h1>
              <p className="text-xs text-slate-400">
                Multi-Node Edge Intelligence Dashboard & System Aggregator
              </p>
            </div>
          </div>
        </div>

        {/* Live SSE, Target IP & Status indicators */}
        <div className="flex items-center gap-3">
          {ipConfig?.current_ip && (
            <div className="hidden md:inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border bg-slate-900 border-slate-800 text-slate-300">
              <Globe className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-mono text-[11px] text-cyan-200">
                Node IP: {ipConfig.current_ip}:{ipConfig.port || 8420}
              </span>
            </div>
          )}

          <div className={`inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border ${
            sseConnected
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
          }`}>
            <Radio className={`w-3.5 h-3.5 ${sseConnected ? 'animate-pulse' : ''}`} />
            <span>{sseConnected ? 'SSE Live Stream' : 'HTTP Polling'}</span>
          </div>

          <button
            onClick={() => {
              fetchOverview();
              fetchIpConfig();
            }}
            className="p-2 bg-slate-900 border border-slate-800 rounded-lg hover:border-slate-700 text-slate-400 hover:text-slate-200 transition"
            title="Refresh overview and IP status"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main>
        {/* System Overview Statistics */}
        <OverviewCards data={data} />

        {/* Location Comparison Bar Chart */}
        <LocationComparison nodes={data.nodes} />

        {/* Edge Node IP Configuration Panel */}
        <div id="ip-config-section">
          <IpConfigCard
            ipConfig={ipConfig}
            initialEditNode={editTargetNode}
            onConfigUpdated={(newCfg) => {
              setIpConfig(newCfg);
              fetchOverview();
            }}
          />
        </div>

        {/* Multi-Node Grid Cards */}
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Activity className="w-5 h-5 text-cyan-400" />
              Monitored Nodes ({data.nodes?.length || 0})
            </h2>
            <span className="text-xs text-slate-400">Updated: {lastFetchTime}</span>
          </div>

          {(!data.nodes || data.nodes.length === 0) ? (
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center">
              <h3 className="text-base font-semibold text-slate-300">No Nodes Connected</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                Configure the Edge Node IP above or start nodes using sensor simulator/hardware bridge to begin stream aggregation.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {data.nodes.map((node) => (
                <NodeCard
                  key={node.node_id}
                  node={node}
                  onEditIp={handleEditNodeIp}
                  onConfigUpdated={(newCfg) => {
                    setIpConfig(newCfg);
                    fetchOverview();
                  }}
                  currentConfigIp={ipConfig?.current_ip}
                  currentConfigPort={ipConfig?.port}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="mt-12 pt-6 border-t border-slate-900 text-center text-xs text-slate-600">
        NavosEdge Parent Manager Server • Lightweight Edge Infrastructure Architecture
      </footer>
    </div>
  );
}
