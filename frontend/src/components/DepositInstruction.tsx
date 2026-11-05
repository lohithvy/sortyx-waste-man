import compStyles from '../styles/components.module.css';

export default function DepositInstruction() {
  return (
    <div className={compStyles.depositInstruction}>
      <span className={compStyles.depositInstructionIcon}>🗑️</span>
      <span className={compStyles.depositInstructionTitle}>Deposit Your Waste</span>
      <span className={compStyles.depositInstructionSub}>
        The bin is open — place the item inside now
      </span>
    </div>
  );
}
