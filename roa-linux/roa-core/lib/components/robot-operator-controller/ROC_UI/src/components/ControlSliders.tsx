import { useState } from 'react';

interface ControlSlidersProps {
  pressedKeys: Set<string>;
}

export function ControlSliders({ pressedKeys }: ControlSlidersProps) {
  const [speed, setSpeed] = useState(50);
  const [power, setPower] = useState(75);
  const [torque, setTorque] = useState(60);
  const [precision, setPrecision] = useState(80);

  const SliderControl = ({ 
    label, 
    value, 
    onChange, 
    color = 'blue' 
  }: { 
    label: string; 
    value: number; 
    onChange: (value: number) => void;
    color?: string;
  }) => {
    const colorStyles = {
      blue: {
        track: 'bg-blue-500',
        thumb: 'bg-blue-400 shadow-blue-400/50'
      },
      cyan: {
        track: 'bg-cyan-500',
        thumb: 'bg-cyan-400 shadow-cyan-400/50'
      },
      green: {
        track: 'bg-green-500',
        thumb: 'bg-green-400 shadow-green-400/50'
      },
      yellow: {
        track: 'bg-yellow-500',
        thumb: 'bg-yellow-400 shadow-yellow-400/50'
      }
    };

    const selectedColor = colorStyles[color as keyof typeof colorStyles];

    return (
      <div className="mb-3">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-blue-300 font-mono text-[10px]">{label}</span>
          <span className="text-cyan-400 font-mono text-[10px] bg-slate-800/50 px-1.5 py-0.5 rounded">
            {value}%
          </span>
        </div>
        <div className="relative">
          <div className="h-1.5 bg-slate-700/50 rounded-lg overflow-hidden">
            <div 
              className={`h-full ${selectedColor.track} transition-all duration-150`}
              style={{ width: `${value}%` }}
            />
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="absolute inset-0 w-full h-1.5 appearance-none bg-transparent cursor-grab active:cursor-grabbing slider-thumb"
            style={{
              background: 'transparent'
            }}
          />
        </div>
        <style jsx>{`
          .slider-thumb::-webkit-slider-thumb {
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            cursor: grab;
            transition: all 0.15s ease;
          }
          .slider-thumb::-webkit-slider-thumb {
            background: ${color === 'blue' ? '#60a5fa' : color === 'cyan' ? '#22d3ee' : color === 'green' ? '#4ade80' : '#facc15'};
            box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.8), 0 0 8px ${color === 'blue' ? 'rgba(96, 165, 250, 0.5)' : color === 'cyan' ? 'rgba(34, 211, 238, 0.5)' : color === 'green' ? 'rgba(74, 222, 128, 0.5)' : 'rgba(250, 204, 21, 0.5)'};
          }
          .slider-thumb:active::-webkit-slider-thumb {
            cursor: grabbing;
            transform: scale(1.1);
          }
          .slider-thumb::-moz-range-thumb {
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: none;
            cursor: grab;
            transition: all 0.15s ease;
            background: ${color === 'blue' ? '#60a5fa' : color === 'cyan' ? '#22d3ee' : color === 'green' ? '#4ade80' : '#facc15'};
            box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.8), 0 0 8px ${color === 'blue' ? 'rgba(96, 165, 250, 0.5)' : color === 'cyan' ? 'rgba(34, 211, 238, 0.5)' : color === 'green' ? 'rgba(74, 222, 128, 0.5)' : 'rgba(250, 204, 21, 0.5)'};
          }
          .slider-thumb:active::-moz-range-thumb {
            cursor: grabbing;
            transform: scale(1.1);
          }
        `}</style>
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-blue-500/30 rounded-lg p-4 shadow-2xl w-64">
      <div className="text-blue-300 font-mono text-[10px] mb-3 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
        CONTROL PARAMETERS
      </div>
      
      <SliderControl label="SPEED" value={speed} onChange={setSpeed} color="blue" />
      <SliderControl label="POWER" value={power} onChange={setPower} color="cyan" />
      <SliderControl label="TORQUE" value={torque} onChange={setTorque} color="green" />
      <SliderControl label="PRECISION" value={precision} onChange={setPrecision} color="yellow" />

      <div className="mt-3 pt-3 border-t border-blue-500/20">
        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
          <div className="bg-slate-800/50 px-2 py-1.5 rounded">
            <div className="text-blue-400/70">Battery</div>
            <div className="text-green-400">98%</div>
          </div>
          <div className="bg-slate-800/50 px-2 py-1.5 rounded">
            <div className="text-blue-400/70">Temp</div>
            <div className="text-cyan-400">42°C</div>
          </div>
        </div>
      </div>
    </div>
  );
}