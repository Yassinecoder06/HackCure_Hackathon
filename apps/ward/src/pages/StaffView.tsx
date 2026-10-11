import React, { useState, useEffect } from 'react';
import { STRINGS } from '../i18n/strings';
import { wardApi } from '../services/api';
import {
  Bell,
  CheckCircle,
  AlertTriangle,
  Play,
  Check,
  X,
  Shield,
  Layers,
  Pill,
  Sparkles,
  HeartPulse
} from 'lucide-react';

interface StaffViewProps {
  beds: any[];
  staff?: any[];
  calls: any[];
  alerts: any[];
  onRefresh?: () => void;
  targetFastEntryBed?: string | null;
  onClearFastEntryTarget?: () => void;
}

export const StaffView: React.FC<StaffViewProps> = ({
  beds,
  staff = [],
  calls,
  alerts,
  onRefresh,
  targetFastEntryBed,
  onClearFastEntryTarget
}) => {
  const [activeTab, setActiveTab] = useState<'calls' | 'fastentry' | 'assignments' | 'whatif' | 'meds' | 'family'>('calls');

  // Fast entry form state
  const [selectedBedId, setSelectedBedId] = useState<string>(targetFastEntryBed || 'B06');
  const [consciousness, setConsciousness] = useState<string>('A');
  const [onOxygen, setOnOxygen] = useState<boolean>(false);
  const [respRate, setRespRate] = useState<string>('20');
  const [pulse, setPulse] = useState<string>('80');
  const [sysBp, setSysBp] = useState<string>('120');
  const [tempC, setTempC] = useState<string>('37.0');
  const [submittingObs, setSubmittingObs] = useState<boolean>(false);
  const [obsSuccessMsg, setObsSuccessMsg] = useState<string | null>(null);

  // Suggestions state
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [decidingSug, setDecidingSug] = useState<boolean>(false);
  const [requestingSug, setRequestingSug] = useState<boolean>(false);
  const [decisionFeedback, setDecisionFeedback] = useState<string | null>(null);

  const session = wardApi.getSession();
  const isChargeNurse = session?.staff?.role === 'charge_nurse';
  const onWardNurses = staff.filter((s: any) => s.onWard && (s.role === 'nurse' || s.role === 'charge_nurse'));

  // What-If state
  const [whatIfDisruptions, setWhatIfDisruptions] = useState<string[]>(['staff_leaves']);
  const [whatIfResult, setWhatIfResult] = useState<any | null>(null);
  const [runningWhatIf, setRunningWhatIf] = useState<boolean>(false);

  // Meds timeline state
  const [medTimeline, setMedTimeline] = useState<any | null>(null);

  // Family updates state
  const [familyUpdates, setFamilyUpdates] = useState<any[]>([]);
  const [consentName, setConsentName] = useState<string>('Fatima (Daughter)');
  const [inviteResult, setInviteResult] = useState<any | null>(null);
  const [draftNote, setDraftNote] = useState<string>('Patient is resting comfortably after lunch.');

  useEffect(() => {
    if (targetFastEntryBed) {
      setSelectedBedId(targetFastEntryBed);
      setActiveTab('fastentry');
      onClearFastEntryTarget?.();
    }
  }, [targetFastEntryBed]);

  useEffect(() => {
    loadSuggestions();
    loadMeds();
    loadFamilyUpdates();

    const unsub = wardApi.subscribe((type) => {
      if (type === 'assignment_suggestion' || type === 'staff' || type === 'auth_changed') {
        loadSuggestions();
      }
    });
    return () => unsub();
  }, []);

  const loadSuggestions = async () => {
    try {
      const data = await wardApi.getSuggestions();
      setSuggestions(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
      setSuggestions([]);
    }
  };

  const loadMeds = async () => {
    try {
      const data = await wardApi.getMedsTimeline();
      setMedTimeline(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadFamilyUpdates = async () => {
    try {
      const data = await wardApi.getFamilyUpdates();
      setFamilyUpdates(data || []);
    } catch (e) {
      console.error(e);
    }
  };

  // Critical persistent alert takeover
  const criticalAlert = alerts.find(a => a.priority === 'critical');

  const handleAckAlert = async (alertId: string) => {
    await wardApi.acknowledgeAlert(alertId);
    onRefresh?.();
  };

  const handleAckCall = async (callId: string) => {
    await wardApi.acknowledgeCall(callId);
    onRefresh?.();
  };

  const handleResolveCall = async (callId: string) => {
    await wardApi.resolveCall(callId);
    onRefresh?.();
  };

  const handleSubmitObservation = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingObs(true);
    setObsSuccessMsg(null);
    try {
      const payload: any = {
        consciousness,
        on_oxygen: onOxygen
      };
      if (respRate) payload.resp_rate = parseInt(respRate, 10);
      if (pulse) payload.pulse = parseInt(pulse, 10);
      if (sysBp) payload.sys_bp = parseInt(sysBp, 10);
      if (tempC) payload.temp_c = parseFloat(tempC);

      await wardApi.submitObservations(selectedBedId, payload);
      setObsSuccessMsg(`Observations recorded for Bed ${selectedBedId}! Score updated.`);
      onRefresh?.();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmittingObs(false);
    }
  };

  const handleDecideSuggestion = async (id: string, decision: 'approve' | 'reject') => {
    setDecidingSug(true);
    setDecisionFeedback(null);
    try {
      await wardApi.decideSuggestion(id, decision, 'Charge Nurse approved in staff controls');
      setDecisionFeedback(decision === 'approve' ? '✓ Rebalance proposal approved! Bed assignments updated across the ward.' : 'Rebalance proposal rejected.');
      await loadSuggestions();
      onRefresh?.();
    } catch (e: any) {
      alert(e.message || 'Failed to record assignment decision');
    } finally {
      setDecidingSug(false);
    }
  };

  const handleRequestSuggestion = async () => {
    setRequestingSug(true);
    setDecisionFeedback(null);
    try {
      await wardApi.requestSuggestion();
      await loadSuggestions();
      onRefresh?.();
    } catch (e: any) {
      alert(e.message || 'Failed to request suggestion from solver');
    } finally {
      setRequestingSug(false);
    }
  };

  const handleToggleStaffPresence = async (staffId: string, onWard: boolean, reason: string) => {
    try {
      await wardApi.setStaffPresence(staffId, onWard, reason);
      onRefresh?.();
      await loadSuggestions();
    } catch (e: any) {
      alert(e.message || 'Failed to update staff presence');
    }
  };

  const handleCheckInAllShiftStaff = async () => {
    try {
      for (const st of staff.filter((s: any) => s.role === 'nurse' || s.role === 'charge_nurse')) {
        if (!st.onWard) {
          await wardApi.setStaffPresence(st.staffId, true, 'shift_start');
        }
      }
      onRefresh?.();
      await loadSuggestions();
    } catch (e: any) {
      alert(e.message || 'Failed to check in staff team');
    }
  };

  const handleRunWhatIf = async () => {
    setRunningWhatIf(true);
    try {
      const disruptionsPayload = whatIfDisruptions.map(d => ({ type: d, atMin: 15 }));
      const result = await wardApi.runWhatIf(disruptionsPayload);
      setWhatIfResult(result);
    } catch (e) {
      console.error(e);
    } finally {
      setRunningWhatIf(false);
    }
  };

  const handleAdministerMed = async (doseId: string, action: 'given' | 'not_given') => {
    await wardApi.recordAdministration(doseId, action);
    await loadMeds();
  };

  const handleCreateConsentAndInvite = async () => {
    try {
      await wardApi.createFamilyConsent('adm_06', consentName);
      const inv = await wardApi.createFamilyInvite('adm_06');
      setInviteResult(inv);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDraftFamilyNote = async () => {
    try {
      await wardApi.draftFamilyUpdate('adm_06', 'nurse_note', draftNote);
      await loadFamilyUpdates();
      setDraftNote('');
    } catch (e) {
      console.error(e);
    }
  };

  const handleDecideFamilyUpdate = async (updateId: string, decision: 'approve' | 'reject') => {
    try {
      await wardApi.decideFamilyUpdate(updateId, decision);
      await loadFamilyUpdates();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="staff-view-container">
      {/* Critical Alarm Persistent Takeover Modal */}
      {criticalAlert && (
        <div className="critical-full-modal">
          <div className="critical-modal-content">
            <AlertTriangle size={56} color="#ef4444" />
            <h2 style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-main)' }}>{STRINGS.alerts.criticalTakeoverTitle}</h2>
            <div style={{ backgroundColor: 'rgba(239,68,68,0.1)', padding: '1rem', borderRadius: 8, width: '100%', border: '1px solid rgba(239,68,68,0.3)' }}>
              <div style={{ fontWeight: 700, fontSize: '1.2rem', color: '#ef4444' }}>
                Bed {criticalAlert.bed} — Critical Clinical Event
              </div>
              <ul style={{ textAlign: 'left', marginTop: 8, fontSize: '0.9rem', color: 'var(--text-main)' }}>
                {criticalAlert.explanation.map((exp: string, idx: number) => (
                  <li key={idx}>• {exp}</li>
                ))}
              </ul>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Persistent audio alarm active. Continuous alert escalation until acknowledged by attending staff.
            </p>
            <button
              className="ack-critical-btn"
              onClick={() => handleAckAlert(criticalAlert.alertId)}
              id="btn-ack-critical"
            >
              <CheckCircle size={20} style={{ display: 'inline', marginRight: 8 }} />
              {STRINGS.alerts.ackAlertBtn}
            </button>
          </div>
        </div>
      )}

      {/* Escalation Alert Ladder Bar */}
      {alerts.length > 0 && (
        <div className="escalation-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Bell size={24} color="#f97316" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-main)' }}>
                {alerts.length} Active Escalation Alerts
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {alerts[0].explanation[0]}
              </div>
            </div>
          </div>
          <button
            className="btn-outline"
            style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#ef4444' }}
            onClick={() => handleAckAlert(alerts[0].alertId)}
          >
            Acknowledge Top Alert
          </button>
        </div>
      )}

      {/* Staff Controls Navigation Tabs */}
      <div className="staff-tabs">
        <button
          className={`tab-btn ${activeTab === 'calls' ? 'active' : ''}`}
          onClick={() => setActiveTab('calls')}
          id="tab-btn-calls"
        >
          <Bell size={16} />
          Bedside Calls ({calls.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'fastentry' ? 'active' : ''}`}
          onClick={() => setActiveTab('fastentry')}
          id="tab-btn-fastentry"
        >
          <HeartPulse size={16} />
          10s Fast Entry
        </button>
        <button
          className={`tab-btn ${activeTab === 'assignments' ? 'active' : ''}`}
          onClick={() => setActiveTab('assignments')}
          id="tab-btn-assignments"
        >
          <Layers size={16} />
          Workload Rebalance ({suggestions.filter(s => s.status === 'pending').length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'whatif' ? 'active' : ''}`}
          onClick={() => setActiveTab('whatif')}
          id="tab-btn-whatif"
        >
          <Sparkles size={16} />
          SimPy What-If Twin
        </button>
        <button
          className={`tab-btn ${activeTab === 'meds' ? 'active' : ''}`}
          onClick={() => setActiveTab('meds')}
          id="tab-btn-meds"
        >
          <Pill size={16} />
          Medication Timeline
        </button>
        <button
          className={`tab-btn ${activeTab === 'family' ? 'active' : ''}`}
          onClick={() => setActiveTab('family')}
          id="tab-btn-family"
        >
          <Shield size={16} />
          Family Care Link
        </button>
      </div>

      {/* 1. BEDSIDE CALLS TAB */}
      {activeTab === 'calls' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.calls.title}</h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Arrival feedback, multi-role routing (Assist → Nurse, Comfort → Care Assistant), and escalation ladder.
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {calls.map(call => (
              <div
                key={call.callId}
                className="room-box"
                style={{
                  borderLeft: `5px solid ${call.state === 'escalated' ? '#ef4444' : call.state === 'sent' ? '#f59e0b' : '#10b981'}`
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>Bed {call.bed}</span>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 4,
                      backgroundColor: call.state === 'escalated' ? 'rgba(239,68,68,0.2)' : call.state === 'sent' ? 'rgba(245,158,11,0.2)' : 'rgba(16,185,129,0.2)',
                      color: call.state === 'escalated' ? '#ef4444' : call.state === 'sent' ? '#b45309' : '#059669',
                      textTransform: 'uppercase'
                    }}
                  >
                    {call.state}
                  </span>
                </div>

                <div style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginTop: 6 }}>
                  Type: <strong>{call.kind === 'assist' ? STRINGS.calls.assistCall : STRINGS.calls.comfortCall}</strong>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Routed to: <strong>{call.routedToRole.replace('_', ' ').toUpperCase()}</strong>
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  {call.state === 'sent' && (
                    <button
                      className="btn-success"
                      onClick={() => handleAckCall(call.callId)}
                      style={{ flex: 1 }}
                      id={`btn-ack-${call.callId}`}
                    >
                      <Check size={14} style={{ display: 'inline', marginRight: 4 }} />
                      {STRINGS.calls.ackBtn}
                    </button>
                  )}
                  <button
                    className="btn-outline"
                    onClick={() => handleResolveCall(call.callId)}
                    style={{ flex: 1 }}
                    id={`btn-resolve-${call.callId}`}
                  >
                    {STRINGS.calls.resolveBtn}
                  </button>
                </div>
              </div>
            ))}
            {calls.length === 0 && (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1 / -1' }}>
                {STRINGS.calls.noCalls}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 2. 10-SECOND FAST ENTRY TAB */}
      {activeTab === 'fastentry' && (
        <div className="room-box" style={{ padding: '1.5rem' }}>
          <div style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.fastEntry.title}</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{STRINGS.fastEntry.subtitle}</p>
          </div>

          {obsSuccessMsg && (
            <div style={{ background: 'rgba(16,185,129,0.15)', border: '1px solid #10b981', color: '#10b981', padding: '0.75rem', borderRadius: 6, marginBottom: '1rem', fontSize: '0.85rem' }}>
              ✓ {obsSuccessMsg}
            </div>
          )}

          <form onSubmit={handleSubmitObservation} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="fast-entry-grid">
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{STRINGS.fastEntry.selectBed}</label>
                <select
                  value={selectedBedId}
                  onChange={e => setSelectedBedId(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.6rem',
                    borderRadius: 6,
                    fontSize: '0.9rem'
                  }}
                  id="select-fastentry-bed"
                >
                  {beds.map(b => (
                    <option key={b.bed} value={b.bed}>
                      Bed {b.bed} ({b.admission?.patientRef || 'Empty'})
                    </option>
                  ))}
                </select>
              </div>

              {/* Consciousness ACVPU */}
              <div className="form-group" style={{ gridColumn: 'span 2' }}>
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{STRINGS.fastEntry.consciousnessLabel}</label>
                <div className="button-radio-group">
                  {[
                    { val: 'A', label: 'A — Alert (0 pts)' },
                    { val: 'C', label: 'C — Confusion (3 pts)' },
                    { val: 'V', label: 'V — Voice (3 pts)' },
                    { val: 'P', label: 'P — Pain (3 pts)' },
                    { val: 'U', label: 'U — Unresponsive (3 pts)' }
                  ].map(opt => (
                    <button
                      key={opt.val}
                      type="button"
                      className={`radio-pill ${consciousness === opt.val ? 'selected' : ''}`}
                      onClick={() => setConsciousness(opt.val)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Supplemental Oxygen */}
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{STRINGS.fastEntry.oxygenLabel}</label>
                <div className="button-radio-group">
                  <button
                    type="button"
                    className={`radio-pill ${!onOxygen ? 'selected' : ''}`}
                    onClick={() => setOnOxygen(false)}
                  >
                    {STRINGS.fastEntry.oxygenNo} (0 pts)
                  </button>
                  <button
                    type="button"
                    className={`radio-pill ${onOxygen ? 'selected' : ''}`}
                    onClick={() => setOnOxygen(true)}
                  >
                    {STRINGS.fastEntry.oxygenYes} (+2 pts)
                  </button>
                </div>
              </div>

              {/* Resp Rate */}
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{STRINGS.fastEntry.respRateLabel}</label>
                <input
                  type="number"
                  value={respRate}
                  onChange={e => setRespRate(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.6rem',
                    borderRadius: 6
                  }}
                />
              </div>

              {/* Pulse */}
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Heart Rate / Pulse (bpm)</label>
                <input
                  type="number"
                  value={pulse}
                  onChange={e => setPulse(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.6rem',
                    borderRadius: 6
                  }}
                />
              </div>

              {/* Blood Pressure */}
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Systolic Blood Pressure (mmHg)</label>
                <input
                  type="number"
                  value={sysBp}
                  onChange={e => setSysBp(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.6rem',
                    borderRadius: 6
                  }}
                />
              </div>

              {/* Temperature */}
              <div className="form-group">
                <label style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Temperature (°C)</label>
                <input
                  type="number"
                  step="0.1"
                  value={tempC}
                  onChange={e => setTempC(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.6rem',
                    borderRadius: 6
                  }}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={submittingObs}
              style={{ alignSelf: 'flex-start', padding: '0.8rem 1.8rem', fontSize: '0.95rem' }}
              id="btn-submit-obs"
            >
              {submittingObs ? 'Recording...' : STRINGS.fastEntry.submit}
            </button>
          </form>
        </div>
      )}

      {/* 3. OR-TOOLS ASSIGNMENT REBALANCING TAB */}
      {activeTab === 'assignments' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.assignments.title}</h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Mathematical workload balancing respecting continuity of care, proximity, and skill mix.
              </p>
            </div>
            <button
              className="btn-primary"
              onClick={handleRequestSuggestion}
              disabled={requestingSug}
              id="btn-request-rebalance"
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0.65rem 1.25rem' }}
            >
              <Sparkles size={16} />
              {requestingSug ? 'Calculating OR-Tools Optimization...' : 'Calculate Optimal Rebalance (OR-Tools)'}
            </button>
          </div>

          {/* Role Check & Switch Banner */}
          {!isChargeNurse && (
            <div style={{ background: 'rgba(234, 88, 12, 0.12)', border: '1px solid #ea580c', padding: '0.85rem 1.25rem', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <div style={{ fontWeight: 800, color: '#f97316', fontSize: '0.9rem' }}>
                  Logged in as {session?.staff?.name || 'Staff'} ({session?.staff?.role || 'nurse'})
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  Safety Invariant 1: Reviewing and approving assignment suggestions requires Charge Nurse authority (CN1, PIN 687463).
                </div>
              </div>
              <button
                className="btn-primary"
                onClick={async () => {
                  await wardApi.login('CN1', '687463');
                  onRefresh?.();
                  await loadSuggestions();
                }}
                style={{ background: '#0284c7', padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                id="btn-switch-charge-nurse"
              >
                Switch to Charge Nurse A Session (1-Tap)
              </button>
            </div>
          )}

          {/* 0 Nurses On Ward Alert */}
          {onWardNurses.length === 0 && (
            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: '0.85rem 1.25rem', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <div style={{ fontWeight: 800, color: '#ef4444', fontSize: '0.9rem' }}>
                  ⚠️ No Nurses Currently Checked In On Ward
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  The Google OR-Tools solver requires at least one nurse on duty to calculate workload assignments.
                </div>
              </div>
              <button
                className="btn-success"
                onClick={handleCheckInAllShiftStaff}
                style={{ padding: '0.5rem 1.1rem', fontSize: '0.85rem' }}
                id="btn-checkin-shift-nurses"
              >
                Check In Shift Nurses (1-Tap)
              </button>
            </div>
          )}

          {/* Decision Feedback Banner */}
          {decisionFeedback && (
            <div style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid #10b981', color: '#10b981', padding: '0.75rem 1.25rem', borderRadius: 6, fontSize: '0.85rem', fontWeight: 600 }}>
              {decisionFeedback}
            </div>
          )}

          {/* Ward Shift & Staff Availability Roster */}
          <div className="room-box" style={{ padding: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
              <div>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)', margin: 0 }}>
                  Ward Shift & Staff Availability Roster
                </h4>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {staff.filter((s: any) => s.onWard).length} of {staff.length} on ward
                </span>
              </div>
              <button
                className="btn-outline"
                style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                onClick={handleCheckInAllShiftStaff}
              >
                Check In All Shift Staff
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 10 }}>
              {staff.map((st: any) => (
                <div
                  key={st.staffId}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid ' + (st.onWard ? 'rgba(16,185,129,0.4)' : 'var(--border-subtle)'),
                    borderRadius: 6,
                    padding: '0.75rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontWeight: 800, color: 'var(--text-main)', fontSize: '0.9rem' }}>{st.displayName} ({st.staffId})</span>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                        {st.role.replace('_', ' ')} {st.skills?.length > 0 ? `· [${st.skills.join(', ')}]` : ''}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 800,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: st.onWard ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.15)',
                        color: st.onWard ? '#10b981' : '#94a3b8'
                      }}
                    >
                      {st.onWard ? 'ON WARD' : 'OFF WARD'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                    {!st.onWard ? (
                      <button
                        className="btn-success"
                        onClick={() => handleToggleStaffPresence(st.staffId, true, 'shift_start')}
                        style={{ flex: 1, padding: '4px 8px', fontSize: '0.75rem' }}
                      >
                        Check In (On Ward)
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn-outline"
                          onClick={() => handleToggleStaffPresence(st.staffId, false, 'break_start')}
                          style={{ flex: 1, padding: '4px 8px', fontSize: '0.75rem' }}
                        >
                          Break
                        </button>
                        <button
                          className="btn-outline"
                          onClick={() => handleToggleStaffPresence(st.staffId, false, 'called_away')}
                          style={{ flex: 1, padding: '4px 8px', fontSize: '0.75rem', borderColor: 'rgba(239,68,68,0.3)', color: '#ef4444' }}
                        >
                          Called Away
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {suggestions.length === 0 && (
            <div className="room-box" style={{ padding: '2.5rem 1.5rem', textAlign: 'center', border: '1px dashed rgba(59,130,246,0.3)' }}>
              <Sparkles size={36} color="#0284c7" style={{ margin: '0 auto 12px' }} />
              <h4 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)' }}>No Rebalancing Calculations Pending</h4>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: 500, margin: '8px auto 16px' }}>
                Click "Calculate Optimal Rebalance" to trigger Google OR-Tools MIP solver. It distributes bed assignments across available nurses according to live NEWS2 acuity, continuity of care, and room walking distance.
              </p>
              <button className="btn-primary" onClick={handleRequestSuggestion} disabled={requestingSug}>
                {requestingSug ? 'Calculating OR-Tools Optimization...' : 'Run OR-Tools Solver Now'}
              </button>
            </div>
          )}

          {suggestions.map(sug => (
            <div key={sug.suggestionId} className="room-box" style={{ padding: '1.5rem', border: '1px solid rgba(59,130,246,0.3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="advisory-badge">{STRINGS.assignments.advisoryBadge}</span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Status: {sug.status}</span>
              </div>

              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 12 }}>
                Trigger: {sug.trigger}
              </div>

              <div style={{ marginTop: 14 }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>Proposed Bed Transfers</h4>
                <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                  {sug.changes.map((ch: any, idx: number) => (
                    <div key={idx} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', padding: '0.5rem 0.85rem', borderRadius: 6, fontSize: '0.85rem', color: 'var(--text-main)' }}>
                      Bed <strong>{ch.bed}</strong>: {ch.fromStaffId} → <span style={{ color: '#0284c7', fontWeight: 700 }}>{ch.toStaffId}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ marginTop: 14 }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>Workload Rebalance (Acuity Weighted)</h4>
                <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
                  {sug.loadBefore && Object.keys(sug.loadBefore).map(stId => (
                    <div key={stId} style={{ background: 'var(--bg-surface)', padding: '0.6rem 1rem', borderRadius: 6, border: '1px solid var(--border-subtle)', minWidth: 100 }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>{stId} Load</div>
                      <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', marginTop: 2 }}>
                        {sug.loadBefore[stId]} → <span style={{ color: '#10b981' }}>{sug.loadAfter?.[stId] ?? '—'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ marginTop: 14 }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>{STRINGS.assignments.reasonsTitle}</h4>
                <ul style={{ fontSize: '0.85rem', color: 'var(--text-main)', paddingLeft: 18, marginTop: 6, lineHeight: 1.6 }}>
                  {sug.reasons.map((r: string, idx: number) => (
                    <li key={idx} style={{ color: 'var(--text-main)' }}>{r}</li>
                  ))}
                </ul>
              </div>

              {sug.status === 'pending' && (
                <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                  <button
                    className="btn-success"
                    onClick={() => handleDecideSuggestion(sug.suggestionId, 'approve')}
                    disabled={decidingSug}
                    id="btn-approve-assignment"
                  >
                    <Check size={16} style={{ display: 'inline', marginRight: 6 }} />
                    {STRINGS.assignments.approveBtn}
                  </button>
                  <button
                    className="btn-outline"
                    onClick={() => handleDecideSuggestion(sug.suggestionId, 'reject')}
                    disabled={decidingSug}
                  >
                    <X size={16} style={{ display: 'inline', marginRight: 6 }} />
                    {STRINGS.assignments.rejectBtn}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 4. SIMPY WHAT-IF SIMULATION TAB */}
      {activeTab === 'whatif' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.whatIf.title}</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{STRINGS.whatIf.subtitle}</p>
          </div>

          <div className="room-box" style={{ padding: '1.5rem' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: 8, color: 'var(--text-main)' }}>Select Shift Disruptions to Inject:</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {[
                { id: 'staff_leaves', label: '1 Nurse Called Away (Mid-Shift)' },
                { id: 'admissions', label: '4 Urgent Emergency Admissions' },
                { id: 'call_surge', label: 'Call Volume Peak (26 calls/hr)' },
                { id: 'route_comfort_to_assistants', label: 'Route Comfort Calls to Care Assistants (40%)' }
              ].map(dis => (
                <button
                  key={dis.id}
                  type="button"
                  className={`radio-pill ${whatIfDisruptions.includes(dis.id) ? 'selected' : ''}`}
                  onClick={() => {
                    if (whatIfDisruptions.includes(dis.id)) {
                      setWhatIfDisruptions(whatIfDisruptions.filter(x => x !== dis.id));
                    } else {
                      setWhatIfDisruptions([...whatIfDisruptions, dis.id]);
                    }
                  }}
                >
                  {dis.label}
                </button>
              ))}
            </div>

            <div style={{ marginTop: 16 }}>
              <button
                className="btn-primary"
                onClick={handleRunWhatIf}
                disabled={runningWhatIf}
                id="btn-run-whatif"
              >
                <Play size={16} />
                {runningWhatIf ? STRINGS.whatIf.running : STRINGS.whatIf.runBtn}
              </button>
            </div>
          </div>

          {whatIfResult && (
            <div className="room-box" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)' }}>Simulation Output (Baseline vs Scenario)</h4>
                <span style={{ fontSize: '0.75rem', color: '#0284c7', fontWeight: 700 }}>{STRINGS.whatIf.percentiles}</span>
              </div>

              <div className="whatif-grid">
                <div className="metric-card">
                  <h4>{STRINGS.whatIf.metrics.wait}</h4>
                  <div className="metric-values">
                    <span className="median-val" style={{ color: whatIfResult.scenario.wait_for_nurse_min.median > 5 ? '#ef4444' : '#10b981' }}>
                      {whatIfResult.scenario.wait_for_nurse_min.median}m
                    </span>
                    <span className="percentiles-band">
                      [{whatIfResult.scenario.wait_for_nurse_min.p5}m – {whatIfResult.scenario.wait_for_nurse_min.p95}m]
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Baseline: {whatIfResult.baseline.wait_for_nurse_min.median}m</span>
                </div>

                <div className="metric-card">
                  <h4>{STRINGS.whatIf.metrics.queue}</h4>
                  <div className="metric-values">
                    <span className="median-val" style={{ color: 'var(--text-main)' }}>
                      {whatIfResult.scenario.queue_length.median}
                    </span>
                    <span className="percentiles-band">
                      [{whatIfResult.scenario.queue_length.p5} – {whatIfResult.scenario.queue_length.p95}]
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Baseline: {whatIfResult.baseline.queue_length.median}</span>
                </div>

                <div className="metric-card">
                  <h4>{STRINGS.whatIf.metrics.utilization}</h4>
                  <div className="metric-values">
                    <span className="median-val" style={{ color: (whatIfResult.scenario.nurse_utilization.median <= 1 ? whatIfResult.scenario.nurse_utilization.median * 100 : whatIfResult.scenario.nurse_utilization.median) > 85 ? '#ea580c' : 'var(--text-main)' }}>
                      {whatIfResult.scenario.nurse_utilization.median <= 1 ? (whatIfResult.scenario.nurse_utilization.median * 100).toFixed(0) : whatIfResult.scenario.nurse_utilization.median}%
                    </span>
                    <span className="percentiles-band">
                      [{whatIfResult.scenario.nurse_utilization.p5 <= 1 ? (whatIfResult.scenario.nurse_utilization.p5 * 100).toFixed(0) : whatIfResult.scenario.nurse_utilization.p5}% – {whatIfResult.scenario.nurse_utilization.p95 <= 1 ? (whatIfResult.scenario.nurse_utilization.p95 * 100).toFixed(0) : whatIfResult.scenario.nurse_utilization.p95}%]
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Baseline: {whatIfResult.baseline.nurse_utilization.median <= 1 ? (whatIfResult.baseline.nurse_utilization.median * 100).toFixed(0) : whatIfResult.baseline.nurse_utilization.median}%
                  </span>
                </div>

                <div className="metric-card">
                  <h4>{STRINGS.whatIf.metrics.overdueMeds}</h4>
                  <div className="metric-values">
                    <span className="median-val" style={{ color: 'var(--text-main)' }}>
                      {whatIfResult.scenario.overdue_meds.median}
                    </span>
                    <span className="percentiles-band">
                      [p5: {whatIfResult.scenario.overdue_meds.p5} – p95: {whatIfResult.scenario.overdue_meds.p95}]
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Baseline: {whatIfResult.baseline.overdue_meds.median}</span>
                </div>
              </div>

              <div style={{ marginTop: 20 }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>{STRINGS.whatIf.assumptionsTitle}</h4>
                <ul style={{ fontSize: '0.85rem', color: 'var(--text-main)', paddingLeft: 18, marginTop: 6, lineHeight: 1.6 }}>
                  {whatIfResult.assumptions.map((asm: string, idx: number) => (
                    <li key={idx}>{asm}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5. MEDICATION TIMELINE TAB */}
      {activeTab === 'meds' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.meds.title}</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Administration record logged with nurse presence. System schedules & reminds; never chooses drugs or doses.
            </p>
          </div>

          {medTimeline?.clashes?.length > 0 && (
            <div style={{ background: 'rgba(249,115,22,0.15)', border: '1px solid #f97316', padding: '0.85rem', borderRadius: 8 }}>
              <div style={{ fontWeight: 700, color: '#ea580c' }}>⚠️ {STRINGS.meds.clashWarning}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-main)', marginTop: 4 }}>
                {medTimeline.clashes[0].reason}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {medTimeline?.doses?.map((dose: any) => (
              <div
                key={dose.doseId}
                className="room-box"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderLeft: `4px solid ${dose.status === 'overdue' ? '#ef4444' : dose.status === 'given' ? '#10b981' : '#f59e0b'}`
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 800, color: 'var(--text-main)', fontSize: '1.05rem' }}>Bed {dose.bed}</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{dose.label}</span>
                    {dose.status === 'overdue' && (
                      <span style={{ background: '#ef4444', color: 'white', fontSize: '0.65rem', fontWeight: 800, padding: '2px 6px', borderRadius: 3 }}>
                        {STRINGS.meds.overdueWarning}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    Scheduled: {new Date(dose.due).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} | Status: <strong>{dose.status.toUpperCase()}</strong>
                  </div>
                  {dose.patientReportedAt && (
                    <div style={{ fontSize: '0.75rem', color: '#0284c7', marginTop: 4, fontWeight: 600 }}>
                      ℹ {STRINGS.meds.patientReported}
                    </div>
                  )}
                </div>

                <div>
                  {dose.status !== 'given' ? (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn-success"
                        onClick={() => handleAdministerMed(dose.doseId, 'given')}
                      >
                        {STRINGS.meds.markGiven}
                      </button>
                      <button
                        className="btn-outline"
                        onClick={() => handleAdministerMed(dose.doseId, 'not_given')}
                      >
                        {STRINGS.meds.markNotGiven}
                      </button>
                    </div>
                  ) : (
                    <span style={{ color: '#10b981', fontWeight: 700, fontSize: '0.85rem' }}>
                      ✓ Administered by {dose.administeredBy}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. FAMILY CARE LINK TAB */}
      {activeTab === 'family' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{STRINGS.family.title}</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Consent-first window for relatives. Outbound push only. Invariant 2 strictly active: vitals, scores, and drugs never leave the ward.
            </p>
          </div>

          {/* Consent & Invite Generation */}
          <div className="room-box" style={{ padding: '1.5rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 8, color: 'var(--text-main)' }}>{STRINGS.family.consentTitle} & Invite Generator</h4>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={consentName}
                onChange={e => setConsentName(e.target.value)}
                placeholder="Relative Name & Relation"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.6rem',
                  borderRadius: 6,
                  flex: 1,
                  minWidth: 200
                }}
              />
              <button className="btn-primary" onClick={handleCreateConsentAndInvite} id="btn-create-family-invite">
                Record Consent & Issue Invite
              </button>
            </div>

            {inviteResult && (
              <div style={{ background: 'rgba(16,185,129,0.15)', border: '1px solid #10b981', padding: '1rem', borderRadius: 8, marginTop: 16 }}>
                <div style={{ fontWeight: 800, color: '#10b981' }}>✓ One-Time Relative Invite Created!</div>
                <div style={{ marginTop: 6, fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  Hand this PIN code to the relative: <strong style={{ color: '#0284c7', fontSize: '1.2rem', letterSpacing: 2 }}>{inviteResult.code}</strong>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  Invite URL: <a href="http://localhost:5174" target="_blank" rel="noreferrer" style={{ color: '#0284c7', fontWeight: 600 }}>http://localhost:5174</a>
                </div>
              </div>
            )}
          </div>

          {/* Nurse Approval Queue for Updates */}
          <div className="room-box" style={{ padding: '1.5rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 8, color: 'var(--text-main)' }}>Draft Note for Relatives</h4>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <input
                type="text"
                value={draftNote}
                onChange={e => setDraftNote(e.target.value)}
                placeholder="Draft reassuring nurse note (e.g. resting comfortably, appetite good)"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.6rem',
                  borderRadius: 6,
                  flex: 1,
                  minWidth: 240
                }}
              />
              <button className="btn-primary" onClick={handleDraftFamilyNote}>
                Queue Draft
              </button>
            </div>

            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginTop: 20, marginBottom: 8, color: 'var(--text-main)' }}>
              {STRINGS.family.queueTitle}
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {familyUpdates.map((upd: any) => (
                <div
                  key={upd.updateId}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.85rem',
                    borderRadius: 6,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}
                >
                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#0284c7', textTransform: 'uppercase', fontWeight: 700 }}>
                      {upd.kind.replace('_', ' ')}
                    </span>
                    <div style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginTop: 2 }}>
                      "{upd.text}"
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                      Status: <strong>{upd.status}</strong>
                    </div>
                  </div>

                  {upd.status === 'pending_approval' && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn-success"
                        onClick={() => handleDecideFamilyUpdate(upd.updateId, 'approve')}
                      >
                        {STRINGS.family.approveUpdate}
                      </button>
                      <button
                        className="btn-outline"
                        onClick={() => handleDecideFamilyUpdate(upd.updateId, 'reject')}
                      >
                        {STRINGS.family.rejectUpdate}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
