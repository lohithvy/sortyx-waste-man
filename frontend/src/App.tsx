import { AppStateProvider } from './state/AppStateContext';
import ActiveDashboard from './screens/ActiveDashboard';

export default function App() {
  return (
    <AppStateProvider>
      <ActiveDashboard />
    </AppStateProvider>
  );
}
