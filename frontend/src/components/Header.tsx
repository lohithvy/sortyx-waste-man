import styles from '../styles/Header.module.css';
import { useAppState } from '../state/AppStateContext';
import { useCurrentTime } from '../hooks/useCurrentTime';
import logoImg from '../assets/SortyxLogo.jpg';

export default function Header() {
  const { state } = useAppState();
  const { time, date } = useCurrentTime();
  const online = state.wsConnected || state.systemStatus.isOnline;

  return (
    <header className={styles.header}>
      {/* Left — Brand */}
      <div className={styles.brand}>
        <img src={logoImg} alt="Sortyx" className={styles.logo} />
        <div className={styles.brandText}>
          <span className={styles.title}>Sortyx 2.0</span>
          <span className={styles.subtitle}>AI Waste Sorting System</span>
        </div>
      </div>

      {/* Center — Status */}
      {state.quotaStatus.quotaExceeded ? (
        <div className={`${styles.statusBadge} ${styles.statusWarning}`} title={state.quotaStatus.message}>
          <span className={styles.statusDotWarning} />
          AI Quota Standby{state.quotaStatus.retryAfterSeconds > 0 ? ` (${state.quotaStatus.retryAfterSeconds}s)` : ''}
        </div>
      ) : (
        <div
          className={`${styles.statusBadge} ${online ? styles.statusOnline : styles.statusOffline}`}
        >
          <span className={styles.statusDot} />
          {online ? 'System Online' : 'System Offline'}
        </div>
      )}

      {/* Right — Info */}
      <div className={styles.info}>
        {/* WiFi icon */}
        <span className={styles.wifiIcon} title="Network">
          {/* SVG WiFi */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12.55a11 11 0 0 1 14.08 0" />
            <path d="M1.42 9a16 16 0 0 1 21.16 0" />
            <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
            <line x1="12" y1="20" x2="12.01" y2="20" />
          </svg>
        </span>

        {/* Time / Date */}
        <div className={styles.timeBlock}>
          <div className={styles.time}>{time}</div>
          <div className={styles.date}>{date}</div>
        </div>

        {/* Settings gear */}
        <button className={styles.settingsBtn} title="Settings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    </header>
  );
}
