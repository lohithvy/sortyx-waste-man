import styles from '../styles/IdleScreen.module.css';
import waitingImage from '../assets/Sortyx1.jpg';

export default function IdleScreen() {
  return (
    <div className={styles.container}>
      <img
        src={waitingImage}
        alt="Sortyx 2.0 — Waiting for waste"
        className={styles.image}
      />
    </div>
  );
}
