import {
  createContext,
  useContext,
  useReducer,
  useEffect,
  type ReactNode,
  type Dispatch,
} from 'react';
import {
  SystemState,
  type BinStatus,
  type ClassificationResult,
  type SortingProgress,
  type DailyStats,
  type SystemStatus,
  type QuotaStatus,
} from '../types';
import { useWebSocket } from '../hooks/useWebSocket';

/* ── State shape ─────────────────────────────────────────────────── */

export interface AppState {
  systemState: SystemState;
  binStatuses: BinStatus[];
  classificationResult: ClassificationResult | null;
  sortingProgress: SortingProgress;
  dailyStats: DailyStats;
  systemStatus: SystemStatus;
  quotaStatus: QuotaStatus;
  wsConnected: boolean;
  frozenImageUrl: string | null;
  repositionMessage: string | null;
  sortingSuccess: boolean;
}

const defaultBins: BinStatus[] = [
  {
    id: 'food_waste',
    binNumber: 1,
    category: 'food_waste',
    displayName: 'Food Waste',
    title: 'BIN 1 – FOOD WASTE',
    fillPercentage: 0,
    sensorStatus: 'not_configured',
    weightKg: null,
    weightDisplay: 'Not Calibrated',
    isCalibrated: false,
    loadCellConnected: false,
    loadCellStatus: 'Load Cell Disconnected',
  },
  {
    id: 'recyclable',
    binNumber: 2,
    category: 'recyclable',
    displayName: 'Recyclable',
    title: 'BIN 2 – RECYCLABLE',
    fillPercentage: 0,
    sensorStatus: 'not_configured',
    weightKg: null,
    weightDisplay: 'Not Calibrated',
    isCalibrated: false,
    loadCellConnected: false,
    loadCellStatus: 'Load Cell Disconnected',
  },
  {
    id: 'non_recyclable',
    binNumber: 3,
    category: 'non_recyclable',
    displayName: 'Non-Recyclable',
    title: 'BIN 3 – NON-RECYCLABLE',
    fillPercentage: 0,
    sensorStatus: 'not_configured',
    weightKg: null,
    weightDisplay: 'Not Calibrated',
    isCalibrated: false,
    loadCellConnected: false,
    loadCellStatus: 'Load Cell Disconnected',
  },
];

const defaultProgress: SortingProgress = {
  objectDetected: false,
  classified: false,
  binOpening: false,
  waitingForDeposit: false,
  closingBin: false,
};

const defaultQuota: QuotaStatus = {
  quotaExceeded: false,
  message: '',
  retryAfterSeconds: 0,
};

const initialState: AppState = {
  systemState: SystemState.Idle,
  binStatuses: defaultBins,
  classificationResult: null,
  sortingProgress: defaultProgress,
  dailyStats: {
    totalItems: 0,
    foodWaste: 0,
    recyclable: 0,
    nonRecyclable: 0,
    organic: 0,
    bio: 0,
    nonBio: 0,
  },
  systemStatus: {
    state: SystemState.Idle,
    isOnline: false,
    deviceConnected: false,
    cameraActive: false,
  },
  quotaStatus: defaultQuota,
  wsConnected: false,
  frozenImageUrl: null,
  repositionMessage: null,
  sortingSuccess: false,
};

/* ── Actions ─────────────────────────────────────────────────────── */

export type AppAction =
  | { type: 'SET_SYSTEM_STATE'; payload: SystemState }
  | { type: 'SET_BIN_STATUSES'; payload: BinStatus[] }
  | { type: 'UPDATE_BIN'; payload: BinStatus }
  | { type: 'SET_CLASSIFICATION'; payload: ClassificationResult | null }
  | { type: 'SET_SORTING_PROGRESS'; payload: Partial<SortingProgress> }
  | { type: 'RESET_SORTING_PROGRESS' }
  | { type: 'SET_DAILY_STATS'; payload: DailyStats }
  | { type: 'SET_SYSTEM_STATUS'; payload: Partial<SystemStatus> }
  | { type: 'SET_QUOTA_STATUS'; payload: QuotaStatus }
  | { type: 'SET_WS_CONNECTED'; payload: boolean }
  | { type: 'SET_FROZEN_IMAGE'; payload: string | null }
  | { type: 'SET_REPOSITION_MESSAGE'; payload: string | null }
  | { type: 'TRIGGER_SORTING_SUCCESS' }
  | { type: 'CLEAR_SORTING_SUCCESS' }
  | { type: 'FULL_STATE_UPDATE'; payload: Partial<AppState> };

