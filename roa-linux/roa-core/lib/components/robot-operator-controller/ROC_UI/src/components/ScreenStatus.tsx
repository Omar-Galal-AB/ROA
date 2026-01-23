import { useState, useEffect } from 'react';
import { Monitor, Timer, Activity, Wifi } from 'lucide-react';

export function ScreenStatus() {
  const [fps, setFps] = useState(60);
  const [latency, setLatency] = useState(12);
  const [renderTime, setRenderTime] = useState(16.7);
  const [drawCalls, setDrawCalls] = useState(2847);

  // Simulate fluctuating values
  useEffect(() => {
    const interval = setInterval(() => {
      setFps(prev => Math.max(45, Math.min(144, prev + (Math.random() - 0.5) * 10)));
      setLatency(prev => Math.max(5, Math.min(50, prev + (Math.random() - 0.5) * 5)));
      setRenderTime(prev => Math.max(8, Math.min(25, prev + (Math.random() - 0.5) * 2)));
      setDrawCalls(prev => Math.max(2000, Math.min(5000, prev + (Math.random() - 0.5) * 200)));
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const StatusItem = ({ 
    icon: Icon, 
    label, 
    value, 
    unit,
    status 
  }: { 
    icon: any; 
    label: string; 
    value: string | number; 
    unit: string;
    status: 'good' | 'warning' | 'critical';
  }) => {
    const statusColors = {
      good: 'text-green-400',
      warning: 'text-yellow-400',
      critical: 'text-red-400'
    };

    const statusBg = {
      good: 'bg-green-500/20 border-green-500/30',
      warning: 'bg-yellow-500/20 border-yellow-500/30',
      critical: 'bg-red-500/20 border-red-500/30'
    };

    return (
      <div className={`rounded-md p-2 border ${statusBg[status]}`}>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Icon className={`w-3 h-3 ${statusColors[status]}`} />
          <span className="text-cyan-300 font-mono text-[9px]">{label}</span>
        </div>
        <div className="flex items-end justify-between">
          <span className={`font-mono text-lg ${statusColors[status]}`}>
            {typeof value === 'number' ? value.toFixed(value < 100 ? 1 : 0) : value}
          </span>
          <span className="text-cyan-400/70 font-mono text-[10px]">{unit}</span>
        </div>
      </div>
    );
  };

  const getFpsStatus = (fps: number): 'good' | 'warning' | 'critical' => {
    if (fps >= 55) return 'good';
    if (fps >= 45) return 'warning';
    return 'critical';
  };

  const getLatencyStatus = (latency: number): 'good' | 'warning' | 'critical' => {
    if (latency <= 20) return 'good';
    if (latency <= 40) return 'warning';
    return 'critical';
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-cyan-500/30 rounded-lg p-4 shadow-2xl w-64">
      <div className="text-cyan-300 font-mono text-[10px] mb-3 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse"></div>
        DISPLAY STATUS
      </div>

      <div className="space-y-2">
        <StatusItem 
          icon={Monitor}
          label="FRAME RATE"
          value={fps}
          unit="FPS"
          status={getFpsStatus(fps)}
        />

        <StatusItem 
          icon={Wifi}
          label="NETWORK LATENCY"
          value={latency}
          unit="ms"
          status={getLatencyStatus(latency)}
        />

        <StatusItem 
          icon={Timer}
          label="RENDER TIME"
          value={renderTime}
          unit="ms"
          status={renderTime < 20 ? 'good' : 'warning'}
        />

        <StatusItem 
          icon={Activity}
          label="DRAW CALLS"
          value={drawCalls}
          unit=""
          status={drawCalls < 3500 ? 'good' : 'warning'}
        />
      </div>

      <div className="mt-3 pt-3 border-t border-cyan-500/20">
        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
          <div className="bg-slate-800/50 px-2 py-1.5 rounded">
            <div className="text-cyan-400/70">Resolution</div>
            <div className="text-cyan-300">1920x1080</div>
          </div>
          <div className="bg-slate-800/50 px-2 py-1.5 rounded">
            <div className="text-cyan-400/70">V-Sync</div>
            <div className="text-green-400">ON</div>
          </div>
        </div>
      </div>

      <div className="mt-2 text-[9px] font-mono text-cyan-400/60 text-center">
        Display Performance Monitor
      </div>
    </div>
  );
}