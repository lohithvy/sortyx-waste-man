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

        {/* Organic */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconOrganic}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.5S2 11.5 2 13.5s1.75 3.75 1.75 3.75" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.organic}</span>
            <span className={styles.statLabel}>Organic</span>
          </div>
        </div>

        {/* Bio */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconBio}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.bio}</span>
            <span className={styles.statLabel}>Bio</span>
          </div>
        </div>

        {/* Non-Bio */}
        <div className={styles.stat}>
          <div className={`${styles.statIcon} ${styles.statIconNonBio}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{s.nonBio}</span>
            <span className={styles.statLabel}>Non-Bio</span>
          </div>
        </div>
      </div>
    </div>
  );
}
