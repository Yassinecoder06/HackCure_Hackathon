import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { StationBoard } from './pages/StationBoard';
import { StaffView } from './pages/StaffView';
import { wardApi } from './services/api';
import './styles/index.css';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'board' | 'staff'>(() => {
    return window.location.pathname.includes('/staff') ? 'staff' : 'board';
  });

  const [beds, setBeds] = useState<any[]>([]);
  const [calls, setCalls] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [targetFastEntryBed, setTargetFastEntryBed] = useState<string | null>(null);

  // Sync route on popstate or tab change
  useEffect(() => {
    const handlePopState = () => {
      setCurrentTab(window.location.pathname.includes('/staff') ? 'staff' : 'board');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const handleSelectTab = (tab: 'board' | 'staff') => {
    setCurrentTab(tab);
    window.history.pushState({}, '', tab === 'board' ? '/board' : '/staff');
  };

  const loadInitialSnapshot = async () => {
    try {
      const snap = await wardApi.getSnapshot('W1');
      setBeds(snap.beds || []);
      setCalls(snap.calls || []);
      setAlerts(snap.alerts || []);
    } catch (e) {
      console.warn('Snapshot fetch error (awaiting mock server or backend):', e);
    }
  };

  useEffect(() => {
    // 1. Initial REST snapshot
    loadInitialSnapshot();

    // 2. Connect WebSocket
    wardApi.connectWebSocket();

    // 3. Subscribe to real-time events
    const unsubscribe = wardApi.subscribe((type, data) => {
      if (type === 'connection') {
        setIsConnected(data.connected);
      } else if (type === 'snapshot') {
        setBeds(data.beds || []);
        setCalls(data.calls || []);
        setAlerts(data.alerts || []);
      } else if (type === 'bed') {
        setBeds(prev => prev.map(b => b.bed === data.bed ? data : b));
      } else if (type === 'call') {
        setCalls(prev => {
          const filtered = prev.filter(c => c.callId !== data.callId);
          if (data.state === 'resolved') return filtered;
          return [data, ...filtered];
        });
      } else if (type === 'alert') {
        setAlerts(prev => {
          const filtered = prev.filter(a => a.alertId !== data.alertId);
          if (data.acknowledgedBy) return filtered;
          return [data, ...filtered];
        });
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar
        currentTab={currentTab}
        onSelectTab={handleSelectTab}
        isConnected={isConnected}
        onPeakTriggered={loadInitialSnapshot}
      />

      <main style={{ flex: 1 }}>
        {currentTab === 'board' ? (
          <StationBoard
            beds={beds}
            calls={calls}
            alerts={alerts}
            onOpenFastEntry={(bedId) => {
              setTargetFastEntryBed(bedId);
              handleSelectTab('staff');
            }}
          />
        ) : (
          <StaffView
            beds={beds}
            calls={calls}
            alerts={alerts}
            onRefresh={loadInitialSnapshot}
            targetFastEntryBed={targetFastEntryBed}
            onClearFastEntryTarget={() => setTargetFastEntryBed(null)}
          />
        )}
      </main>
    </div>
  );
};
export default App;
