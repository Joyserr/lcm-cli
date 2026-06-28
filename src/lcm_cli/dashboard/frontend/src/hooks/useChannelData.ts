import { useState, useCallback } from 'react';
import type { WsMessage } from '../types';

const MAX_POINTS = 50000;

interface ChannelFieldData {
  timestamps: number[];
  values: number[];
}

export function useChannelData() {
  const [data, setData] = useState<Record<string, Record<string, ChannelFieldData>>>({});

  const handleMessage = useCallback((msg: WsMessage) => {
    const { channel, timestamp, data: fields } = msg;
    setData((prev) => {
      const next = { ...prev };
      if (!next[channel]) next[channel] = {};
      const chData = { ...next[channel] };
      for (const [field, value] of Object.entries(fields)) {
        if (typeof value !== 'number') continue;
        if (!chData[field]) chData[field] = { timestamps: [], values: [] };
        const fd = chData[field];
        fd.timestamps.push(timestamp);
        fd.values.push(value);
        if (fd.timestamps.length > MAX_POINTS) {
          fd.timestamps = fd.timestamps.slice(-MAX_POINTS);
          fd.values = fd.values.slice(-MAX_POINTS);
        }
      }
      next[channel] = chData;
      return next;
    });
  }, []);

  return { data, handleMessage };
}
