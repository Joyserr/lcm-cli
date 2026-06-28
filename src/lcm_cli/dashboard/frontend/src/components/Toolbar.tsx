import React from 'react';

interface ToolbarProps {
  connected: boolean;
  timeWindow: number;
  onTimeWindowChange: (seconds: number) => void;
  channelCount: number;
  paused: boolean;
  onTogglePause: () => void;
}

const TIME_OPTIONS = [
  { label: '10s', value: 10 },
  { label: '30s', value: 30 },
  { label: '1m', value: 60 },
  { label: '5m', value: 300 },
  { label: 'All', value: 0 },
];

export function Toolbar({ connected, timeWindow, onTimeWindowChange, channelCount, paused, onTogglePause }: ToolbarProps) {
  return (
    <div className="toolbar">
      <div className="toolbar-left">
        <span className="logo">
          <span className="logo-icon">L</span>
          LCM Dashboard
        </span>
        <span className={`status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? 'Live' : 'Offline'}
        </span>
        {channelCount > 0 && (
          <span className="channel-count">{channelCount} channel{channelCount !== 1 ? 's' : ''}</span>
        )}
      </div>
      <div className="toolbar-right">
        <button
          className={`pause-btn ${paused ? 'paused' : 'running'}`}
          onClick={onTogglePause}
        >
          {paused ? '▶ Resume' : '❙❙ Pause'}
        </button>
        <label>Window</label>
        <select value={timeWindow} onChange={(e) => onTimeWindowChange(Number(e.target.value))}>
          {TIME_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
