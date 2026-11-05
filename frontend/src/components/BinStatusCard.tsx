import styles from '../styles/BinStatus.module.css';
import type { BinStatus } from '../types';

interface Props {
  bin: BinStatus;
}

function getCategoryClasses(category: string) {
  switch (category) {
    case 'organic':
      return { icon: styles.iconOrganic, percent: styles.percentOrganic, fill: styles.fillOrganic };
    case 'bio':
      return { icon: styles.iconBio, percent: styles.percentBio, fill: styles.fillBio };
    case 'non_bio':
    default:
      return { icon: styles.iconNonBio, percent: styles.percentNonBio, fill: styles.fillNonBio };
  }
}

function CategoryIcon({ category }: { category: string }) {
  switch (category) {
    case 'organic':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.5S2 11.5 2 13.5s1.75 3.75 1.75 3.75" />
        </svg>
      );
    case 'bio':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      );
    default:
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      );
  }
}

export default function BinStatusCard({ bin }: Props) {
  const cls = getCategoryClasses(bin.category);
  const notConfigured = bin.sensorStatus === 'not_configured';

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardCategory}>
          <div className={`${styles.cardIcon} ${cls.icon}`}>
            <CategoryIcon category={bin.category} />
          </div>
          <span className={styles.cardName}>{bin.displayName}</span>
        </div>
        <span className={`${styles.cardPercent} ${cls.percent}`}>
          {notConfigured ? '—' : `${Math.round(bin.fillPercentage)}%`}
        </span>
      </div>

      <div className={styles.progressTrack}>
        <div
          className={`${styles.progressFill} ${cls.fill}`}
          style={{ width: notConfigured ? '0%' : `${bin.fillPercentage}%` }}
        />
      </div>

      {notConfigured && (
        <div className={styles.sensorStatus}>Sensor not configured</div>
      )}
      {bin.sensorStatus === 'ok' && (
        <div className={`${styles.sensorStatus} ${styles.sensorOk}`}>Sensor OK</div>
      )}
      {bin.sensorStatus === 'error' && (
        <div className={styles.sensorStatus} style={{ color: 'var(--color-error)' }}>
          Sensor Error
        </div>
      )}
    </div>
  );
}
