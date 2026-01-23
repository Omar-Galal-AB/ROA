interface ArmControlsProps {
  pressedKeys: Set<string>;
}

export function ArmControls({ pressedKeys }: ArmControlsProps) {
  const ArrowKey = ({ direction, keyName }: { direction: string; keyName: string }) => {
    const isPressed = pressedKeys.has(keyName.toLowerCase());
    
    const arrowPaths = {
      up: 'M12 4l-8 8h5v8h6v-8h5z',
      down: 'M12 20l8-8h-5V4H9v8H4z',
      left: 'M4 12l8-8v5h8v6h-8v5z',
      right: 'M20 12l-8 8v-5H4v-6h8V4z'
    };

    return (
      <div
        className={`
          w-12 h-12 rounded-md flex items-center justify-center
          transition-all duration-100 border-2
          ${isPressed 
            ? 'bg-purple-400 border-purple-300 text-slate-900 shadow-lg shadow-purple-400/50 scale-95' 
            : 'bg-slate-800/80 border-purple-500/50 text-purple-300 hover:border-purple-400'
          }
        `}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
          <path d={arrowPaths[direction as keyof typeof arrowPaths]} />
        </svg>
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-purple-500/30 rounded-lg p-4 shadow-2xl">
      <div className="text-purple-300 font-mono text-[10px] mb-2 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-purple-400 rounded-full"></div>
        ARM CONTROL
      </div>
      <div className="flex flex-col items-center gap-1.5">
        <div className="flex justify-center">
          <ArrowKey direction="up" keyName="arrowup" />
        </div>
        <div className="flex gap-1.5">
          <ArrowKey direction="left" keyName="arrowleft" />
          <ArrowKey direction="down" keyName="arrowdown" />
          <ArrowKey direction="right" keyName="arrowright" />
        </div>
      </div>
      <div className="mt-3 text-[9px] text-purple-400/70 font-mono text-center">
        Arm Position
      </div>
    </div>
  );
}