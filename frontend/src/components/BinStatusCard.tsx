import styles from '../styles/BinStatus.module.css';
import type { BinStatus } from '../types';

interface Props {
  bin: BinStatus;
}

function getCategoryClasses(category: string) {
  switch (category) {
    case 'food_waste':
    case 'organic':
      return { icon: styles.iconFoodWaste, percent: styles.percentFoodWaste, fill: styles.fillFoodWaste };
    case 'recyclable':
    case 'bio':
      return { icon: styles.iconRecyclable, percent: styles.percentRecyclable, fill: styles.fillRecyclable };
    case 'non_recyclable':
    case 'non_bio':
    default:
      return { icon: styles.iconNonRecyclable, percent: styles.percentNonRecyclable, fill: styles.fillNonRecyclable };
  }
}

function CategoryIcon({ category }: { category: string }) {
  switch (category) {
    case 'food_waste':
    case 'organic':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.5S2 11.5 2 13.5s1.75 3.75 1.75 3.75" />
        </svg>
      );
    case 'recyclable':
    case 'bio':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      );
    case 'non_recyclable':
    case 'non_bio':
    default:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <line x1="10" y1="11" x2="10" y2="17" />
          <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
      );
  }
}

export default function BinStatusCard({ bin }: Props) {
  const cls = getCategoryClasses(bin.category);
  const notConfigured = bin.sensorStatus === 'not_configured';

  // Compute canonical title e.g. "BIN 1 – FOOD WASTE"
  const binNum = (bin.category === 'food_waste' || bin.category === 'organic')
    ? 1
    : (bin.category === 'recyclable' || bin.category === 'bio')
    ? 2
    : (bin.category === 'non_recyclable' || bin.category === 'non_bio')
    ? 3
    : (bin.binNumber === 2 ? 2 : bin.binNumber === 3 ? 3 : 1);
  const displayName = binNum === 1 ? 'Food Waste' : binNum === 2 ? 'Recyclable' : 'Non-Recyclable';
  const titleDisplay = `BIN ${binNum} – ${displayName.toUpperCase()}`;

  // Calibration and live weight formatting
  const isCalibrated = Boolean(bin.isCalibrated);
  const hasWeight = bin.weightKg != null && !isNaN(bin.weightKg);
  const weightText = isCalibrated && hasWeight
    ? `${bin.weightKg!.toFixed(2)} kg`
    : (bin.weightDisplay || 'Not Calibrated');

  // Load cell connection: strictly false unless verified connected
  const loadCellConnected = Boolean(bin.loadCellConnected);
  const loadCellText = bin.loadCellStatus || (loadCellConnected ? 'Load Cell Connected' : 'Load Cell Disconnected');

  return (
    <div className={styles.card}>
      {/* Header: Icon, Bin Title, Category Name, Optional Fill % */}
      <div className={styles.cardHeader}>
        <div className={styles.cardCategory}>
          <div className={`${styles.cardIcon} ${cls.icon}`}>
            <CategoryIcon category={bin.category} />
          </div>
          <div className={styles.cardTitleGroup}>
            <span className={styles.cardBinTitle}>{titleDisplay}</span>
            <span className={styles.cardName}>{displayName}</span>
          </div>
        </div>
        <span className={`${styles.cardPercent} ${cls.percent}`}>
          {notConfigured || bin.fillPercentage <= 0 ? '' : `${Math.round(bin.fillPercentage)}%`}
        </span>
      </div>

      {/* Weight section: Prominent Live Weight readout */}
      <div className={styles.weightSection}>
        <span className={styles.weightLabel}>Live weight</span>
        {isCalibrated && hasWeight ? (
          <span className={styles.weightValue}>{weightText}</span>
        ) : (
          <span className={styles.notCalibratedBadge}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {weightText}
          </span>
        )}
      </div>

      {/* Sensor connection status row */}
      <div className={styles.loadCellRow}>
        <span
          className={loadCellConnected ? styles.statusDotConnected : styles.statusDotDisconnected}
          aria-hidden="true"
        />
        <span className={styles.loadCellText}>{loadCellText}</span>
      </div>

      {/* Optional Ultrasonic fill progress */}
      {!notConfigured && bin.fillPercentage > 0 && (
        <div className={styles.progressTrack} title={`Fill Level: ${Math.round(bin.fillPercentage)}%`}>
          <div
            className={`${styles.progressFill} ${cls.fill}`}
            style={{ width: `${Math.min(100, Math.max(0, bin.fillPercentage))}%` }}
          />
        </div>
      )}
    </div>
  );
}
