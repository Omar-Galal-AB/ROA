import { useState, useEffect } from 'react';

interface RobotCommandsProps {
  pressedKeys: Set<string>;
}

export function RobotCommands({ pressedKeys }: RobotCommandsProps) {
  const [mode, setMode] = useState<'manual' | 'automatic'>('manual');
  const [selectedRobot, setSelectedRobot] = useState('ROBOT-01');
  const [commandPanel, setCommandPanel] = useState<'movement' | 'utility' | 'advanced'>('movement');

  const robots = [
    { id: 'ROBOT-01', name: 'Alpha Scout', type: 'Scout' },
    { id: 'ROBOT-02', name: 'Beta Heavy', type: 'Heavy' },
    { id: 'ROBOT-03', name: 'Gamma Arm', type: 'Manipulator' },
    { id: 'ROBOT-04', name: 'Delta Drone', type: 'Aerial' },
    { id: 'ROBOT-05', name: 'Epsilon Loader', type: 'Loader' },
    { id: 'ROBOT-06', name: 'Zeta Patrol', type: 'Patrol' },
    { id: 'ROBOT-07', name: 'Eta Digger', type: 'Excavator' },
    { id: 'ROBOT-08', name: 'Theta Carrier', type: 'Transport' },
    { id: 'ROBOT-09', name: 'Iota Sentry', type: 'Guard' },
    { id: 'ROBOT-10', name: 'Kappa Welder', type: 'Welder' },
  ];

  const commandSets = {
    manual: {
      movement: [
        { key: 'F1', label: 'HOME POSITION', description: 'Reset to default' },
        { key: 'F2', label: 'PRECISION MODE', description: 'Slow & accurate' },
        { key: 'F3', label: 'SPRINT MODE', description: 'Maximum speed' },
        { key: 'F4', label: 'CROUCH/LOWER', description: 'Reduce height' },
      ],
      utility: [
        { key: 'F5', label: 'GRIP TOGGLE', description: 'Open/Close gripper' },
        { key: 'F6', label: 'CAMERA SWITCH', description: 'Cycle cameras' },
        { key: 'F7', label: 'LIGHT TOGGLE', description: 'LED on/off' },
        { key: 'F8', label: 'TOOL SWITCH', description: 'Change tool' },
      ],
      advanced: [
        { key: 'F9', label: 'CALIBRATE', description: 'Sensor calibration' },
        { key: 'F10', label: 'DIAGNOSTIC', description: 'System check' },
        { key: 'F11', label: 'SAVE STATE', description: 'Save position' },
        { key: 'F12', label: 'EMERGENCY STOP', description: 'Halt all motors' },
      ],
    },
    automatic: {
      movement: [
        { key: 'F1', label: 'AUTO PATROL', description: 'Start patrol route' },
        { key: 'F2', label: 'FOLLOW PATH', description: 'Waypoint nav' },
        { key: 'F3', label: 'RETURN HOME', description: 'Go to start' },
        { key: 'F4', label: 'AVOID OBSTACLES', description: 'Enable sensors' },
      ],
      utility: [
        { key: 'F5', label: 'AUTO PICK', description: 'Object detection' },
        { key: 'F6', label: 'AUTO SCAN', description: 'Environment scan' },
        { key: 'F7', label: 'AUTO SORT', description: 'Organize items' },
        { key: 'F8', label: 'AUTO CHARGE', description: 'Find charger' },
      ],
      advanced: [
        { key: 'F9', label: 'AUTO DOCK', description: 'Return to station' },
        { key: 'F10', label: 'SEQUENCE RUN', description: 'Execute routine' },
        { key: 'F11', label: 'LEARNING MODE', description: 'Record actions' },
        { key: 'F12', label: 'SWARM SYNC', description: 'Multi-robot coord' },
      ],
    },
  };

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
  }, []);

  const currentCommands = commandSets[mode][commandPanel];

  const CommandButton = ({ keyLabel, label, description }: { keyLabel: string; label: string; description: string }) => {
    const isPressed = pressedKeys.has(keyLabel.toLowerCase());
    
    return (
      <div
        className={`
          p-2 rounded-md transition-all duration-100 border cursor-pointer
          ${isPressed 
            ? 'bg-emerald-400 border-emerald-300 text-slate-900 shadow-lg shadow-emerald-400/50 scale-98' 
            : 'bg-slate-800/60 border-emerald-500/30 hover:border-emerald-400/50 hover:bg-slate-800/80'
          }
        `}
      >
        <div className="flex items-center gap-2">
          <div
            className={`
              px-1.5 py-0.5 rounded font-mono text-[9px] border
              ${isPressed 
                ? 'bg-slate-900 text-emerald-300 border-slate-700' 
                : 'bg-slate-900/50 text-emerald-400 border-emerald-500/30'
              }
            `}
          >
            {keyLabel}
          </div>
          <div className="flex-1">
            <div className={`font-mono text-[10px] ${isPressed ? 'text-slate-900' : 'text-emerald-300'}`}>
              {label}
            </div>
            <div className={`font-mono text-[8px] ${isPressed ? 'text-slate-700' : 'text-emerald-400/60'}`}>
              {description}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-emerald-500/30 rounded-lg p-4 shadow-2xl w-80">
      <div className="text-emerald-300 font-mono text-[10px] mb-3 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></div>
        ROBOT COMMANDS
      </div>

      {/* Robot Selector */}
      <div className="mb-3">
        <div className="text-emerald-400/70 font-mono text-[8px] mb-1.5">SELECT ROBOT (1-9, 0)</div>
        <div className="grid grid-cols-2 gap-1.5 max-h-32 overflow-y-auto pr-1 scrollbar-thin">
          {robots.map((robot, index) => (
            <button
              key={robot.id}
              onClick={() => setSelectedRobot(robot.id)}
              className={`
                px-2 py-1.5 rounded-md font-mono text-[9px] transition-all border
                ${selectedRobot === robot.id
                  ? 'bg-emerald-500/30 border-emerald-400 text-emerald-200'
                  : 'bg-slate-800/40 border-emerald-500/20 text-emerald-400 hover:bg-slate-800/60'
                }
              `}
            >
              <div className="flex items-center gap-1.5">
                <span className="bg-slate-900/50 px-1 py-0.5 rounded text-[8px] text-emerald-300">
                  {index + 1 === 10 ? '0' : index + 1}
                </span>
                {robot.id}
              </div>
              <div className="text-[8px] text-emerald-300/60">{robot.type}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-1.5 mb-3 bg-slate-800/50 p-0.5 rounded-lg">
        <button
          onClick={() => setMode('manual')}
          className={`
            flex-1 py-1.5 px-3 rounded-md font-mono text-[10px] transition-all
            ${mode === 'manual' 
              ? 'bg-blue-500 text-white shadow-lg' 
              : 'bg-transparent text-blue-400 hover:bg-slate-700/50'
            }
          `}
        >
          MANUAL
        </button>
        <button
          onClick={() => setMode('automatic')}
          className={`
            flex-1 py-1.5 px-3 rounded-md font-mono text-[10px] transition-all
            ${mode === 'automatic' 
              ? 'bg-purple-500 text-white shadow-lg' 
              : 'bg-transparent text-purple-400 hover:bg-slate-700/50'
            }
          `}
        >
          AUTO
        </button>
      </div>

      {/* Command Panel Selector */}
      <div className="flex gap-0.5 mb-2 bg-slate-800/30 p-0.5 rounded-lg">
        <button
          onClick={() => setCommandPanel('movement')}
          className={`
            flex-1 py-1 px-2 rounded font-mono text-[9px] transition-all
            ${commandPanel === 'movement' 
              ? 'bg-emerald-500/40 text-emerald-200' 
              : 'text-emerald-400/60 hover:text-emerald-300'
            }
          `}
        >
          MOVE
        </button>
        <button
          onClick={() => setCommandPanel('utility')}
          className={`
            flex-1 py-1 px-2 rounded font-mono text-[9px] transition-all
            ${commandPanel === 'utility' 
              ? 'bg-emerald-500/40 text-emerald-200' 
              : 'text-emerald-400/60 hover:text-emerald-300'
            }
          `}
        >
          UTILITY
        </button>
        <button
          onClick={() => setCommandPanel('advanced')}
          className={`
            flex-1 py-1 px-2 rounded font-mono text-[9px] transition-all
            ${commandPanel === 'advanced' 
              ? 'bg-emerald-500/40 text-emerald-200' 
              : 'text-emerald-400/60 hover:text-emerald-300'
            }
          `}
        >
          ADVANCED
        </button>
      </div>

      {/* Command List */}
      <div className="space-y-1.5 mb-3 max-h-44 overflow-y-auto pr-1 scrollbar-thin">
        {currentCommands.map((cmd) => (
          <CommandButton
            key={cmd.key}
            keyLabel={cmd.key}
            label={cmd.label}
            description={cmd.description}
          />
        ))}
      </div>

      <div className="pt-2 border-t border-emerald-500/20">
        <div className="text-[8px] font-mono text-emerald-400/60 text-center">
          {selectedRobot} | {mode.toUpperCase()} | {commandPanel.toUpperCase()}
        </div>
      </div>
    </div>
  );
}