import React, { useState } from 'react';
import { STRINGS } from '../i18n/strings';
import { wardApi } from '../services/api';
import { LayoutGrid, Smartphone, Zap, UserCheck } from 'lucide-react';

interface NavbarProps {
  currentTab: 'board' | 'staff';
  onSelectTab: (tab: 'board' | 'staff') => void;
  isConnected: boolean;
  onPeakTriggered?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  isConnected,
  onPeakTriggered
}) => {
  const [selectedStaff, setSelectedStaff] = useState<string>('CN1');
  const [triggering, setTriggering] = useState<boolean>(false);

  const handleStaffChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedStaff(id);
    wardApi.setStaffId(id);
  };

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

        <div className="staff-select-box">
          <UserCheck size={14} color="#94a3b8" />
          <select value={selectedStaff} onChange={handleStaffChange} id="select-staff-id">
            <option value="CN1">CN1: Charge Nurse A</option>
            <option value="N1">N1: Nurse B</option>
            <option value="N2">N2: Nurse C</option>
            <option value="N3">N3: Nurse D</option>
            <option value="CA1">CA1: Care Assistant E</option>
            <option value="DR1">DR1: Doctor F</option>
          </select>
        </div>

        <div className="status-pill" title={isConnected ? STRINGS.app.connectionOnline : STRINGS.app.connectionOffline}>
          <div className="status-dot" style={{ backgroundColor: isConnected ? '#10b981' : '#f59e0b' }}></div>
          <span>{isConnected ? 'LIVE' : 'SYNCING'}</span>
        </div>
      </div>
    </header>
  );
};
