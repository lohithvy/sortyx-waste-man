import styles from '../styles/DetectedWaste.module.css';
import { useAppState } from '../state/AppStateContext';

interface StepDef {
  key: keyof typeof stepKeys;
  label: string;
  dynamicLabel?: (category: string) => string;
}

const stepKeys = {
  objectDetected: 'objectDetected',
  classified: 'classified',
  binOpening: 'binOpening',
  waitingForDeposit: 'waitingForDeposit',
  closingBin: 'closingBin',
} as const;

function formatCategory(cat: string) {
  switch (cat) {
    case 'food_waste':
    case 'organic': return 'Food Waste';
    case 'recyclable':
    case 'bio': return 'Recyclable';
    case 'non_recyclable':
    case 'non_bio': return 'Non-Recyclable';
    default: return cat;
  }
}

const STEPS: StepDef[] = [
  { key: 'objectDetected', label: 'Object Detected' },
  {
    key: 'classified',
    label: 'Classified',
    dynamicLabel: (cat) => `Classified as ${formatCategory(cat)}`,
  },
  {
    key: 'binOpening',
    label: 'Opening Bin',
    dynamicLabel: (cat) => `Opening ${formatCategory(cat)} Bin`,
  },
  { key: 'waitingForDeposit', label: 'Waiting for Deposit' },
  { key: 'closingBin', label: 'Closing Bin' },
];

export default function SortingProgress() {
  const { state } = useAppState();
  const progress = state.sortingProgress;
  const category = state.classificationResult?.category ?? '';

  // Find first incomplete step to mark as "active"
  const activeIndex = STEPS.findIndex(
    (s) => !progress[s.key as keyof typeof progress],
  );

  return (
    <div className={styles.progressCard}>
      <div className={styles.progressTitle}>Sorting Progress</div>
      <div className={styles.steps}>
        {STEPS.map((step, i) => {
          const done = progress[step.key as keyof typeof progress];
          const isActive = i === activeIndex;
          const label =
            step.dynamicLabel && category
              ? step.dynamicLabel(category)
              : step.label;

          let circleClass = styles.circlePending;
          let labelClass = styles.stepLabel;
          let stepClass = styles.step;

          if (done) {
            circleClass = styles.circleCompleted;
            labelClass = `${styles.stepLabel} ${styles.stepLabelCompleted}`;
            stepClass = `${styles.step} completed`;
          } else if (isActive) {
            circleClass = styles.circleActive;
            labelClass = `${styles.stepLabel} ${styles.stepLabelActive}`;
          }

          return (
            <div key={step.key} className={stepClass}>
              <div className={`${styles.stepCircle} ${circleClass}`}>
                {done ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>
              <span className={labelClass}>{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
