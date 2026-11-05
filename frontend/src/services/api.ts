const API_BASE = import.meta.env.VITE_API_URL ?? '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

import type { SystemStatus, BinStatus, DailyStats } from '../types';

export function getSystemStatus(): Promise<SystemStatus> {
  return request('/api/status');
}

export function getBinStatuses(): Promise<BinStatus[]> {
  return request('/api/bins');
}

export function getTodayStats(): Promise<DailyStats> {
  return request('/api/stats/today');
}

export function triggerEmergencyStop(): Promise<{ success: boolean }> {
  return request('/api/emergency-stop', { method: 'POST' });
}
