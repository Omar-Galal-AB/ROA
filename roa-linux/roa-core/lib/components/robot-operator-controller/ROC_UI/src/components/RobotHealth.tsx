import { useState, useEffect } from 'react';
import { Heart, Activity, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface Robot {
  id: string;
  name: string;
  status: 'online' | 'warning' | 'offline';
  heartbeat: number;
  battery: number;
  temperature: number;
  errors: number;
}

export function RobotHealth() {
  const [selectedRobot, setSelectedRobot] = useState('ROBOT-01');
  const [robots, setRobots] = useState<Robot[]>([
    { id: 'ROBOT-01', name: 'Alpha Scout', status: 'online', heartbeat: 98, battery: 87, temperature: 45, errors: 0 },
    { id: 'ROBOT-02', name: 'Beta Heavy', status: 'online', heartbeat: 95, battery: 72, temperature: 52, errors: 0 },
    { id: 'ROBOT-03', name: 'Gamma Arm', status: 'warning', heartbeat: 78, battery: 34, temperature: 68, errors: 2 },
    { id: 'ROBOT-04', name: 'Delta Drone', status: 'online', heartbeat: 100, battery: 91, temperature: 38, errors: 0 },
    { id: 'ROBOT-05', name: 'Epsilon Loader', status: 'online', heartbeat: 92, battery: 65, temperature: 48, errors: 0 },
    { id: 'ROBOT-06', name: 'Zeta Patrol', status: 'online', heartbeat: 96, battery: 78, temperature: 44, errors: 0 },
    { id: 'ROBOT-07', name: 'Eta Digger', status: 'warning', heartbeat: 85, battery: 42, temperature: 71, errors: 1 },
    { id: 'ROBOT-08', name: 'Theta Carrier', status: 'online', heartbeat: 94, battery: 88, temperature: 39, errors: 0 },
    { id: 'ROBOT-09', name: 'Iota Sentry', status: 'online', heartbeat: 99, battery: 93, temperature: 41, errors: 0 },
    { id: 'ROBOT-10', name: 'Kappa Welder', status: 'offline', heartbeat: 0, battery: 0, temperature: 25, errors: 5 },
  ]);

  // Simulate heartbeat fluctuation
  useEffect(() => {
    const interval = setInterval(() => {
      setRobots(prev => prev.map(robot => ({
        ...robot,
        heartbeat: robot.status === 'offline' ? 0 : Math.max(60, Math.min(100, robot.heartbeat + (Math.random() - 0.5) * 10)),
        battery: Math.max(0, robot.battery - Math.random() * 0.1),
        temperature: robot.status === 'offline' ? 25 : Math.max(30, Math.min(80, robot.temperature + (Math.random() - 0.5) * 3)),
      })));
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  // Handle number key shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      const num = parseInt(e.key);
      if (num >= 1 && num <= 9) {
        const robotIndex = num - 1;
        if (robots[robotIndex]) {
          setSelectedRobot(robots[robotIndex].id);
        }
      } else if (e.key === '0' && robots[9]) {
        setSelectedRobot(robots[9].id);
      }
    };

    window.addEventListener('keypress', handleKeyPress);
    return () => window.removeEventListener('keypress', handleKeyPress);
  }, [robots]);

  const selectedRobotData = robots.find(r => r.id === selectedRobot);

  const HeartbeatMonitor = ({ value }: { value: number }) => {
    return (
      <div className="relative h-16 bg-slate-800/40 rounded-lg border border-green-500/20 overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex items-center gap-2">
            <Heart className="w-5 h-5 text-red-500 animate-pulse" fill="currentColor" />
            <span className="text-green-400 font-mono text-2xl">{value.toFixed(0)}</span>
            <span className="text-green-400/70 font-mono text-sm">BPM</span>
          </div>
        </div>
        {/* Simulated ECG line */}
        <svg className="absolute inset-0 w-full h-full opacity-30" viewBox="0 0 200 50">
          <polyline
            points="0,25 40,25 45,10 50,40 55,25 200,25"
            fill="none"
            stroke="#22c55e"
            strokeWidth="2"
            className="animate-pulse"
          />
        </svg>
      </div>
    );
  };

  const StatusBadge = ({ status }: { status: 'online' | 'warning' | 'offline' }) => {
    const config = {
      online: { color: 'bg-green-500', text: 'ONLINE', icon: CheckCircle2 },
      warning: { color: 'bg-yellow-500', text: 'WARNING', icon: AlertTriangle },
      offline: { color: 'bg-red-500', text: 'OFFLINE', icon: AlertTriangle },
    };

    const { color, text, icon: Icon } = config[status];

    return (
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${color}/20 border border-${color.split('-')[1]}-500/40`}>
        <div className={`w-2 h-2 rounded-full ${color} animate-pulse`}></div>
        <Icon className="w-3 h-3" />
        <span className="font-mono text-xs">{text}</span>
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-green-500/30 rounded-lg p-4 shadow-2xl w-80">
      <div className="text-green-300 font-mono text-[10px] mb-3 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></div>
        ROBOT HEALTH MONITOR
      </div>

      {/* Robot Selector */}
      <div className="grid grid-cols-2 gap-1.5 mb-3 max-h-32 overflow-y-auto pr-1 scrollbar-thin">
        {robots.map((robot, index) => (
          <button
            key={robot.id}
            onClick={() => setSelectedRobot(robot.id)}
            className={`
              px-2 py-1.5 rounded-md font-mono text-[9px] transition-all border
              ${selectedRobot === robot.id
                ? 'bg-green-500/30 border-green-400 text-green-200'
                : 'bg-slate-800/40 border-green-500/20 text-green-400 hover:bg-slate-800/60'
              }
            `}
          >
            <div className="flex items-center gap-1.5">
              <div className={`w-1 h-1 rounded-full ${
                robot.status === 'online' ? 'bg-green-500' : 
                robot.status === 'warning' ? 'bg-yellow-500' : 'bg-red-500'
              } animate-pulse`}></div>
              <span className="bg-slate-900/50 px-1 py-0.5 rounded text-[8px] text-green-300">
                {index + 1 === 10 ? '0' : index + 1}
              </span>
              {robot.id}
            </div>
            <div className="text-[8px] text-green-300/60 mt-0.5">{robot.name}</div>
          </button>
        ))}
      </div>
      
      <div className="text-[8px] text-green-400/50 font-mono text-center mb-2 border-t border-green-500/20 pt-2">
        Press 1-9, 0 for quick select
      </div>

      {/* Selected Robot Details */}
      {selectedRobotData && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-green-200 font-mono text-sm">{selectedRobotData.name}</div>
              <div className="text-green-400/60 font-mono text-[9px]">{selectedRobotData.id}</div>
            </div>
            <StatusBadge status={selectedRobotData.status} />
          </div>

          {/* Heartbeat Monitor */}
          <HeartbeatMonitor value={selectedRobotData.heartbeat} />

          {/* Vital Stats */}
          <div className="grid grid-cols-3 gap-1.5">
            <div className="bg-slate-800/40 rounded-md p-2 border border-green-500/20">
              <div className="flex items-center gap-0.5 mb-1">
                <Activity className="w-2.5 h-2.5 text-green-400" />
                <span className="text-green-400/70 font-mono text-[8px]">BATTERY</span>
              </div>
              <div className={`font-mono text-sm ${
                selectedRobotData.battery > 50 ? 'text-green-400' : 
                selectedRobotData.battery > 20 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {selectedRobotData.battery.toFixed(0)}%
              </div>
            </div>

            <div className="bg-slate-800/40 rounded-md p-2 border border-green-500/20">
              <div className="flex items-center gap-0.5 mb-1">
                <Activity className="w-2.5 h-2.5 text-cyan-400" />
                <span className="text-cyan-400/70 font-mono text-[8px]">TEMP</span>
              </div>
              <div className={`font-mono text-sm ${
                selectedRobotData.temperature < 60 ? 'text-cyan-400' : 
                selectedRobotData.temperature < 70 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {selectedRobotData.temperature.toFixed(0)}°C
              </div>
            </div>

            <div className="bg-slate-800/40 rounded-md p-2 border border-green-500/20">
              <div className="flex items-center gap-0.5 mb-1">
                <AlertTriangle className="w-2.5 h-2.5 text-orange-400" />
                <span className="text-orange-400/70 font-mono text-[8px]">ERRORS</span>
              </div>
              <div className={`font-mono text-sm ${
                selectedRobotData.errors === 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {selectedRobotData.errors}
              </div>
            </div>
          </div>

          {/* System Messages */}
          <div className="bg-slate-800/30 rounded-md p-2 border border-green-500/20 max-h-20 overflow-y-auto">
            <div className="text-green-400/70 font-mono text-[8px] mb-1">SYSTEM LOG</div>
            <div className="space-y-0.5 text-[8px] font-mono">
              <div className="text-green-300">✓ All systems operational</div>
              {selectedRobotData.errors > 0 && (
                <div className="text-yellow-400">⚠ {selectedRobotData.errors} warning(s) detected</div>
              )}
              <div className="text-green-300/60">Last sync: 2s ago</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}