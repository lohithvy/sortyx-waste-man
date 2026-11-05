import compStyles from '../styles/components.module.css';
import { useAppState } from '../state/AppStateContext';

export default function ManualReviewAlert() {
  const { state } = useAppState();
  const result = state.classificationResult;

  return (
    <div className={compStyles.manualReview}>
      <div className={compStyles.manualReviewHeader}>
        <span className={compStyles.manualReviewIcon}>⚠️</span>
        Manual Review Required
      </div>
      <div className={compStyles.manualReviewBody}>
        {result?.reason || 'The system could not confidently classify this item.'}
        {result?.isHazardous && (
          <strong> This item may be hazardous.</strong>
        )}
      </div>
      <div className={compStyles.manualReviewInstruction}>
        Please remove the object and sort it manually.
      </div>
    </div>
  );
}
