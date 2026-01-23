import { useState, useEffect } from 'react';
import { Cpu, Zap, HardDrive, MemoryStick } from 'lucide-react';

export function HardwareStatus() {
  const [cpuTemp, setCpuTemp] = useState(62);
  const [gpuTemp, setGpuTemp] = useState(71);
  const [cpuUsage, setCpuUsage] = useState(45);
  const [gpuUsage, setGpuUsage] = useState(78);
  const [ramUsage, setRamUsage] = useState(12.4);
  const [vramUsage, setVramUsage] = useState(6.8);

  // Simulate fluctuating values
  useEffect(() => {
    const interval = setInterval(() => {
      setCpuTemp(prev => Math.max(55, Math.min(85, prev + (Math.random() - 0.5) * 2)));
      setGpuTemp(prev => Math.max(65, Math.min(90, prev + (Math.random() - 0.5) * 2)));
      setCpuUsage(prev => Math.max(30, Math.min(95, prev + (Math.random() - 0.5) * 5)));
      setGpuUsage(prev => Math.max(60, Math.min(100, prev + (Math.random() - 0.5) * 5)));
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  const HardwareItem = ({ 
    icon: Icon, 
    label, 
    value, 
    unit, 
    maxValue, 
    warningThreshold 
  }: { 
    icon: any; 
    label: string; 
    value: number; 
    unit: string;
    maxValue?: number;
    warningThreshold?: number;
  }) => {
    const isWarning = warningThreshold && value > warningThreshold;
    const percentage = maxValue ? (value / maxValue) * 100 : value;

    return (
      <div className="bg-slate-800/40 rounded-md p-2 border border-orange-500/20">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Icon className="w-3 h-3 text-orange-400" />
          <span className="text-orange-300 font-mono text-[9px]">{label}</span>
        </div>
        <div className="flex items-end justify-between mb-1.5">
          <span className={`font-mono text-lg ${isWarning ? 'text-red-400' : 'text-orange-100'}`}>
            {typeof value === 'number' ? value.toFixed(1) : value}
          </span>
          <span className="text-orange-400/70 font-mono text-[10px]">{unit}</span>
        </div>
        {maxValue && (
          <div className="h-1 bg-slate-700/50 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-300 ${
                isWarning ? 'bg-red-500' : 'bg-orange-500'
              }`}
              style={{ width: `${Math.min(percentage, 100)}%` }}
            />
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-orange-500/30 rounded-lg p-4 shadow-2xl w-64">
      <div className="text-orange-300 font-mono text-[10px] mb-3 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-orange-400 rounded-full animate-pulse"></div>
        UE5 HARDWARE STATUS
      </div>

      <div className="space-y-2">
        <HardwareItem 
          icon={Cpu}
          label="CPU TEMP"
          value={cpuTemp}
          unit="°C"
          maxValue={100}
          warningThreshold={75}
        />

        <HardwareItem 
          icon={Zap}
          label="GPU TEMP"
          value={gpuTemp}
          unit="°C"
          maxValue={100}
          warningThreshold={80}
        />

        <HardwareItem 
          icon={Cpu}
          label="CPU USAGE"
          value={cpuUsage}
          unit="%"
          maxValue={100}
          warningThreshold={90}
        />

        <HardwareItem 
          icon={Zap}
          label="GPU USAGE"
          value={gpuUsage}
          unit="%"
          maxValue={100}
          warningThreshold={95}
        />

        <div className="grid grid-cols-2 gap-2">
          <HardwareItem 
            icon={MemoryStick}
            label="RAM"
            value={ramUsage}
            unit="GB"
          />
          <HardwareItem 
            icon={HardDrive}
            label="VRAM"
            value={vramUsage}
            unit="GB"
          />
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-orange-500/20">
        <div className="text-[9px] font-mono text-orange-400/60 text-center">
          Unreal Engine 5 - System Monitor
        </div>
      </div>
    </div>
  );
}