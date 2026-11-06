import { useState, useEffect } from 'react';
import styles from '../styles/SortingSuccessOverlay.module.css';
import { useAppState } from '../state/AppStateContext';

export default function SortingSuccessOverlay() {
  const { dispatch } = useAppState();
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    // Keep it visible for exactly 2 seconds (2000ms)
    const holdTimer = setTimeout(() => {
      setFadingOut(true);
    }, 2000);

    return () => clearTimeout(holdTimer);
  }, []);

  useEffect(() => {
    if (fadingOut) {
      // Allow 300ms for smooth fade out before dismissing
      const fadeTimer = setTimeout(() => {
        dispatch({ type: 'CLEAR_SORTING_SUCCESS' });
      }, 300);

      return () => clearTimeout(fadeTimer);
    }
  }, [fadingOut, dispatch]);

  return (
    <div
      className={`${styles.overlay} ${fadingOut ? styles.overlayFadingOut : ''}`}
      role="alert"
      aria-live="assertive"
    >
      <div className={`${styles.card} ${fadingOut ? styles.cardFadingOut : ''}`}>
        <div className={styles.iconCircle}>
          <svg
            className={styles.checkIcon}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <h2 className={styles.title}>Waste Sorted Successfully!</h2>
        <p className={styles.subtitle}>Thank you for keeping the environment clean.</p>
      </div>
    </div>
  );
}

