import styles from '../styles/ActiveDashboard.module.css';
import Header from '../components/Header';
import BinStatusPanel from '../components/BinStatusPanel';
import CameraFeed from '../components/CameraFeed';
import DetectedWastePanel from '../components/DetectedWastePanel';
import StatsBar from '../components/StatsBar';

export default function ActiveDashboard() {
  return (
    <div className={styles.dashboard}>
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
  );
}