function getCanonicalBinNumber(b: any): 1 | 2 | 3 {
  if (!b) return 1;
  const cat = (b.category || b.id || b.bin || '').toString().toLowerCase().replace('-', '_');
  if (cat.includes('non')) return 3;
  if (cat.includes('recyclable') || cat.includes('bio')) return 2;
  if (cat.includes('food') || cat.includes('organic')) return 1;
  const num = Number(b.binNumber ?? b.bin_number);
  if (num === 2) return 2;
  if (num === 3) return 3;
  return 1;
}

function mergeBinData(base: BinStatus, incoming: any): BinStatus {
  const isCalibrated = Boolean(incoming.isCalibrated ?? incoming.is_calibrated ?? base.isCalibrated);
  const weightKg = incoming.weightKg ?? incoming.weight_kg ?? (isCalibrated ? base.weightKg : null);
  const weightDisplay =
    incoming.weightDisplay ??
    incoming.weight_display ??
    (isCalibrated && weightKg != null ? `${Number(weightKg).toFixed(2)} kg` : 'Not Calibrated');
  const loadCellConnected = Boolean(incoming.loadCellConnected ?? incoming.load_cell_connected ?? false);
  const loadCellStatus =
    incoming.loadCellStatus ??
    incoming.load_cell_status ??
    (loadCellConnected ? 'Load Cell Connected' : 'Load Cell Disconnected');

  return {
    ...base,
    fillPercentage:
      incoming.fillPercentage !== undefined
        ? Number(incoming.fillPercentage)
        : incoming.fill_percentage !== undefined
        ? Number(incoming.fill_percentage)
        : base.fillPercentage,
    sensorStatus: incoming.sensorStatus ?? incoming.sensor_status ?? base.sensorStatus,
    weightKg: weightKg != null ? Number(weightKg) : null,
    weightDisplay,
    isCalibrated,
    loadCellConnected,
    loadCellStatus,
  };
}

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_SYSTEM_STATE': {
      const isIdle = action.payload === SystemState.Idle;
      return {
        ...state,
        systemState: action.payload,
        systemStatus: { ...state.systemStatus, state: action.payload },
        frozenImageUrl: isIdle ? null : state.frozenImageUrl,
        repositionMessage: isIdle ? null : state.repositionMessage,
      };
    }

    case 'SET_FROZEN_IMAGE':
      return { ...state, frozenImageUrl: action.payload };

    case 'SET_REPOSITION_MESSAGE':
      return { ...state, repositionMessage: action.payload };

    case 'SET_QUOTA_STATUS':
      return { ...state, quotaStatus: action.payload };

    case 'SET_BIN_STATUSES': {
      if (!Array.isArray(action.payload)) return state;
      const updated = state.binStatuses.map((base) => {
        const found = action.payload.find((p: any) => getCanonicalBinNumber(p) === base.binNumber);
        return found ? mergeBinData(base, found) : base;
      });
      return { ...state, binStatuses: updated };
    }

    case 'UPDATE_BIN': {
      const targetSlot = getCanonicalBinNumber(action.payload);
      const updated = state.binStatuses.map((base) =>
        base.binNumber === targetSlot ? mergeBinData(base, action.payload) : base,
      );
      return { ...state, binStatuses: updated };
    }

    case 'SET_CLASSIFICATION':
      return { ...state, classificationResult: action.payload };

    case 'SET_SORTING_PROGRESS':
      return { ...state, sortingProgress: { ...state.sortingProgress, ...action.payload } };

    case 'RESET_SORTING_PROGRESS':
      return { ...state, sortingProgress: defaultProgress };

    case 'SET_DAILY_STATS':
      return { ...state, dailyStats: action.payload };

    case 'SET_SYSTEM_STATUS':
      return { ...state, systemStatus: { ...state.systemStatus, ...action.payload } };

    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.payload, systemStatus: { ...state.systemStatus, isOnline: action.payload } };

    case 'TRIGGER_SORTING_SUCCESS':
      return { ...state, sortingSuccess: true };

    case 'CLEAR_SORTING_SUCCESS':
      return { ...state, sortingSuccess: false };

    case 'FULL_STATE_UPDATE': {
      const next = { ...state };
      if (action.payload.systemState !== undefined) next.systemState = action.payload.systemState;
      if (action.payload.binStatuses && Array.isArray(action.payload.binStatuses)) {
        next.binStatuses = state.binStatuses.map((base) => {
          const found = (action.payload.binStatuses as any[])?.find((p: any) => getCanonicalBinNumber(p) === base.binNumber);
          return found ? mergeBinData(base, found) : base;
        });
      }
      if (action.payload.classificationResult !== undefined) next.classificationResult = action.payload.classificationResult;
      if (action.payload.sortingProgress) next.sortingProgress = { ...next.sortingProgress, ...action.payload.sortingProgress };
      if (action.payload.dailyStats) next.dailyStats = action.payload.dailyStats;
      if (action.payload.systemStatus) next.systemStatus = { ...next.systemStatus, ...action.payload.systemStatus };
      if (action.payload.frozenImageUrl !== undefined) next.frozenImageUrl = action.payload.frozenImageUrl;
      if (action.payload.repositionMessage !== undefined) next.repositionMessage = action.payload.repositionMessage;
      return next;
    }

    default:
      return state;
  }
}

