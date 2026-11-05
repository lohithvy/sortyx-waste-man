import compStyles from '../styles/components.module.css';

export default function ErrorDisplay() {
  const handleRetry = () => {
    window.location.reload();
  };

  return (
    <div className={compStyles.errorCard}>
      <div className={compStyles.errorHeader}>
        <span className={compStyles.errorIcon}>❌</span>
        System Error
      </div>
      <div className={compStyles.errorBody}>
        An unexpected error occurred. The system may need attention.
      </div>
      <div className={compStyles.errorActions}>
        <button
          className={`${compStyles.errorBtn} ${compStyles.errorBtnPrimary}`}
          onClick={handleRetry}
        >
          Retry
        </button>
        <button
          className={`${compStyles.errorBtn} ${compStyles.errorBtnSecondary}`}
          onClick={handleRetry}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
