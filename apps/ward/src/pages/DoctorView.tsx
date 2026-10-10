import React, { useState, useEffect } from 'react';
import { wardApi } from '../services/api';
import {
  Stethoscope,
  AlertTriangle,
  Send,
  ShieldCheck,
  Signal,
  Check
} from 'lucide-react';

interface DoctorViewProps {
  beds: any[];
  alerts: any[];
  onRefresh?: () => void;
}

export const DoctorView: React.FC<DoctorViewProps> = ({
  beds,
  alerts,
  onRefresh
}) => {
  const [selectedBed, setSelectedBed] = useState<string>('B06');
  const [orderText, setOrderText] = useState<string>('Start O2 via nasal cannula at 2L/min. Repeat arterial blood gas in 30 mins.');
  const [doctorOrders, setDoctorOrders] = useState<any[]>([]);
  const [submittingOrder, setSubmittingOrder] = useState<boolean>(false);
  const [orderSuccessMsg, setOrderSuccessMsg] = useState<string | null>(null);

  const loadDoctorOrders = async () => {
    try {
      const orders = await wardApi.getDoctorOrders();
      setDoctorOrders(orders || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadDoctorOrders();
  }, []);

  const handleAckAlert = async (alertId: string) => {
    await wardApi.acknowledgeAlert(alertId);
    onRefresh?.();
  };

  const handleSendOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderText.trim()) return;
    setSubmittingOrder(true);
    setOrderSuccessMsg(null);
    try {
      await wardApi.createDoctorOrder(selectedBed, orderText.trim());
      setOrderSuccessMsg(`Order dispatched to ward nursing staff for Bed ${selectedBed}!`);
      setOrderText('');
      await loadDoctorOrders();
      onRefresh?.();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmittingOrder(false);
    }
  };

  // Urgent beds with high NEWS2 or active alerts
  const urgentBeds = beds.filter(b => (b.news2?.total || 0) >= 4 || alerts.some(a => a.bed === b.bed));

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Remote Doctor Header */}
      <div className="room-box" style={{ padding: '1.25rem 1.5rem', borderLeft: '5px solid #38bdf8' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ background: '#0284c7', color: 'white', padding: 8, borderRadius: 8 }}>
              <Stethoscope size={24} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>Remote On-Call Doctor Console</h2>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Dr. F (Senior Attending) · Ward W1 Internal Medicine</span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)', padding: '0.35rem 0.75rem', borderRadius: 999, fontSize: '0.75rem', color: '#38bdf8', fontWeight: 700 }}>
            <Signal size={14} />
            <span>Low-Bandwidth Optimized</span>
          </div>
        </div>

        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem', color: '#94a3b8' }}>
          <ShieldCheck size={16} color="#38bdf8" />
          <span>Hard UI Invariant: Orders and validations take ≤ 3 taps. Decisions are logged with doctor identity.</span>
        </div>
      </div>

      {/* Urgent Clinical Escalations List */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={18} color="#f97316" />
            Urgent Clinical Escalations Requiring Attending Review
          </h3>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{urgentBeds.length} Patients Monitored</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {urgentBeds.map(bed => {
            const bedAlert = alerts.find(a => a.bed === bed.bed);
            const n2 = bed.news2;
            const band = n2?.band || 'low';
            const isHigh = n2 && n2.total >= 7;

            return (
              <div
                key={bed.bed}
                className="room-box"
                style={{
                  padding: '1.25rem',
                  border: isHigh ? '2px solid #ef4444' : '1px solid var(--border-subtle)',
                  background: isHigh ? 'rgba(239,68,68,0.06)' : 'var(--bg-card)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>Bed {bed.bed}</span>
                      <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>({bed.admission?.patientRef || 'Patient'})</span>
                      <span className={`score-badge ${band}`} style={{ width: 32, height: 32, fontSize: '1rem' }}>
                        {n2?.total ?? '—'}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: 6 }}>
                      Assigned Nurse: <strong>{bed.assignedNurse}</strong> | Room: <strong>{bed.room}</strong>
                    </div>
                  </div>

                  {/* Algorithmic Confidence Badge (Invariant 12) */}
                  {n2?.confidence && (
                    <div style={{ background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)', borderRadius: 6, padding: '0.4rem 0.75rem', textAlign: 'right' }}>
                      <div style={{ fontSize: '0.75rem', color: '#38bdf8', fontWeight: 800 }}>
                        Confidence: {(n2.confidence.value * 100).toFixed(0)}%
                      </div>
                      <div style={{ fontSize: '0.65rem', color: '#94a3b8', maxWidth: 220 }}>
                        {n2.confidence.basis}
                      </div>
                    </div>
                  )}
                </div>

                {/* Clinical Explanations Trace */}
                <div style={{ marginTop: 10, background: 'var(--bg-surface)', padding: '0.75rem', borderRadius: 6 }}>
                  <div style={{ fontSize: '0.75rem', color: '#cbd5e1', fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
                    Automated Rule Trace Explanation:
                  </div>
                  <ul style={{ fontSize: '0.8rem', color: '#e2e8f0', paddingLeft: 16 }}>
                    {bedAlert?.explanation ? (
                      bedAlert.explanation.map((e: string, i: number) => <li key={i}>{e}</li>)
                    ) : (
                      <li>Score {n2?.total} computed from active telemetry. Response protocol: {n2?.response}</li>
                    )}
                  </ul>
                </div>

                {/* 1-Tap Acknowledge & Direct Order */}
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  {bedAlert && (
                    <button
                      className="btn-success"
                      onClick={() => handleAckAlert(bedAlert.alertId)}
                      style={{ padding: '0.45rem 0.9rem', fontSize: '0.8rem' }}
                    >
                      <Check size={14} style={{ display: 'inline', marginRight: 4 }} />
                      1-Tap Validate & Acknowledge
                    </button>
                  )}
                  <button
                    className="btn-primary"
                    onClick={() => setSelectedBed(bed.bed)}
                    style={{ padding: '0.45rem 0.9rem', fontSize: '0.8rem' }}
                  >
                    Select for Prescription Order
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Doctor Remote Instruction Form (Step ≤ 3 Validation) */}
      <div className="room-box" style={{ padding: '1.5rem', border: '1px solid rgba(56,189,248,0.3)' }}>
        <h3 style={{ fontSize: '1.15rem', fontWeight: 800, marginBottom: 4 }}>
          Dispatch Doctor Clinical Instruction to Ward
        </h3>
        <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: 12 }}>
          Step 1: Pick bed → Step 2: Choose template or type order → Step 3: Dispatch to attending nurses.
        </p>

        {orderSuccessMsg && (
          <div style={{ background: 'rgba(16,185,129,0.15)', border: '1px solid #10b981', color: '#10b981', padding: '0.75rem', borderRadius: 6, marginBottom: '1rem', fontSize: '0.85rem' }}>
            ✓ {orderSuccessMsg}
          </div>
        )}

        <form onSubmit={handleSendOrder} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ minWidth: 160 }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 700 }}>Target Bed</label>
              <select
                value={selectedBed}
                onChange={e => setSelectedBed(e.target.value)}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  color: 'white',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.6rem',
                  borderRadius: 6,
                  marginTop: 4
                }}
              >
                {beds.map(b => (
                  <option key={b.bed} value={b.bed}>
                    Bed {b.bed} ({b.admission?.patientRef || 'Patient'})
                  </option>
                ))}
              </select>
            </div>

            <div style={{ flex: 1 }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 700 }}>Quick Presets (1-Tap Selection)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {[
                  'Start O2 at 2L/min via nasal cannula',
                  'Administer IV Normal Saline 500mL bolus',
                  'Repeat arterial blood gas in 30 mins',
                  'Urgent bedside evaluation by registrar',
                  'Initiate ICU step-down transfer review'
                ].map((preset, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setOrderText(preset)}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      color: '#cbd5e1',
                      padding: '4px 8px',
                      borderRadius: 4,
                      fontSize: '0.75rem',
                      cursor: 'pointer'
                    }}
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 700 }}>Instruction Order Text</label>
            <textarea
              value={orderText}
              onChange={e => setOrderText(e.target.value)}
              rows={3}
              style={{
                width: '100%',
                background: 'var(--bg-surface)',
                color: 'white',
                border: '1px solid var(--border-subtle)',
                padding: '0.75rem',
                borderRadius: 6,
                marginTop: 4,
                fontFamily: 'inherit',
                fontSize: '0.9rem'
              }}
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={submittingOrder}
            style={{ alignSelf: 'flex-start', padding: '0.75rem 1.5rem', background: '#0284c7' }}
          >
            <Send size={16} />
            {submittingOrder ? 'Dispatching...' : 'Dispatch Clinical Order (Step 3/3)'}
          </button>
        </form>
      </div>

      {/* Dispatched Orders Log */}
      <div>
        <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 8, color: '#e2e8f0' }}>
          Attending Orders Dispatched This Shift
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {doctorOrders.map((ord: any) => (
            <div
              key={ord.orderId}
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                padding: '0.85rem',
                borderRadius: 6,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 800, color: '#38bdf8' }}>Bed {ord.bed}</span>
                  <span style={{ fontSize: '0.85rem', color: '#fff' }}>"{ord.orderText}"</span>
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: 4 }}>
                  Dispatched by {ord.doctorName} at {new Date(ord.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
              <span style={{ color: '#10b981', fontSize: '0.75rem', fontWeight: 700 }}>✓ Logged in Audit Log</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
