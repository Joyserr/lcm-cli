import React, { useEffect, useRef, useMemo, useState } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import type { PlotSeries } from '../types';

interface PlotPanelProps {
  id: string;
  title: string;
  series: PlotSeries[];
  data: Record<string, Record<string, { timestamps: number[]; values: number[] }>>;
  timeWindow: number;
  onRemove: () => void;
  onRemoveSeries: (index: number) => void;
  onClearSeries: () => void;
  onTitleChange: (newTitle: string) => void;
  paused: boolean;
}

function computeStats(values: number[]) {
  if (values.length === 0) return { min: 0, max: 0, avg: 0, last: 0 };
  let min = Infinity, max = -Infinity, sum = 0;
  for (const v of values) {
    if (v < min) min = v;
    if (v > max) max = v;
    sum += v;
  }
  return { min, max, avg: sum / values.length, last: values[values.length - 1] };
}

export function PlotPanel({ title, series, data, timeWindow, onRemove, onRemoveSeries, onClearSeries, onTitleChange, paused }: PlotPanelProps) {
  const [editingTitle, setEditingTitle] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  const plotData = useMemo(() => {
    const now = Date.now() / 1000;
    const cutoff = timeWindow > 0 ? now - timeWindow : 0;

    const allTimes = new Set<number>();
    for (const s of series) {
      const chData = data[s.channel]?.[s.field];
      if (!chData) continue;
      for (const t of chData.timestamps) {
        if (t >= cutoff) allTimes.add(t);
      }
    }
    const sorted = Array.from(allTimes).sort((a, b) => a - b);

    const seriesArrays: (number | null)[][] = series.map(() =>
      sorted.map(() => null)
    );
    for (let si = 0; si < series.length; si++) {
      const s = series[si];
      const chData = data[s.channel]?.[s.field];
      if (!chData) continue;
      const timeMap = new Map<number, number>();
      for (let i = 0; i < chData.timestamps.length; i++) {
        if (chData.timestamps[i] >= cutoff) {
          timeMap.set(chData.timestamps[i], chData.values[i]);
        }
      }
      for (let ti = 0; ti < sorted.length; ti++) {
        const val = timeMap.get(sorted[ti]);
        if (val !== undefined) seriesArrays[si][ti] = val;
      }
    }

    return [sorted, ...seriesArrays] as uPlot.AlignedData;
  }, [series, data, timeWindow]);

  // Compute per-series stats
  const stats = useMemo(() => {
    return series.map((s) => {
      const now = Date.now() / 1000;
      const cutoff = timeWindow > 0 ? now - timeWindow : 0;
      const chData = data[s.channel]?.[s.field];
      if (!chData) return { min: 0, max: 0, avg: 0, last: 0 };
      const vals = chData.values.filter((_, i) => chData.timestamps[i] >= cutoff);
      return computeStats(vals);
    });
  }, [series, data, timeWindow]);

  // Chart create/update
  useEffect(() => {
    if (!chartRef.current || series.length === 0) return;

    if (plotRef.current) {
      plotRef.current.destroy();
      plotRef.current = null;
    }

    const opts: uPlot.Options = {
      width: chartRef.current.clientWidth || 600,
      height: 260,
      title,
      series: [
        { label: 'Time' },
        ...series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: 2,
          fill: s.color + '18',
        })),
      ],
      axes: [
        {
          label: '',
          values: (_self: uPlot, ticks: number[]) =>
            ticks.map((t) => {
              const d = new Date(t * 1000);
              return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
            }),
          grid: { stroke: 'rgba(0,0,0,0.05)', width: 1 },
          ticks: { stroke: 'rgba(0,0,0,0.05)', width: 1 },
        },
        {
          label: '',
          grid: { stroke: 'rgba(0,0,0,0.05)', width: 1 },
          ticks: { stroke: 'rgba(0,0,0,0.05)', width: 1 },
        },
      ],
      cursor: {
        drag: { x: true, y: false },
      },
      legend: { show: false },
      padding: [8, 8, 0, 0],
    };

    plotRef.current = new uPlot(opts, plotData, chartRef.current);

    return () => {
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [plotData, series, title]);

  // Resize observer
  useEffect(() => {
    if (!chartRef.current) return;
    const el = chartRef.current;
    const observer = new ResizeObserver(() => {
      if (plotRef.current) {
        plotRef.current.setSize({ width: el.clientWidth, height: 260 });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fmt = (n: number) => {
    if (Math.abs(n) >= 1000) return n.toFixed(0);
    if (Math.abs(n) >= 1) return n.toFixed(2);
    return n.toFixed(4);
  };

  return (
    <div className="plot-panel">
      <div className="plot-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {editingTitle ? (
            <input
              className="plot-title-input"
              defaultValue={title}
              autoFocus
              onBlur={(e) => { onTitleChange(e.target.value); setEditingTitle(false); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { onTitleChange((e.target as HTMLInputElement).value); setEditingTitle(false); } }}
            />
          ) : (
            <span className="plot-title" onDoubleClick={() => setEditingTitle(true)} style={{ cursor: 'text' }} title="Double-click to edit">
              {title}
            </span>
          )}
          {paused && <span style={{ fontSize: '10px', color: 'var(--orange)', fontWeight: 600 }}>PAUSED</span>}
          <div className="plot-tags">
            {series.map((s, i) => (
              <span
                key={i}
                className="plot-tag plot-tag-removable"
                style={{ color: s.color, background: s.color + '14' }}
                onClick={() => onRemoveSeries(i)}
                title="Click to remove"
              >
                {s.label}
                <span className="plot-tag-x">×</span>
              </span>
            ))}
            {series.length > 1 && (
              <span
                className="plot-tag plot-tag-clear"
                onClick={onClearSeries}
                title="Clear all"
              >
                Clear
              </span>
            )}
          </div>
        </div>
        <div className="plot-actions">
          <button className="plot-remove" onClick={onRemove}>✕</button>
        </div>
      </div>

      {series.length === 0 ? (
        <div className="plot-empty">
          <div className="plot-empty-icon">📈</div>
          Click a field from the sidebar to add a curve
        </div>
      ) : (
        <>
          <div ref={chartRef} className="plot-chart" />
          {/* Stats row */}
          <div style={{
            display: 'flex',
            gap: '16px',
            marginTop: '10px',
            padding: '8px 12px',
            background: 'rgba(0,0,0,0.02)',
            borderRadius: '8px',
            flexWrap: 'wrap',
          }}>
            {series.map((s, i) => (
              <div key={i} style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '10px', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: s.color }}>{s.label}</span>
                <span>Last: <b style={{ color: 'var(--text-primary)' }}>{fmt(stats[i].last)}</b></span>
                <span>Min: <b style={{ color: 'var(--text-primary)' }}>{fmt(stats[i].min)}</b></span>
                <span>Max: <b style={{ color: 'var(--text-primary)' }}>{fmt(stats[i].max)}</b></span>
                <span>Avg: <b style={{ color: 'var(--text-primary)' }}>{fmt(stats[i].avg)}</b></span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
