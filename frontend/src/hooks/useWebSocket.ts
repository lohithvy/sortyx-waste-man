import { useEffect, useRef, useCallback, type Dispatch } from 'react';
import type { AppAction } from '../state/AppStateContext';
import { SystemState, type WSMessage } from '../types';

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const HEARTBEAT_INTERVAL_MS = 25000;

export function useWebSocket(dispatch: Dispatch<AppAction>) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const getWsUrl = useCallback(() => {
    const envUrl = import.meta.env.VITE_WS_URL;
    if (envUrl) return envUrl as string;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/ws`;
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = undefined;
    }
  }, []);

  const startHeartbeat = useCallback((ws: WebSocket) => {
    stopHeartbeat();
    heartbeatTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [stopHeartbeat]);

  /* ── Message handler ─────────────────────────────────────────── */

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case 'state_change':
        case 'state_update': {
          const p = ((msg.payload || msg) as any) || {};
          const rawState = (p.state) as SystemState;
          if (rawState) {
            dispatch({
              type: 'SET_SYSTEM_STATE',
              payload: rawState,
            });

            const ctx = p.context;
            if (ctx?.frozen_image_url) {
              dispatch({ type: 'SET_FROZEN_IMAGE', payload: ctx.frozen_image_url });
            }
            if (ctx?.reposition_message !== undefined) {
              dispatch({ type: 'SET_REPOSITION_MESSAGE', payload: ctx.reposition_message });
            }

            // Update sorting progress stepper based on system state
            if (rawState === SystemState.PersonDetected || rawState === SystemState.CameraActive) {
              dispatch({
                type: 'SET_SORTING_PROGRESS',
                payload: { objectDetected: true },
              });
            } else if (rawState === SystemState.ClassificationResult) {
              dispatch({
                type: 'SET_SORTING_PROGRESS',
                payload: { objectDetected: true, classified: true },
              });
            } else if (rawState === SystemState.ServoOpening) {
              dispatch({
                type: 'SET_SORTING_PROGRESS',
                payload: { objectDetected: true, classified: true, binOpening: true },
              });
            } else if (rawState === SystemState.AwaitingDeposit) {
              dispatch({
                type: 'SET_SORTING_PROGRESS',
                payload: { objectDetected: true, classified: true, binOpening: true, waitingForDeposit: true },
              });
            } else if (rawState === SystemState.LidClosing) {
              dispatch({
                type: 'SET_SORTING_PROGRESS',
                payload: { objectDetected: true, classified: true, binOpening: true, waitingForDeposit: true, closingBin: true },
              });
            } else if (rawState === SystemState.Idle) {
              dispatch({ type: 'RESET_SORTING_PROGRESS' });
              dispatch({ type: 'SET_CLASSIFICATION', payload: null });
              dispatch({ type: 'SET_FROZEN_IMAGE', payload: null });
              dispatch({ type: 'SET_REPOSITION_MESSAGE', payload: null });
            }
          }
          break;
        }

        case 'bin_update':
        case 'bin_status_update':
        case 'weight_update': {
          const p = ((msg.payload || msg) as any) || {};
          const binKey = p.bin_id || p.id || p.category;
          if (binKey) {
            dispatch({
              type: 'UPDATE_BIN',
              payload: {
                id: binKey,
                binNumber: p.bin_number ?? p.binNumber,
                category: (p.category || binKey).toLowerCase().replace('-', '_'),
                displayName: p.display_name || p.displayName || binKey,
                title: p.title,
                fillPercentage: Number(p.fill_percentage ?? p.fillPercentage ?? 0),
                sensorStatus: p.sensor_status || p.sensorStatus || 'ok',
                weightKg: p.weight_kg ?? p.weightKg ?? null,
                weightDisplay: p.weight_display ?? p.weightDisplay,
                isCalibrated: p.is_calibrated ?? p.isCalibrated,
                loadCellConnected: p.load_cell_connected ?? p.loadCellConnected,
                loadCellStatus: p.load_cell_status ?? p.loadCellStatus,
              },
            });
          }
          break;
        }

        case 'bins_status':
          dispatch({ type: 'SET_BIN_STATUSES', payload: msg.payload as never });
          break;

        case 'classification_result':
        case 'classification_update': {
          const p = msg.payload || msg;
          const imgUrl = (p as any).image_url || (p as any).imageUrl || (p as any).frozen_image_url;
          const mapped = {
            wasteName: (p as any).waste_name || (p as any).wasteName || 'Unknown Item',
            category: (p as any).category,
            confidence: (p as any).confidence,
            reason: (p as any).reason,
            isHazardous: Boolean((p as any).is_hazardous || (p as any).isHazardous),
            requiresManualReview: Boolean((p as any).requires_manual_review || (p as any).requiresManualReview),
            binId: (p as any).bin_id || (p as any).binId,
            imageUrl: imgUrl,
          };
          dispatch({ type: 'SET_CLASSIFICATION', payload: mapped as never });
          if (imgUrl) {
            dispatch({ type: 'SET_FROZEN_IMAGE', payload: imgUrl });
          }
          dispatch({
            type: 'SET_SORTING_PROGRESS',
            payload: { objectDetected: true, classified: true },
          });
          break;
        }

        case 'sorting_progress':
          dispatch({
            type: 'SET_SORTING_PROGRESS',
            payload: msg.payload as never,
          });
          break;

        case 'sorting_success':
        case 'sorting_completed':
          dispatch({ type: 'TRIGGER_SORTING_SUCCESS' });
          break;

        case 'quota_update': {
          const p = (msg.payload || msg) as any;
          dispatch({
            type: 'SET_QUOTA_STATUS',
            payload: {
              quotaExceeded: Boolean(p.quota_exceeded ?? p.quotaExceeded),
              message: p.message || '',
              retryAfterSeconds: Number(p.retry_after_seconds ?? p.retryAfterSeconds ?? 0),
            },
          });
          break;
        }

        case 'error': {
          const p = (msg.payload || msg) as any;
          if (p.error_code === 'GEMINI_QUOTA_EXCEEDED') {
            dispatch({
              type: 'SET_QUOTA_STATUS',
              payload: {
                quotaExceeded: true,
                message: p.message || 'Gemini AI free-tier daily quota limit reached.',
                retryAfterSeconds: Number(p.retry_delay_seconds || 300),
              },
            });
          }
          break;
        }

        case 'daily_stats': {
          const p = ((msg.payload || msg) as any) || {};
          const foodWaste = Number(
            p.foodWaste ?? p.food_waste_count ?? p.food_waste ?? p.organic ?? p.organic_count ?? 0,
          );
          const recyclable = Number(
            p.recyclable ?? p.recyclable_count ?? p.recyclable ?? p.bio ?? p.bio_count ?? 0,
          );
          const nonRecyclable = Number(
            p.nonRecyclable ?? p.non_recyclable_count ?? p.non_recyclable ?? p.nonBio ?? p.non_bio_count ?? 0,
          );
          const total = Number(
            p.totalItems ?? p.total_items ?? (foodWaste + recyclable + nonRecyclable),
          );
          dispatch({
            type: 'SET_DAILY_STATS',
            payload: {
              totalItems: total,
              foodWaste,
              recyclable,
              nonRecyclable,
              organic: foodWaste,
              bio: recyclable,
              nonBio: nonRecyclable,
            },
          });
          break;
        }

        case 'system_status':
          dispatch({ type: 'SET_SYSTEM_STATUS', payload: msg.payload as never });
          break;

        case 'full_state':
          dispatch({ type: 'FULL_STATE_UPDATE', payload: msg.payload as never });
          break;

        case 'idle':
          dispatch({ type: 'SET_SYSTEM_STATE', payload: SystemState.Idle });
          dispatch({ type: 'SET_CLASSIFICATION', payload: null });
          dispatch({ type: 'RESET_SORTING_PROGRESS' });
          dispatch({ type: 'SET_FROZEN_IMAGE', payload: null });
          dispatch({ type: 'SET_REPOSITION_MESSAGE', payload: null });
          break;

        case 'pong':
          // heartbeat ack
          break;

        default:
          console.debug('[WS] Message received:', msg.type);
      }
    },
    [dispatch],
  );

  /* ── Connect ─────────────────────────────────────────────────── */

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) return;

    const url = getWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.info('[WS] Connected to', url);
      reconnectAttempt.current = 0;
      dispatch({ type: 'SET_WS_CONNECTED', payload: true });
      startHeartbeat(ws);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleMessage(data);
      } catch {
        // Plain text message (e.g. pong)
        if (event.data === 'pong') {
          // heartbeat ack
        }
      }
    };

    ws.onerror = (err) => {
      console.warn('[WS] Error:', err);
    };

    ws.onclose = () => {
      console.info('[WS] Disconnected');
      dispatch({ type: 'SET_WS_CONNECTED', payload: false });
      stopHeartbeat();
      wsRef.current = null;

      // Exponential backoff reconnect
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** reconnectAttempt.current,
        RECONNECT_MAX_MS,
      );
      reconnectAttempt.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };
  }, [getWsUrl, dispatch, startHeartbeat, stopHeartbeat, handleMessage]);

  useEffect(() => {
    connect();

    return () => {
      stopHeartbeat();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, stopHeartbeat]);

  return { isConnected: wsRef.current?.readyState === WebSocket.OPEN };
}
