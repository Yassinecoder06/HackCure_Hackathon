import React, { useState } from 'react';
import { STRINGS } from '../i18n/strings';
import { wardApi } from '../services/api';
import { LayoutGrid, Smartphone, Zap, UserCheck } from 'lucide-react';

interface NavbarProps {
  currentTab: 'board' | 'staff' | 'doctor';
  onSelectTab: (tab: 'board' | 'staff' | 'doctor') => void;
  isConnected: boolean;
  onPeakTriggered?: () => void;
  onOpenLogin: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  isConnected,
  onPeakTriggered,
  onOpenLogin
}) => {
  const [triggering, setTriggering] = useState<boolean>(false);
  const session = wardApi.getSession();
  const staff = session?.staff;

  const handleTriggerPeak = async () => {
    try {
      setTriggering(true);
      await wardApi.triggerPeakDemo();
      onPeakTriggered?.();
    } catch (e) {
      console.error(e);
    } finally {
      setTriggering(false);
    }
  };

  return (
    <header className="navbar">
      <div className="nav-brand">
        <div className="brand-icon">BP</div>
        <div className="brand-text">
          <h1>{STRINGS.app.title}</h1>
          <span>{STRINGS.app.wardName}</span>
        </div>
      </div>

      <nav className="nav-links">
        <button
          className={`nav-btn ${currentTab === 'board' ? 'active' : ''}`}
          onClick={() => onSelectTab('board')}
          id="nav-tab-board"
        >
          <LayoutGrid size={16} />
          {STRINGS.nav.stationBoard}
        </button>
        <button
          className={`nav-btn ${currentTab === 'staff' ? 'active' : ''}`}
          onClick={() => onSelectTab('staff')}
          id="nav-tab-staff"
        >
          <Smartphone size={16} />
          {STRINGS.nav.staffView}
        </button>
        <button
          className={`nav-btn ${currentTab === 'doctor' ? 'active' : ''}`}
          onClick={() => onSelectTab('doctor')}
          id="nav-tab-doctor"
        >
          <UserCheck size={16} />
          Doctor Console
        </button>
      </nav>

      <div className="nav-controls">
        <button
          className="demo-trigger-btn"
          onClick={handleTriggerPeak}
          disabled={triggering}
          title="Simulate night-shift deterioration on Bed B06 and call escalation"
          id="btn-trigger-peak"
        >
          <Zap size={14} />
          {triggering ? 'Triggering...' : STRINGS.nav.triggerPeakDemo}
        </button>

        {/* Staff Identity & Session Badge */}
        <button
          className="staff-auth-badge"
          onClick={onOpenLogin}
          title="Click to Switch Staff or Re-authenticate"
          id="btn-switch-staff"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'rgba(30, 41, 59, 0.8)',
            border: '1px solid rgba(148, 163, 184, 0.25)',
            borderRadius: 8,
            padding: '0.35rem 0.65rem',
            color: '#f8fafc',
            cursor: 'pointer',
            fontSize: '0.8rem',
            transition: 'all 0.15s ease'
          }}
        >
          <UserCheck size={15} color="#38bdf8" />
          <div style={{ textAlign: 'left', lineHeight: 1.2 }}>
            <div style={{ fontWeight: 700, fontSize: '0.8rem' }}>
              {staff ? `${staff.name} (${staff.id})` : 'Charge Nurse A (CN1)'}
            </div>
            <div style={{ fontSize: '0.65rem', color: staff?.role === 'doctor' ? '#c084fc' : '#38bdf8', textTransform: 'capitalize' }}>
              {staff?.role ? staff.role.replace('_', ' ') : 'Charge Nurse'} · Active Session
            </div>
          </div>
        </button>

        <div className="status-pill" title={isConnected ? STRINGS.app.connectionOnline : STRINGS.app.connectionOffline}>
          <div className="status-dot" style={{ backgroundColor: isConnected ? '#10b981' : '#f59e0b' }}></div>
          <span>{isConnected ? 'LIVE' : 'SYNCING'}</span>
        </div>
      </div>
    </header>
  );
};
