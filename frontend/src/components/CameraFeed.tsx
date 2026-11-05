import { useState, useEffect } from 'react';
import styles from '../styles/CameraFeed.module.css';
import { useAppState } from '../state/AppStateContext';
import { SystemState } from '../types';
import DepositInstruction from './DepositInstruction';

interface CameraDevice {
  index: number;
  name: string;
  is_external: boolean;
  is_virtual: boolean;
  is_active: boolean;
}

interface CameraStatus {
  is_connected: boolean;
  index: number;
  device_name: string;
  resolution: string;
  fps: number;
}

export default function CameraFeed() {
  const { state } = useAppState();
  const [streamActive, setStreamActive] = useState(true);
  const [devices, setDevices] = useState<CameraDevice[]>([]);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus | null>(null);
  const [switching, setSwitching] = useState(false);
  const result = state.classificationResult;

  const isAnalyzing = [
    SystemState.ImageCapture,
    SystemState.Classifying,
  ].includes(state.systemState);

  const showDetection =
    result &&
    [
      SystemState.ClassificationResult,
      SystemState.ServoOpening,
      SystemState.AwaitingDeposit,
      SystemState.LidClosing,
    ].includes(state.systemState);

  const showDeposit = [
    SystemState.AwaitingDeposit,
    SystemState.ServoOpening,
  ].includes(state.systemState);

  // Fetch camera devices and status
  const fetchCameraInfo = async () => {
    try {
      const [devRes, statusRes] = await Promise.all([
        fetch('/api/camera/devices'),
        fetch('/api/camera/status'),
      ]);
      if (devRes.ok) {
        const devs = await devRes.json();
        setDevices(devs);
      }
      if (statusRes.ok) {
        const stat = await statusRes.json();
        setCameraStatus(stat);
      }
    } catch {
      // Ignore network errors in local dev
    }
  };

  useEffect(() => {
    fetchCameraInfo();
    const interval = setInterval(fetchCameraInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDeviceChange = async (newIndex: number) => {
    setSwitching(true);
    try {
      const res = await fetch('/api/camera/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: newIndex }),
      });
      if (res.ok) {
        await fetchCameraInfo();
      }
    } finally {
      setSwitching(false);
    }
  };

  const handleReconnect = async () => {
    setSwitching(true);
    try {
      await fetch('/api/camera/reconnect', { method: 'POST' });
      await fetchCameraInfo();
    } finally {
      setSwitching(false);
    }
  };

  const categoryIcon =
    result?.category === 'organic'
      ? '🍃'
      : result?.category === 'bio'
      ? '📄'
      : '♻️';

  const confidencePct = result
    ? Math.round(result.confidence <= 1 ? result.confidence * 100 : result.confidence)
    : 0;

  return (
    <div className={styles.wrapper}>
      {/* Device Selector & Hardware Status Bar */}
      <div className={styles.cameraControlsBar}>
        <div className={styles.cameraDeviceGroup}>
          <span className={styles.cameraLabel}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
            Camera:
          </span>
          <select
            className={styles.cameraSelect}
            value={cameraStatus?.index ?? 0}
            onChange={(e) => handleDeviceChange(Number(e.target.value))}
            disabled={switching}
          >
            {devices.length > 0 ? (
              devices.map((dev) => (
                <option key={dev.index} value={dev.index}>
                  {dev.name} {dev.is_external ? '(USB)' : '(Built-in)'}
                </option>
              ))
            ) : (
              <option value={0}>USB Camera (Index 0)</option>
            )}
          </select>
        </div>

        <div className={styles.cameraInfoPill}>
          <div className={styles.statusDot} />
          <span>{cameraStatus?.resolution || '1280x720'} • {cameraStatus?.fps || 30} FPS</span>
          <button
            className={styles.reconnectButton}
            onClick={handleReconnect}
            title="Reconnect Camera"
            disabled={switching}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            {switching ? 'Resetting...' : 'Reconnect'}
          </button>
        </div>
      </div>

      <div className={styles.container}>
        {/* Badges */}
        {isAnalyzing ? (
          <div className={`${styles.badge} ${styles.badgeAnalyzing}`}>
            <div className={styles.pulseDot} />
            Analyzing Waste (~2s)
          </div>
        ) : (
          <div className={`${styles.badge} ${styles.badgeLive}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
            Live Detection
          </div>
        )}

        {state.quotaStatus?.quotaExceeded ? (
          <div className={`${styles.badge} ${styles.badgeQuota}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            AI Standby
          </div>
        ) : (
          <div className={`${styles.badge} ${styles.badgeAI}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
            Cloud Run AI
          </div>
        )}

        {/* Reposition Banner */}
        {state.repositionMessage && !isAnalyzing && (
          <div className={styles.repositionBanner}>
            <span className={styles.repositionIcon}>⚠️</span>
            <span>{state.repositionMessage}</span>
          </div>
        )}

        {/* Corner brackets */}
        <div className={styles.corners}>
          <div className={`${styles.corner} ${styles.cornerTL}`} />
          <div className={`${styles.corner} ${styles.cornerTR}`} />
          <div className={`${styles.corner} ${styles.cornerBL}`} />
          <div className={`${styles.corner} ${styles.cornerBR}`} />
        </div>

        {/* Live Camera Feed: Never frozen, streams continuously at 30 FPS */}
        {streamActive ? (
          <img
            src="/api/camera/stream"
            alt="Sortyx Live Camera"
            className={styles.feedImage}
            onError={() => setStreamActive(false)}
            onLoad={() => setStreamActive(true)}
          />
        ) : (
          <div className={styles.placeholder}>
            <span className={styles.placeholderIcon}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                <circle cx="12" cy="13" r="4"/>
              </svg>
            </span>
            <span className={styles.placeholderText}>Camera Feed — Sortyx 2.0</span>
          </div>
        )}

        {/* Analyzing Waste Overlay (Renders on top without freezing video stream) */}
        {isAnalyzing && (
          <div className={styles.analyzingOverlay}>
            <div className={styles.spinner} />
            <div className={styles.analyzingText}>Analyzing waste...</div>
            <div className={styles.analyzingSub}>Sortyx Cloud AI identifying item (~2s)</div>
          </div>
        )}

        {/* Bounding box around detected waste */}
        {showDetection && result && (
          <div className={styles.boundingBox}>
            <div className={styles.detectionTag}>
              <span className={styles.tagIcon}>{categoryIcon}</span>
              <span className={styles.tagName}>{result.wasteName}</span>
              <span className={styles.tagConf}>{confidencePct}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Deposit instruction */}
      {showDeposit ? (
        <DepositInstruction />
      ) : (
        <div className={styles.depositArea}>
          <span className={styles.depositIcon}>🗑️</span>
          <span className={styles.depositTitle}>Deposit Your Waste</span>
          <span className={styles.depositSub}>Place the item in front of the camera</span>
        </div>
      )}
    </div>
  );
}
