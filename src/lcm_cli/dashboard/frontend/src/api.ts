import type { ChannelSchema } from './types';

const BASE = '';

export async function fetchChannels(): Promise<string[]> {
  try {
    const res = await fetch(`${BASE}/api/channels`);
    return res.json();
  } catch {
    return [];
  }
}

export async function fetchSchema(channel: string): Promise<ChannelSchema[]> {
  try {
    const res = await fetch(`${BASE}/api/channels/${encodeURIComponent(channel)}/schema`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
