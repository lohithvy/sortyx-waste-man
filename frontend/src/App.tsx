import { AppStateProvider, useAppState } from './state/AppStateContext';
import { SystemState } from './types';
import IdleScreen from './screens/IdleScreen';
import ActiveDashboard from './screens/ActiveDashboard';

function AppInner() {
  const { state } = useAppState();
  const isIdle = state.systemState === SystemState.Idle;

  return isIdle ? <IdleScreen /> : <ActiveDashboard />;
}

export default function App() {
  return (
    <AppStateProvider>
      <AppInner />
    </AppStateProvider>
  );
}
