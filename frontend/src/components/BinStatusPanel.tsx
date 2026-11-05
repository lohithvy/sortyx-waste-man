import styles from '../styles/BinStatus.module.css';
import { useAppState } from '../state/AppStateContext';
import BinStatusCard from './BinStatusCard';

export default function BinStatusPanel() {
  const { state } = useAppState();

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        {/* Recycle icon */}
        <span className={styles.panelIcon}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
        </span>
        <span className={styles.panelTitle}>Bin Status</span>
      </div>

      {state.binStatuses.map((bin) => (
        <BinStatusCard key={bin.id} bin={bin} />
      ))}
    </div>
  );
}
