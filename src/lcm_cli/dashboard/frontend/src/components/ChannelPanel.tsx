import React, { useEffect, useState, useCallback, useRef } from 'react';
import { fetchChannelsInfo, fetchSchema } from '../api';
import type { ChannelSchema, ChannelInfo } from '../types';

interface ChannelPanelProps {
  onFieldSelect: (channel: string, field: string) => void;
  onCompareAdd: (channel: string, field: string) => void;
  compareMode: boolean;
  compareSelection: { channel: string; field: string }[];
  onCompareToggle: () => void;
  refreshTrigger: number;
}

// Apple-style accent colors for channel dots
const DOT_COLORS = ['#007aff', '#34c759', '#ff9500', '#ff3b30', '#af52de', '#ff2d55', '#5ac8fa', '#ffcc00'];

export function ChannelPanel({
  onFieldSelect,
  onCompareAdd,
  compareMode,
  compareSelection,
  onCompareToggle,
  refreshTrigger,
}: ChannelPanelProps) {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [expandedChannels, setExpandedChannels] = useState<Set<string>>(new Set());
  const [schemas, setSchemas] = useState<Record<string, ChannelSchema[]>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined);

  const refresh = useCallback(() => {
    fetchChannelsInfo().then(setChannels).catch(() => setChannels([]));
  }, []);

  useEffect(() => {
    refresh();
    // Periodic refresh every 2 seconds to discover new channels and update Hz
    intervalRef.current = setInterval(refresh, 2000);
    return () => clearInterval(intervalRef.current);
  }, [refreshTrigger, refresh]);

  const toggleChannel = async (ch: string) => {
    setExpandedChannels((prev) => {
      const next = new Set(prev);
      if (next.has(ch)) {
        next.delete(ch);
      } else {
        next.add(ch);
      }
      return next;
    });
    if (!schemas[ch]) {
      const schema = await fetchSchema(ch);
      setSchemas((prev) => ({ ...prev, [ch]: schema }));
    }
  };

  const handleFieldClick = (ch: string, field: string) => {
    if (compareMode) {
      onCompareAdd(ch, field);
    } else {
      onFieldSelect(ch, field);
    }
  };

  const isSelected = (ch: string, field: string) =>
    compareSelection.some((s) => s.channel === ch && s.field === field);

  return (
    <div className="channel-panel">
      <div className="channel-panel-header">
        <h3>Channels</h3>
        <button className="refresh-btn" onClick={refresh} title="Refresh">↻</button>
      </div>

      {channels.length === 0 ? (
        <p className="no-data">
          Waiting for LCM data...<br />
          <span className="hint">Start a publisher to see channels here.</span>
        </p>
      ) : (
        <>
          {compareMode && compareSelection.length > 0 && (
            <div className="compare-banner">
              <span>{compareSelection.length} field{compareSelection.length !== 1 ? 's' : ''} selected</span>
              <button onClick={onCompareToggle}>Add to Panel →</button>
            </div>
          )}

          <div className="sidebar-section-label">Topics ({channels.length})</div>
          <ul className="channel-list">
            {channels.map((ch, idx) => (
              <li key={ch.name}>
                <div className="channel-name" onClick={() => toggleChannel(ch.name)}>
                  <span className="chevron">{expandedChannels.has(ch.name) ? '▾' : '▸'}</span>
                  <span className="channel-dot" style={{ background: DOT_COLORS[idx % DOT_COLORS.length] }} />
                  <span className="channel-label">{ch.name}</span>
                  <span className="channel-hz" title="Frame rate">
                    {ch.frame_rate > 0 ? `${ch.frame_rate.toFixed(1)} Hz` : '—'}
                  </span>
                </div>
                {expandedChannels.has(ch.name) && schemas[ch.name] && (
                  <ul className="field-list">
                    {schemas[ch.name].map((f) => (
                      <li
                        key={f.path}
                        className="field-item"
                        onClick={() => handleFieldClick(ch.name, f.path)}
                        style={isSelected(ch.name, f.path) ? { background: 'var(--bg-active)', color: 'var(--accent)' } : undefined}
                      >
                        <span className="field-type-badge">num</span>
                        {f.path}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
