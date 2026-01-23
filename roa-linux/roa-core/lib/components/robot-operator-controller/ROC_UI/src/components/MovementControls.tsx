interface MovementControlsProps {
  pressedKeys: Set<string>;
}

export function MovementControls({ pressedKeys }: MovementControlsProps) {
  const KeyButton = ({ keyLabel, className }: { keyLabel: string; className?: string }) => {
    const isPressed = pressedKeys.has(keyLabel.toLowerCase());
    return (
      <div
        className={`
          w-12 h-12 rounded-md flex items-center justify-center font-mono text-lg
          transition-all duration-100 border-2
          ${isPressed 
            ? 'bg-cyan-400 border-cyan-300 text-slate-900 shadow-lg shadow-cyan-400/50 scale-95' 
            : 'bg-slate-800/80 border-blue-500/50 text-blue-300 hover:border-blue-400'
          }
          ${className || ''}
        `}
      >
        {keyLabel}
      </div>
    );
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-blue-500/30 rounded-lg p-4 shadow-2xl">
      <div className="text-blue-300 font-mono text-[10px] mb-2 flex items-center gap-2">
        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
        MOVEMENT CONTROL
      </div>
      <div className="flex flex-col items-center gap-1.5">
        <div className="flex justify-center">
          <KeyButton keyLabel="W" />
        </div>
        <div className="flex gap-1.5">
          <KeyButton keyLabel="A" />
          <KeyButton keyLabel="S" />
          <KeyButton keyLabel="D" />
        </div>
      </div>
      <div className="mt-3 text-[9px] text-cyan-400/70 font-mono text-center">
        Wheels/Legs
      </div>
    </div>
  );
}