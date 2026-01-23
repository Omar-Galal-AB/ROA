import { useState } from 'react';
import { RobotHealth } from './RobotHealth';
import { RobotCommands } from './RobotCommands';

interface RightTopPanelProps {
  pressedKeys: Set<string>;
}

export function RightTopPanel({ pressedKeys }: RightTopPanelProps) {
  const [activeMenu, setActiveMenu] = useState<'health' | 'commands'>('commands');

  return (
    <div className="flex flex-col gap-2">
      {/* Menu Selector */}
      <div className="flex gap-1">
        <button
          onClick={() => setActiveMenu('health')}
          className={`
            flex-1 px-4 py-1.5 rounded-md font-mono text-[10px] transition-all border
            ${activeMenu === 'health'
              ? 'bg-green-500 text-white border-green-400 shadow-lg shadow-green-500/30'
              : 'bg-slate-800/60 text-green-400 border-green-500/30 hover:bg-slate-800'
            }
          `}
        >
          HEALTH
        </button>
        <button
          onClick={() => setActiveMenu('commands')}
          className={`
            flex-1 px-4 py-1.5 rounded-md font-mono text-[10px] transition-all border
            ${activeMenu === 'commands'
              ? 'bg-emerald-500 text-white border-emerald-400 shadow-lg shadow-emerald-500/30'
              : 'bg-slate-800/60 text-emerald-400 border-emerald-500/30 hover:bg-slate-800'
            }
          `}
        >
          COMMANDS
        </button>
      </div>

      {/* Menu Content */}
      {activeMenu === 'health' && <RobotHealth />}
      {activeMenu === 'commands' && <RobotCommands pressedKeys={pressedKeys} />}
    </div>
  );
}