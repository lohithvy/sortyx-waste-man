import styles from '../styles/StatsBar.module.css';
import { useAppState } from '../state/AppStateContext';

export default function StatsBar() {
  const { state } = useAppState();
  const s = state.dailyStats;

  return (
    <div className={styles.bar}>
      {/* Left label */}
      <div className={styles.label}>
        <div className={styles.labelTitle}>
          <span className={styles.labelIcon}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
            </svg>
          </span>
          Today's Stats
        </div>
        <div className={styles.labelSub}>Waste sorted today</div>
      </div>

      {/* Stats */}
      <div className={styles.stats}>
        {/* Total */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconTotal}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.totalItems}</span>
            <span className={styles.statLabel}>Items Sorted</span>
          </div>
        </div>

        {/* Food Waste */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconFoodWaste}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.5S2 11.5 2 13.5s1.75 3.75 1.75 3.75" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.foodWaste ?? s.organic ?? 0}</span>
            <span className={styles.statLabel}>Food Waste</span>
          </div>
        </div>

        {/* Recyclable */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconRecyclable}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.recyclable ?? s.bio ?? 0}</span>
            <span className={styles.statLabel}>Recyclable</span>
          </div>
        </div>

        {/* Non-Recyclable */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconNonRecyclable}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.nonRecyclable ?? s.nonBio ?? 0}</span>
            <span className={styles.statLabel}>Non-Recyclable</span>
          </div>
        </div>
      </div>
    </div>
  );
}
