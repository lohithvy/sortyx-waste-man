/* ── Sortyx 2.0 — Shared TypeScript Types ────────────────────────── */

export enum SystemState {
  Idle = 'idle',
  PersonDetected = 'person_detected',
  CameraActive = 'camera_active',
  ImageCapture = 'image_capture',
  Classifying = 'classifying',
  ClassificationResult = 'classification_result',
  ServoOpening = 'servo_opening',
  AwaitingDeposit = 'awaiting_deposit',
  LidClosing = 'lid_closing',
  Error = 'error',
  ManualReview = 'manual_review',
}

export type WasteCategory = 'bio' | 'organic' | 'non_bio';

export interface BinStatus {
  id: string;
  category: WasteCategory;
  displayName: string;
  fillPercentage: number;
  sensorStatus: 'ok' | 'error' | 'not_configured';
}

export interface ClassificationResult {
  wasteName: string;
  category?: WasteCategory | null;
  confidence: number;
  reason: string;
  isHazardous: boolean;
  requiresManualReview: boolean;
  imageUrl?: string;
}

export interface SortingProgress {
  objectDetected: boolean;
  classified: boolean;
  binOpening: boolean;
  waitingForDeposit: boolean;
  closingBin: boolean;
}

export interface DailyStats {
  totalItems: number;
  organic: number;
  bio: number;
  nonBio: number;
}

export interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface SystemStatus {
  state: SystemState;
  isOnline: boolean;
  deviceConnected: boolean;
  cameraActive: boolean;
}

export interface QuotaStatus {
  quotaExceeded: boolean;
  message: string;
  retryAfterSeconds: number;
}
