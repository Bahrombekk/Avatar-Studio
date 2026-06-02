/* Analitika tiplari (/api/analytics + fallback). */

export interface AnalyticsTotals {
  sessions: number;
  avgLatency: number;
  cacheRate: number;
  csat: number;
  uptime: number;
}

export interface LatencyStage {
  stage: string;
  value: number;
  color: string;
}

export interface DailyPoint {
  d: string;
  sessions: number;
  latency: number;
}

export interface TopQuery {
  q: string;
  n: number;
  cached: boolean;
}

export interface Analytics {
  totals: AnalyticsTotals;
  latencyBreakdown: LatencyStage[];
  daily: DailyPoint[];
  topQueries: TopQuery[];
}
