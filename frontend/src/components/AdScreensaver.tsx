import { useEffect, useRef, useState, useCallback } from 'react';
import styles from '../styles/AdScreensaver.module.css';
import { useAppState } from '../state/AppStateContext';
import { SystemState } from '../types';

const IDLE_DELAY_MS = 2500; // 2.5s of continuous idle before video resumes
const LOGO_SRC = '/assets/SortyxLogo.jpg'; // Vite asset or fallback

export default function AdScreensaver() {
  const { state } = useAppState();
  const [isVisible, setIsVisible] = useState<boolean>(true);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startVideo = useCallback(() => {
    if (videoRef.current) {
      videoRef.current.currentTime = videoRef.current.currentTime || 0;
      const playPromise = videoRef.current.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          // Autoplay with muted is allowed by all modern browsers
          console.debug('[AdScreensaver] Autoplay prevented:', err);
        });
      }
    }
  }, []);

  const pauseVideo = useCallback(() => {
    if (videoRef.current) {
      videoRef.current.pause();
    }
  }, []);

  useEffect(() => {
    // If not in IDLE state (e.g. hand detected, camera active, sorting, lid closing, etc.):
    // Immediately hide the ad video and open the project dashboard!
    if (state.systemState !== SystemState.Idle) {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
      setIsVisible(false);
      pauseVideo();
      return;
    }

    // If system is IDLE:
    // If success overlay is currently visible, wait until it finishes
    if (state.sortingSuccess) {
      setIsVisible(false);
      return;
    }

    // When IDLE and no hand is detected, smoothly resume the video screensaver
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
    }

    idleTimerRef.current = setTimeout(() => {
      setIsVisible(true);
      startVideo();
    }, IDLE_DELAY_MS);

    return () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
    };
  }, [state.systemState, state.sortingSuccess, startVideo, pauseVideo]);

  // Initial play when mounted
  useEffect(() => {
    if (isVisible) {
      startVideo();
    }
  }, [isVisible, startVideo]);

  return (
    <div
      className={`${styles.overlay} ${isVisible ? styles.visible : ''}`}
      aria-hidden={!isVisible}
    >
      {/* Background looping ad video */}
      <video
        ref={videoRef}
        className={styles.videoElement}
        src="/ads/1.mp4"
        autoPlay
        loop
        muted
        playsInline
        preload="auto"
      />

      {/* Decorative gradient masks for contrast */}
      <div className={styles.gradientTop} />
      <div className={styles.gradientBottom} />

      {/* Top branding bar */}
      <div className={styles.topBar}>
        <div className={styles.brandGroup}>
          <img
            src={LOGO_SRC}
            alt="Sortyx Logo"
            className={styles.brandLogo}
            onError={(e) => {
              // Hide image if path not found
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
          <div className={styles.brandText}>
            <span className={styles.brandTitle}>Sortyx 2.0</span>
            <span className={styles.brandSubtitle}>Smart AI Waste Segregation</span>
          </div>
        </div>

        <div className={styles.statusPill}>
          <span className={styles.radarDot} />
          <span>Active Scanner Ready</span>
        </div>
      </div>

      {/* Bottom call to action */}
      <div className={styles.bottomBar}>
        <div className={styles.ctaCard}>
          <span className={styles.handIcon}>👋</span>
          <div className={ctaTextGroupClass(styles)}>
            <span className={styles.ctaMainText}>Show your hand or waste to sort</span>
            <span className={styles.ctaSubText}>Automated AI sorting begins instantly</span>
          </div>
        </div>
        <span className={styles.touchHint}>Live Optical & Weight Detection Active</span>
      </div>
    </div>
  );
}

function ctaTextGroupClass(styles: Record<string, string>): string {
  return styles.ctaTextGroup || '';
}
