import { useState, useEffect } from 'react';
import { MovementControls } from './components/MovementControls';
import { ArmControls } from './components/ArmControls';
import { LeftTopPanel } from './components/LeftTopPanel';
import { RightTopPanel } from './components/RightTopPanel';

export default function App() {
  const [pressedKeys, setPressedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      setPressedKeys(prev => new Set(prev).add(e.key.toLowerCase()));
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      setPressedKeys(prev => {
        const newSet = new Set(prev);
        newSet.delete(e.key.toLowerCase());
        return newSet;
      });
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  return (
    <div className="w-screen h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 overflow-hidden relative fixed inset-0">
      {/* Background grid effect */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0" style={{
          backgroundImage: 'linear-gradient(rgba(59, 130, 246, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(59, 130, 246, 0.5) 1px, transparent 1px)',
          backgroundSize: '50px 50px'
        }}></div>
      </div>

      {/* Top Left - Multi Panel (Controls, Hardware, Screen) */}
      <div className="absolute top-6 left-6 z-10">
        <LeftTopPanel pressedKeys={pressedKeys} />
      </div>

      {/* Top Right - Multi Panel (Health, Commands) */}
      <div className="absolute top-6 right-6 z-10">
        <RightTopPanel pressedKeys={pressedKeys} />
      </div>

      {/* Bottom Left - WASD Movement Controls */}
      <div className="absolute bottom-6 left-6 z-10">
        <MovementControls pressedKeys={pressedKeys} />
      </div>

      {/* Bottom Right - Arrow Arm Controls */}
      <div className="absolute bottom-6 right-6 z-10">
        <ArmControls pressedKeys={pressedKeys} />
      </div>

      {/* Center Display - Robot Status */}
      <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center">
        <div className="bg-slate-800/40 backdrop-blur-sm border border-blue-500/30 rounded-lg px-6 py-4">
          <h1 className="text-3xl font-mono text-blue-400 mb-1">ROBOT CONTROL SYSTEM</h1>
          <div className="text-cyan-300 font-mono text-xs">UE5 Interface v2.1</div>
          <div className="mt-3 flex gap-2 justify-center">
            <div className="h-1.5 w-1.5 bg-green-400 rounded-full animate-pulse"></div>
            <span className="text-green-400 text-[10px] font-mono">SYSTEM ONLINE</span>
          </div>
        </div>
      </div>
    </div>
  );
}