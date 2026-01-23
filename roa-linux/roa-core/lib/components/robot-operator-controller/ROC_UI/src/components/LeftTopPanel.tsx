import { useState } from 'react';
import { ControlSliders } from './ControlSliders';
import { HardwareStatus } from './HardwareStatus';
import { ScreenStatus } from './ScreenStatus';

interface LeftTopPanelProps {
  pressedKeys: Set<string>;
}

export function LeftTopPanel({ pressedKeys }: LeftTopPanelProps) {
  const [activePanel, setActivePanel] = useState<'controls' | 'hardware' | 'screen'>('controls');

  return (
    <div className="flex flex-col gap-2">
      {/* Panel Selector */}
      <div className="flex gap-1">
        <button
          onClick={() => setActivePanel('controls')}
          className={`
            px-3 py-1.5 rounded-md font-mono text-[10px] transition-all border
            ${activePanel === 'controls'
              ? 'bg-blue-500 text-white border-blue-400 shadow-lg shadow-blue-500/30'
              : 'bg-slate-800/60 text-blue-400 border-blue-500/30 hover:bg-slate-800'
            }
          `}
        >
          CONTROLS
        </button>
        <button
          onClick={() => setActivePanel('hardware')}
          className={`
            px-3 py-1.5 rounded-md font-mono text-[10px] transition-all border
            ${activePanel === 'hardware'
              ? 'bg-orange-500 text-white border-orange-400 shadow-lg shadow-orange-500/30'
              : 'bg-slate-800/60 text-orange-400 border-orange-500/30 hover:bg-slate-800'
            }
          `}
        >
          HARDWARE
        </button>
        <button
          onClick={() => setActivePanel('screen')}
          className={`
            px-3 py-1.5 rounded-md font-mono text-[10px] transition-all border
            ${activePanel === 'screen'
              ? 'bg-cyan-500 text-white border-cyan-400 shadow-lg shadow-cyan-500/30'
              : 'bg-slate-800/60 text-cyan-400 border-cyan-500/30 hover:bg-slate-800'
            }
          `}
        >
          DISPLAY
        </button>
      </div>

      {/* Panel Content */}
      {activePanel === 'controls' && <ControlSliders pressedKeys={pressedKeys} />}
      {activePanel === 'hardware' && <HardwareStatus />}
      {activePanel === 'screen' && <ScreenStatus />}
    </div>
  );
}