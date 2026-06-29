export interface ChannelSchema {
  path: string;
  type: string;
}

export interface ChannelInfo {
  name: string;
  frame_rate: number;
  field_count: number;
}

export interface WsMessage {
  channel: string;
  timestamp: number;
  data: Record<string, number>;
}

export interface PlotSeries {
  channel: string;
  field: string;
  label: string;
  color: string;
}

export interface PlotPanelConfig {
  id: string;
  title: string;
  series: PlotSeries[];
}
