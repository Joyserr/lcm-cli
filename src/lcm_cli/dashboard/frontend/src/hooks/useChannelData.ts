import { useState, useCallback, useRef, useEffect } from 'react';
import type { WsMessage } from '../types';

const MAX_POINTS = 3000;

interface ChannelFieldData {
  timestamps: number[];
  values: number[];
}

export function useChannelData() {
  const [data, setData] = useState<Record<string, Record<string, ChannelFieldData>>>({});
  const pendingRef = useRef<WsMessage[]>([]);
  const dirtyRef = useRef(false);

  const handleMessage = useCallback((msg: WsMessage) => {
    pendingRef.current.push(msg);
    dirtyRef.current = true;
  }, []);

  // Batch-flush pending messages to React state at ~10fps
  useEffect(() => {
    const timer = setInterval(() => {
      if (!dirtyRef.current) return;
      const pending = pendingRef.current;
      pendingRef.current = [];
      dirtyRef.current = false;

      setData((prev) => {
        const next = { ...prev };
        for (const msg of pending) {
          const { channel, timestamp, data: fields } = msg;
          if (!next[channel]) next[channel] = {};
          // Shallow-copy channel object so React detects the change
          const chData = { ...next[channel] };
          for (const [field, value] of Object.entries(fields)) {
            if (typeof value !== 'number') continue;
            const existing = chData[field];
            if (existing) {
              // Push to existing arrays (mutation is OK — chData is already a shallow copy)
              existing.timestamps.push(timestamp);
              existing.values.push(value);
              if (existing.timestamps.length > MAX_POINTS) {
                const excess = existing.timestamps.length - MAX_POINTS;
                existing.timestamps.splice(0, excess);
                existing.values.splice(0, excess);
              }
            } else {
              chData[field] = { timestamps: [timestamp], values: [value] };
            }
          }
          next[channel] = chData;
        }
        return next;
      });
    }, 100); // 10fps flush
    return () => clearInterval(timer);
  }, []);

  return { data, handleMessage };
}
