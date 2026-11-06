import styles from '../styles/DetectedWaste.module.css';
import { useAppState } from '../state/AppStateContext';
import SortingProgress from './SortingProgress';
import ManualReviewAlert from './ManualReviewAlert';
import ErrorDisplay from './ErrorDisplay';
import { SystemState } from '../types';

function getCategoryBadgeClass(category?: string | null) {
  switch (category) {
    case 'food_waste':
    case 'organic': return styles.badgeFoodWaste;
    case 'recyclable':
    case 'bio': return styles.badgeRecyclable;
    case 'non_recyclable':
    case 'non_bio': return styles.badgeNonRecyclable;
    default: return styles.badgeNonRecyclable;
  }
}

function formatCategory(category?: string | null) {
  if (!category) return 'Manual Review';
  switch (category) {
    case 'food_waste':
    case 'organic': return 'Food Waste';
    case 'recyclable':
    case 'bio': return 'Recyclable';
    case 'non_recyclable':
    case 'non_bio': return 'Non-Recyclable';
    default: return category;
  }
}

export default function DetectedWastePanel() {
  const { state } = useAppState();
  const result = state.classificationResult;
  const isError = state.systemState === SystemState.Error;
  const isManualReview = state.systemState === SystemState.ManualReview;

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelIcon}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </span>
        <span className={styles.panelTitle}>Detected Waste</span>
      </div>

      {isError && <ErrorDisplay />}
      {isManualReview && <ManualReviewAlert />}

      {state.quotaStatus?.quotaExceeded && (
        <div className={styles.quotaNotice}>
          <div className={styles.quotaHeader}>
            <span className={styles.quotaIcon}>⏳</span>
            <span className={styles.quotaTitle}>AI Quota Standby</span>
          </div>
          <p className={styles.quotaDesc}>
            {state.quotaStatus.message || 'Gemini API free-tier daily limit reached. Standby active to prevent redundant calls.'}
          </p>
          {state.quotaStatus.retryAfterSeconds > 0 && (
            <div className={styles.quotaTimer}>
              Next attempt window in <strong>{state.quotaStatus.retryAfterSeconds}s</strong>
            </div>
          )}
        </div>
      )}

      {result || state.frozenImageUrl ? (
        <div className={styles.card}>
          {/* Thumbnail: directly shows captured frame immediately */}
          <div className={styles.thumbnail}>
            {state.frozenImageUrl || result?.imageUrl ? (
              <img
                src={state.frozenImageUrl || result?.imageUrl!}
                alt={result?.wasteName || 'Captured Waste Item'}
                className={styles.thumbnailImg}
              />
            ) : (
              <span className={styles.thumbnailPlaceholder}>
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </span>
            )}
          </div>

          {/* Waste name */}
          <div className={styles.wasteName}>
            {result?.wasteName || (state.systemState === SystemState.Classifying ? 'Analyzing Waste...' : 'Item Captured')}
          </div>

          {/* Category + confidence / Analyzing status */}
          <div className={styles.meta}>
            {result ? (
              <>
                <span className={`${styles.categoryBadge} ${getCategoryBadgeClass(result.category)}`}>
                  {formatCategory(result.category)}
                </span>
                <span className={styles.confidence}>
                  Confidence {Math.round(result.confidence <= 1 ? result.confidence * 100 : result.confidence)}%
                </span>
              </>
            ) : (
              <span className={styles.categoryBadge} style={{ background: '#f3e8ff', color: '#7c3aed' }}>
                AI Identifying...
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className={styles.emptyState}>
          <span className={styles.emptyIcon}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <span className={styles.emptyTitle}>No Waste Detected</span>
          <span className={styles.emptySub}>Place an item in front of the camera to begin</span>
        </div>
      )}

      {/* Sorting progress */}
      <SortingProgress />
    </div>
  );
}
