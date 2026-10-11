import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { StationBoard } from './pages/StationBoard';
import { StaffView } from './pages/StaffView';
import { DoctorView } from './pages/DoctorView';
import { LoginModal } from './components/LoginModal';
import { wardApi } from './services/api';
import { audioAlerts } from './components/AudioAlerts';
import { AlertTriangle, VolumeX, CheckCircle2 } from 'lucide-react';
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
  const [isAlarmSounding, setIsAlarmSounding] = useState<boolean>(false);
  const [isMuted, setIsMuted] = useState<boolean>(() => audioAlerts.getMuted());

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

  const handleSilenceAlarm = () => {
    wardApi.silenceAlarm();
  };

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      await wardApi.acknowledgeAlert(alertId);
      await loadInitialSnapshot();
    } catch (e) {
      console.error('Failed to acknowledge alert:', e);
    }
  };

  const handleToggleAudioMute = () => {
    wardApi.toggleAudioMute();
  };

  useEffect(() => {
    // 1. Initial REST snapshot
    loadInitialSnapshot();

    // 2. Connect WebSocket
    wardApi.connectWebSocket();

    // 3. Audio state listener
    const unsubAudio = audioAlerts.subscribe((sounding, muted) => {
      setIsAlarmSounding(sounding);
      setIsMuted(muted);
    });

    // 4. Subscribe to real-time events
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
      unsubAudio();
    };
  }, []);

  const criticalAlert = alerts.find(a => a.priority === 'critical' && a.active !== false);

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
        isAlarmSounding={isAlarmSounding}
        onSilenceAlarm={handleSilenceAlarm}
        isMuted={isMuted}
        onToggleMute={handleToggleAudioMute}
      />

      {/* Global Emergency Alert Banner - Displayed on ALL views whenever a critical alert is active */}
      {criticalAlert && (
        <div
          className="global-emergency-banner"
          id="global-emergency-banner"
          style={{
            background: 'linear-gradient(90deg, #991b1b 0%, #dc2626 50%, #b91c1c 100%)',
            color: '#ffffff',
            padding: '0.65rem 1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 4px 14px rgba(220, 38, 38, 0.4)',
            zIndex: 90,
            borderBottom: '1px solid rgba(254, 202, 202, 0.3)',
            animation: 'fadeIn 0.2s ease-out'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              background: 'rgba(255, 255, 255, 0.2)',
              borderRadius: '50%',
              padding: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <AlertTriangle size={20} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  background: '#fef2f2',
                  color: '#991b1b',
                  padding: '2px 8px',
                  borderRadius: 4,
                  fontWeight: 900,
                  fontSize: '0.75rem',
                  letterSpacing: '0.05em'
                }}>
                  CRITICAL ALERT
                </span>
                <strong style={{ fontSize: '0.95rem' }}>Bed {criticalAlert.bed} — Severe Deterioration (NEWS2 Spike)</strong>
              </div>
              <div style={{ fontSize: '0.8rem', opacity: 0.95, marginTop: 2 }}>
                {criticalAlert.explanation?.[0] || 'Urgent Clinical Review Required'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isAlarmSounding && (
              <button
                id="btn-banner-silence"
                onClick={handleSilenceAlarm}
                title="Stop Alarm Beeping immediately"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  background: 'rgba(255, 255, 255, 0.95)',
                  color: '#b91c1c',
                  border: 'none',
                  borderRadius: 6,
                  padding: '0.45rem 0.85rem',
                  fontWeight: 800,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.2)'
                }}
              >
                <VolumeX size={16} />
                Silence Sound
              </button>
            )}
            <button
              id="btn-banner-ack"
              onClick={() => handleAcknowledgeAlert(criticalAlert.alertId)}
              title="Acknowledge clinical alert and stop alarm"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                background: '#15803d',
                color: '#ffffff',
                border: '1px solid #86efac',
                borderRadius: 6,
                padding: '0.45rem 0.85rem',
                fontWeight: 700,
                fontSize: '0.82rem',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(0,0,0,0.2)'
              }}
            >
              <CheckCircle2 size={16} />
              Acknowledge & Clear
            </button>
          </div>
        </div>
      )}

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
            onAcknowledgeAlert={handleAcknowledgeAlert}
            onSilenceAlarm={handleSilenceAlarm}
            isAlarmSounding={isAlarmSounding}
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
