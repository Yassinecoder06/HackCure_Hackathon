import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { StationBoard } from './pages/StationBoard';
import { StaffView } from './pages/StaffView';
import { DoctorView } from './pages/DoctorView';
import { LoginModal } from './components/LoginModal';
import { wardApi } from './services/api';
import './styles/index.css';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'board' | 'staff' | 'doctor'>(() => {
    if (window.location.pathname.includes('/doctor')) return 'doctor';
    if (window.location.pathname.includes('/staff')) return 'staff';
    return 'board';
  });

  const [beds, setBeds] = useState<any[]>([]);
  const [calls, setCalls] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [triageMetrics, setTriageMetrics] = useState<any | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isLoginOpen, setIsLoginOpen] = useState<boolean>(false);
  const [targetFastEntryBed, setTargetFastEntryBed] = useState<string | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('borj_theme') as 'dark' | 'light') || 'dark';
  });

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'light') {
      document.body.classList.add('light-mode');
      document.body.classList.remove('dark-mode');
    } else {
      document.body.classList.add('dark-mode');
      document.body.classList.remove('light-mode');
    }
    localStorage.setItem('borj_theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  // Sync route on popstate or tab change
  useEffect(() => {
    const handlePopState = () => {
      if (window.location.pathname.includes('/doctor')) {
        setCurrentTab('doctor');
      } else if (window.location.pathname.includes('/staff')) {
        setCurrentTab('staff');
      } else {
        setCurrentTab('board');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const handleSelectTab = (tab: 'board' | 'staff' | 'doctor') => {
    setCurrentTab(tab);
    window.history.pushState({}, '', `/${tab}`);
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
      } else if (type === 'auth_expired') {
        setIsLoginOpen(true);
      } else if (type === 'auth_changed') {
        loadInitialSnapshot();
      } else if (type === 'metrics') {
        setTriageMetrics(data);
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
          // Safety / Contract: if acknowledged or condition cleared (active === false), remove from active alerts
          if (data.acknowledgedBy || data.active === false) return filtered;
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
        onOpenLogin={() => setIsLoginOpen(true)}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      {/* Track 2 Degraded Network Tolerance Banner */}
      {!isConnected && (
        <div style={{ background: '#f59e0b', color: '#1e293b', padding: '0.4rem 1.5rem', fontSize: '0.8rem', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>⚠️ Degraded Network Mode: Attending Ward Local Offline Cache Active. Actions are queued.</span>
          <span>Reconnecting to WebSocket...</span>
        </div>
      )}

      <main style={{ flex: 1 }}>
        {currentTab === 'board' ? (
          <StationBoard
            beds={beds}
            calls={calls}
            alerts={alerts}
            triageMetrics={triageMetrics}
            onOpenFastEntry={(bedId) => {
              setTargetFastEntryBed(bedId);
              handleSelectTab('staff');
            }}
          />
        ) : currentTab === 'staff' ? (
          <StaffView
            beds={beds}
            calls={calls}
            alerts={alerts}
            onRefresh={loadInitialSnapshot}
            targetFastEntryBed={targetFastEntryBed}
            onClearFastEntryTarget={() => setTargetFastEntryBed(null)}
          />
        ) : (
          <DoctorView
            beds={beds}
            alerts={alerts}
            onRefresh={loadInitialSnapshot}
          />
        )}
      </main>

      {/* Staff Login / Switch User Modal */}
      <LoginModal
        isOpen={isLoginOpen}
        onClose={() => setIsLoginOpen(false)}
        onSuccess={() => {
          setIsLoginOpen(false);
          loadInitialSnapshot();
        }}
      />
    </div>
  );
};
export default App;
