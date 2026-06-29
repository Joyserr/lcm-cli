import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Toolbar } from './Toolbar';
import { ChannelPanel } from './ChannelPanel';
import { PlotPanel } from './PlotPanel';
import { useWebSocket } from '../hooks/useWebSocket';
import { useChannelData } from '../hooks/useChannelData';
import type { PlotPanelConfig, PlotSeries, WsMessage } from '../types';

// Apple-style palette for curves
const COLORS = [
  '#007aff', '#ff9500', '#34c759', '#ff3b30',
  '#af52de', '#5ac8fa', '#ff2d55', '#ffcc00',
  '#5856d6', '#30b0c7', '#ff6961', '#77dd77',
];
let colorIdx = 0;
function nextColor() {
  return COLORS[colorIdx++ % COLORS.length];
}

let panelIdCounter = 1;

export function Dashboard() {
  const [timeWindow, setTimeWindow] = useState(30);
  const [panels, setPanels] = useState<PlotPanelConfig[]>([
    { id: 'panel-1', title: 'Plot 1', series: [] },
  ]);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [paused, setPaused] = useState(false);
  const [activePanelId, setActivePanelId] = useState<string>('panel-1');
  const { data, handleMessage } = useChannelData();

  // Track subscribed channels to avoid duplicate subscribe messages
  const subscribedChannels = useRef<Set<string>>(new Set());

  // Compare mode state
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelection, setCompareSelection] = useState<{ channel: string; field: string }[]>([]);

  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const wsOnMessage = useCallback(
    (msg: WsMessage) => {
      if (!pausedRef.current) {
        handleMessage(msg);
      }
      setRefreshTrigger((prev) => prev + 1);
    },
    [handleMessage]
  );

  const { connected, subscribe } = useWebSocket(wsOnMessage);

  // Ensure activePanelId always points to an existing panel
  useEffect(() => {
    if (!panels.find((p) => p.id === activePanelId)) {
      setActivePanelId(panels[0]?.id ?? 'panel-1');
    }
  }, [panels, activePanelId]);

  // Subscribe to a channel (only if not already subscribed)
  const ensureSubscribed = useCallback((channel: string) => {
    if (subscribedChannels.current.has(channel)) return;
    subscribedChannels.current.add(channel);
    try {
      subscribe([channel]);
    } catch {
      // Ignore WebSocket errors — don't block state updates
    }
  }, [subscribe]);

  // Single field click (non-compare mode): add to active panel
  const handleFieldSelect = useCallback(
    (channel: string, field: string) => {
      // Prevent duplicate: if the same channel.field already exists in the active panel, skip
      const targetPanel = panels.find((p) => p.id === activePanelId) || panels[0];
      if (targetPanel && targetPanel.series.some((s) => s.channel === channel && s.field === field)) {
        return; // Already added — silently ignore
      }

      const newSeries: PlotSeries = {
        channel,
        field,
        label: `${channel}.${field}`,
        color: nextColor(),
      };

      ensureSubscribed(channel);

      setPanels((prev) => {
        const target = prev.find((p) => p.id === activePanelId) || prev[0];
        return prev.map((p) =>
          p.id === target.id
            ? { ...p, series: [...p.series, newSeries] }
            : p
        );
      });
    },
    [activePanelId, panels, ensureSubscribed]
  );

  // Compare mode: toggle field in selection
  const handleCompareAdd = useCallback((channel: string, field: string) => {
    setCompareSelection((prev) => {
      const exists = prev.some((s) => s.channel === channel && s.field === field);
      if (exists) {
        return prev.filter((s) => !(s.channel === channel && s.field === field));
      }
      return [...prev, { channel, field }];
    });
  }, []);

  // Commit compare selection to a new panel
  const handleCompareCommit = useCallback(() => {
    if (compareSelection.length === 0) return;

    const newSeries: PlotSeries[] = compareSelection.map((s) => ({
      channel: s.channel,
      field: s.field,
      label: `${s.channel}.${s.field}`,
      color: nextColor(),
    }));

    // Subscribe all channels (only new ones)
    for (const ch of new Set(compareSelection.map((s) => s.channel))) {
      ensureSubscribed(ch);
    }

    const id = `panel-${++panelIdCounter}`;
    const title = `Compare (${compareSelection.length} fields)`;
    setPanels((prev) => [...prev, { id, title, series: newSeries }]);
    setActivePanelId(id);
    setCompareSelection([]);
    setCompareMode(false);
  }, [compareSelection, ensureSubscribed]);

  // Toggle compare mode on/off
  const toggleCompareMode = useCallback(() => {
    setCompareMode((prev) => {
      if (prev) setCompareSelection([]);
      return !prev;
    });
  }, []);

  const addPanel = () => {
    const id = `panel-${++panelIdCounter}`;
    setPanels((prev) => [
      ...prev,
      { id, title: `Plot ${panelIdCounter}`, series: [] },
    ]);
    setActivePanelId(id);
  };

  const removePanel = (id: string) => {
    setPanels((prev) => prev.filter((p) => p.id !== id));
  };

  // Remove a single series from a panel
  const removeSeriesFromPanel = useCallback((panelId: string, seriesIndex: number) => {
    setPanels((prev) =>
      prev.map((p) =>
        p.id === panelId
          ? { ...p, series: p.series.filter((_, i) => i !== seriesIndex) }
          : p
      )
    );
  }, []);

  // Clear all series from a panel
  const clearPanelSeries = useCallback((panelId: string) => {
    setPanels((prev) =>
      prev.map((p) =>
        p.id === panelId ? { ...p, series: [] } : p
      )
    );
  }, []);

  // Rename panel title
  const renamePanel = useCallback((panelId: string, newTitle: string) => {
    setPanels((prev) =>
      prev.map((p) =>
        p.id === panelId ? { ...p, title: newTitle } : p
      )
    );
  }, []);

  return (
    <div className="dashboard">
      <Toolbar
        connected={connected}
        timeWindow={timeWindow}
        onTimeWindowChange={setTimeWindow}
        channelCount={Object.keys(data).length}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
      />

      {/* Compare mode toggle bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 16px',
        background: compareMode ? 'rgba(0,122,255,0.06)' : 'transparent',
        borderBottom: '1px solid var(--border)',
        transition: 'all 0.2s',
      }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={toggleCompareMode}
            style={{
              fontFamily: 'var(--font)',
              fontSize: '12px',
              fontWeight: 500,
              padding: '4px 14px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.2s',
              background: compareMode ? 'var(--accent)' : 'rgba(0,0,0,0.05)',
              color: compareMode ? 'white' : 'var(--text-secondary)',
            }}
          >
            {compareMode ? '✓ Compare Mode' : '⊕ Compare'}
          </button>
          {compareMode && (
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              Select fields across channels, then click "Add to Panel"
            </span>
          )}
        </div>
      </div>

      <div className="dashboard-body">
        <ChannelPanel
          onFieldSelect={handleFieldSelect}
          onCompareAdd={handleCompareAdd}
          compareMode={compareMode}
          compareSelection={compareSelection}
          onCompareToggle={handleCompareCommit}
          refreshTrigger={refreshTrigger}
        />
        <div className="main-area">
          {panels.map((panel) => (
            <PlotPanel
              key={panel.id}
              id={panel.id}
              title={panel.title}
              series={panel.series}
              data={data}
              timeWindow={timeWindow}
              onRemove={() => removePanel(panel.id)}
              onRemoveSeries={(idx) => removeSeriesFromPanel(panel.id, idx)}
              onClearSeries={() => clearPanelSeries(panel.id)}
              onTitleChange={(t) => renamePanel(panel.id, t)}
              onActivate={() => setActivePanelId(panel.id)}
              isActive={panel.id === activePanelId}
              paused={paused}
            />
          ))}
          <button className="add-panel-btn" onClick={addPanel}>
            + Add Plot Panel
          </button>
        </div>
      </div>
    </div>
  );
}
