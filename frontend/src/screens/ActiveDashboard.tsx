import styles from '../styles/ActiveDashboard.module.css';
import Header from '../components/Header';
import BinStatusPanel from '../components/BinStatusPanel';
import CameraFeed from '../components/CameraFeed';
import DetectedWastePanel from '../components/DetectedWastePanel';
import StatsBar from '../components/StatsBar';
import SortingSuccessOverlay from '../components/SortingSuccessOverlay';
import AdScreensaver from '../components/AdScreensaver';
import { useAppState } from '../state/AppStateContext';

export default function ActiveDashboard() {
  const { state } = useAppState();

  return (
    <>
      <div className={`${styles.dashboard} ${state.sortingSuccess ? styles.blurred : ''}`}>
        <div className={styles.header}>
          <Header />
        </div>
        <div className={styles.left}>
          <BinStatusPanel />
        </div>
        <div className={styles.center}>
          <CameraFeed />
        </div>
        <div className={styles.right}>
          <DetectedWastePanel />
        </div>
        <div className={styles.bottom}>
          <StatsBar />
        </div>
      </div>

      {state.sortingSuccess && <SortingSuccessOverlay />}
      <AdScreensaver />
    </>
  );
}