/* ── Context ─────────────────────────────────────────────────────── */

interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
}

const AppStateContext = createContext<AppContextValue | undefined>(undefined);

/* ── Provider ────────────────────────────────────────────────────── */

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // WebSocket connection
  useWebSocket(dispatch);

  // Fetch initial data on mount
  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL ?? '';

    async function fetchInitial() {
      try {
        const [statusRes, binsRes, statsRes] = await Promise.allSettled([
          fetch(`${apiUrl}/api/status`),
          fetch(`${apiUrl}/api/bins`),
          fetch(`${apiUrl}/api/stats/today`),
        ]);

        if (statusRes.status === 'fulfilled' && statusRes.value.ok) {
          const data = await statusRes.value.json();
          dispatch({ type: 'SET_SYSTEM_STATUS', payload: data });
          if (data.state) dispatch({ type: 'SET_SYSTEM_STATE', payload: data.state });
          if (data.gemini_quota) {
            dispatch({
              type: 'SET_QUOTA_STATUS',
              payload: {
                quotaExceeded: Boolean(data.gemini_quota.quota_exceeded),
                message: data.gemini_quota.message || '',
                retryAfterSeconds: Number(data.gemini_quota.retry_after_seconds || 0),
              },
            });
          }
        }
        if (binsRes.status === 'fulfilled' && binsRes.value.ok) {
          const data = await binsRes.value.json();
          dispatch({ type: 'SET_BIN_STATUSES', payload: data });
        }
        if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
          const data = await statsRes.value.json();
          const foodWaste = Number(
            data.foodWaste ?? data.food_waste_count ?? data.organic ?? data.organic_count ?? 0,
          );
          const recyclable = Number(
            data.recyclable ?? data.recyclable_count ?? data.bio ?? data.bio_count ?? 0,
          );
          const nonRecyclable = Number(
            data.nonRecyclable ?? data.non_recyclable_count ?? data.nonBio ?? data.non_bio_count ?? 0,
          );
          const total = Number(
            data.totalItems ?? data.total_items ?? (foodWaste + recyclable + nonRecyclable),
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
        }
      } catch {
        // Backend not available yet — will sync via WS later
      }
    }
    fetchInitial();
  }, []);

  return (
    <AppStateContext.Provider value={{ state, dispatch }}>
      {children}
    </AppStateContext.Provider>
  );
}

/* ── Hook ────────────────────────────────────────────────────────── */

export function useAppState(): AppContextValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}
