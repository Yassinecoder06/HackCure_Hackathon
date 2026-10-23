import React, { useState } from 'react';
import { STRINGS } from '../i18n/strings';
import { wardApi } from '../services/api';
import { AlertCircle, Info, ShieldCheck, X, Bell, User, Brain, Sparkles, Send, RefreshCw, ChevronDown, ChevronUp, HeartHandshake, Copy } from 'lucide-react';

interface StationBoardProps {
  beds: any[];
  calls: any[];
  alerts?: any[];
  triageMetrics?: {
    windowS: number;
    triageLatencyMs: {
      p50: number;
      p95: number;
      n: number;
    };
  } | null;
  onOpenFastEntry?: (bedId: string) => void;
  onAcknowledgeAlert?: (alertId: string) => Promise<void>;
  onSilenceAlarm?: () => void;
  isAlarmSounding?: boolean;
  onSelectTab?: (tab: 'board' | 'staff' | 'doctor' | 'twin' | 'fft') => void;
}

export const StationBoard: React.FC<StationBoardProps> = ({
  beds,
  calls,
  alerts,
  triageMetrics,
  onOpenFastEntry,
  onAcknowledgeAlert,
  onSilenceAlarm,
  isAlarmSounding,
  onSelectTab
}) => {
  const [selectedBed, setSelectedBed] = useState<any | null>(null);
  const [llmExplanation, setLlmExplanation] = useState<any | null>(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmQuestion, setLlmQuestion] = useState('');
  const [showFacts, setShowFacts] = useState(false);

  const fetchLlmExplanation = async (bedId: string, q?: string) => {
    setLlmLoading(true);
    try {
      const res = await wardApi.getBedLLMExplanation(bedId, q);
      setLlmExplanation(res);
    } catch (e: any) {
      console.warn('Failed to load LLM explanation:', e);
    } finally {
      setLlmLoading(false);
    }
  };

  // Group beds by room
  const roomsNorth = [
    { id: 'R1', name: 'Room 1 (x: -12m)', beds: ['B01', 'B02'] },
    { id: 'R2', name: 'Room 2 (x: -6m)', beds: ['B03', 'B04'] },
    { id: 'R3', name: 'Room 3 (x: +6m)', beds: ['B05', 'B06'] },
    { id: 'R4', name: 'Room 4 (x: +12m)', beds: ['B07', 'B08'] }
  ];

  const roomsSouth = [
    { id: 'R5', name: 'Room 5 (x: -9m)', beds: ['B09', 'B10'] },
    { id: 'R6', name: 'Room 6 (x: +9m)', beds: ['B11', 'B12'] }
  ];

  // Sort beds by NEWS2 priority
  const prioritySortedBeds = [...beds].sort((a, b) => {
    const bandRank: Record<string, number> = { high: 4, medium: 3, low_medium: 2, low: 1 };
    const rankA = bandRank[a.news2?.band || 'low'] || 0;
    const rankB = bandRank[b.news2?.band || 'low'] || 0;
    if (rankA !== rankB) return rankB - rankA;
    return (b.news2?.total || 0) - (a.news2?.total || 0);
  });

  const getBedCall = (bedId: string) => calls.find(c => c.bed === bedId && c.state !== 'resolved');

  const renderBedCard = (bedId: string) => {
    const bed = beds.find(b => b.bed === bedId);
    if (!bed) return null;

    const call = getBedCall(bedId);
    const n2 = bed.news2;
    const band = n2?.band || 'low';
    const isPartial = n2 && !n2.complete;

    return (
      <div
        key={bedId}
        className={`bed-card band-${band}`}
        onClick={() => {
          setSelectedBed(bed);
          setLlmExplanation(null);
          setLlmQuestion('');
          setShowFacts(false);
          fetchLlmExplanation(bed.bed);
        }}
        id={`bed-card-${bedId}`}
      >
        {call && (
          <div className={`bed-call-banner ${call.state}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <Bell size={12} style={{ display: 'inline', marginRight: 4 }} />
              {call.kind === 'assist' ? STRINGS.calls.assistCall : STRINGS.calls.comfortCall}
            </span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ textTransform: 'uppercase' }}>{call.state}</span>
              {call.state !== 'acknowledged' && (
                <button
                  type="button"
                  onClick={async (e) => {
                    e.stopPropagation();
                    try {
                      await wardApi.acknowledgeCall(call.callId);
                    } catch (err) {
                      console.error('Failed to acknowledge call:', err);
                    }
                  }}
                  style={{
                    background: '#10b981',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: 4,
                    padding: '2px 8px',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    cursor: 'pointer'
                  }}
                >
                  Acknowledge
                </button>
              )}
            </div>
          </div>
        )}

        <div className="bed-top-row">
          <div>
            <div className="bed-id-wrap">
              <span className="bed-tag">{bed.bed}</span>
              <span className="nurse-tag">
                <User size={10} style={{ display: 'inline', marginRight: 2 }} />
                {bed.assignedNurse || 'Unassigned'}
              </span>
            </div>
            <div className="patient-label" title={bed.admission?.patientRef || 'Empty'}>
              {bed.admission?.patientRef || 'Available Bed'}
            </div>
          </div>

          <div className={`score-badge ${band}`}>
            {n2 ? n2.total : '—'}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
          {isPartial && (
            <div className="partial-badge" title={n2?.label}>
              <AlertCircle size={10} />
              <span>{STRINGS.board.partialWarning} ({n2?.missing?.length || 0} missing)</span>
            </div>
          )}
          {n2?.confidence && (
            <div style={{ fontSize: '0.65rem', color: '#38bdf8', fontWeight: 700, padding: '2px 6px', background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.25)', borderRadius: 3 }}>
              Confidence: {(n2.confidence.value * 100).toFixed(0)}%
            </div>
          )}
        </div>

        {/* Mini Vitals Row */}
        <div className="vitals-mini-grid">
          <div className={`param-chip ${bed.vitals.resp_rate?.status || 'missing'}`}>
            <div className="param-name">RR</div>
            <div className="param-val">{bed.vitals.resp_rate?.value ?? '—'}</div>
          </div>
          <div className={`param-chip ${bed.vitals.spo2?.status || 'missing'}`}>
            <div className="param-name">SpO2</div>
            <div className="param-val">{bed.vitals.spo2?.value ? `${bed.vitals.spo2.value}%` : '—'}</div>
          </div>
          <div className={`param-chip ${bed.vitals.pulse?.status || 'missing'}`}>
            <div className="param-name">HR</div>
            <div className="param-val">{bed.vitals.pulse?.value ?? '—'}</div>
          </div>
          <div className={`param-chip ${bed.vitals.sys_bp?.status || 'missing'}`}>
            <div className="param-name">BP</div>
            <div className="param-val">{bed.vitals.sys_bp?.value ?? '—'}</div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="board-container">
      {/* 2D Floor Plan */}
      <div className="board-main">
        <div className="board-banner">
          <div className="board-banner-info">
            <h2>{STRINGS.board.header}</h2>
            <p>{STRINGS.board.floorPlanTitle}</p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div className="advisory-badge">
              <ShieldCheck size={14} />
              <span>{STRINGS.app.principle}</span>
            </div>
            <div style={{ background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)', color: '#38bdf8', padding: '0.35rem 0.75rem', borderRadius: 6, fontSize: '0.75rem', fontWeight: 700 }}>
              ⚡ Triage Latency: {triageMetrics?.triageLatencyMs ? `p50 ${triageMetrics.triageLatencyMs.p50}ms · p95 ${triageMetrics.triageLatencyMs.p95}ms (n=${triageMetrics.triageLatencyMs.n})` : '< 320ms budget'} · Zero-Cloud Ward Network
            </div>
            {onSelectTab && (
              <button
                onClick={() => onSelectTab('twin')}
                style={{
                  background: 'linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)',
                  border: '1px solid #60a5fa',
                  color: '#ffffff',
                  padding: '0.35rem 0.75rem',
                  borderRadius: 6,
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5
                }}
                id="btn-switch-twin3d"
                title="Launch 3D Digital Twin View"
              >
                🏢 3D Digital Twin →
              </button>
            )}
          </div>
        </div>

        <div className="floorplan-wrapper">
          <div className="corridor-header">
            <span>North Wing (Rooms R1 – R4)</span>
            <span>Corridor Axis</span>
          </div>

          {/* North Rooms */}
          <div className="rooms-row">
            {roomsNorth.map(room => (
              <div key={room.id} className="room-box">
                <div className="room-header">
                  <span className="room-title">{room.name}</span>
                </div>
                <div className="beds-grid">
                  {room.beds.map(bedId => renderBedCard(bedId))}
                </div>
              </div>
            ))}
          </div>

          {/* Central Corridor & Nurse Station */}
          <div className="corridor-spine">
            <div className="station-marker">
              🏥 {STRINGS.board.nurseStation}
            </div>
          </div>

          <div className="corridor-header">
            <span>South Wing (Rooms R5 – R6)</span>
            <span>Corridor Axis</span>
          </div>

          {/* South Rooms */}
          <div className="rooms-row">
            {roomsSouth.map(room => (
              <div key={room.id} className="room-box">
                <div className="room-header">
                  <span className="room-title">{room.name}</span>
                </div>
                <div className="beds-grid">
                  {room.beds.map(bedId => renderBedCard(bedId))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Acuity Triage Priority Sidebar */}
      <aside className="triage-sidebar">
        <div className="triage-header">
          <h3>{STRINGS.board.priorityListTitle}</h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{prioritySortedBeds.length} Patients</span>
        </div>

        <div className="triage-list">
          {prioritySortedBeds.map(bed => {
            const band = bed.news2?.band || 'low';
            const total = bed.news2?.total || 0;
            const isPartial = bed.news2 && !bed.news2.complete;

            return (
              <div
                key={bed.bed}
                className={`triage-item ${band}`}
                onClick={() => setSelectedBed(bed)}
                id={`triage-item-${bed.bed}`}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <strong style={{ fontSize: '1rem', color: 'var(--text-main)' }}>{bed.bed}</strong>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      ({bed.assignedNurse})
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-main)' }}>
                    {bed.admission?.patientRef || 'Empty'}
                  </div>
                  {isPartial && (
                    <span style={{ fontSize: '0.65rem', color: '#f59e0b', fontWeight: 700 }}>
                      ⚠ Partial: {bed.news2?.missing?.join(', ')}
                    </span>
                  )}
                  {bed.priority?.reasons && bed.priority.reasons.length > 0 && (
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                      #{bed.priority.rank}: {bed.priority.reasons[0]}
                    </div>
                  )}
                </div>

                <div className={`score-badge ${band}`}>
                  {total}
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Bed Inspector Modal */}
      {selectedBed && (
        <div className="modal-overlay" onClick={() => setSelectedBed(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <h3>Bed {selectedBed.bed} — Clinical Inspection</h3>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  {selectedBed.admission?.patientRef || 'Empty'} | Acuity {selectedBed.admission?.acuity || 1}
                </span>
              </div>
              <button className="modal-close-btn" onClick={() => setSelectedBed(null)}>
                <X size={20} />
              </button>
            </div>

            <div className="modal-body">
              {/* Active Bed Alert Callout & Silence/Ack Action */}
              {(() => {
                const bedAlert = alerts?.find(a => a.bed === selectedBed.bed && a.active !== false);
                if (!bedAlert) return null;
                return (
                  <div
                    style={{
                      padding: '0.85rem 1rem',
                      borderRadius: 8,
                      backgroundColor: '#fef2f2',
                      border: '2px solid #ef4444',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '1rem',
                      boxShadow: '0 2px 8px rgba(239,68,68,0.15)'
                    }}
                  >
                    <div>
                      <div style={{ color: '#991b1b', fontWeight: 800, fontSize: '0.9rem' }}>
                        🚨 Active Deterioration Alert ({bedAlert.priority.toUpperCase()})
                      </div>
                      <div style={{ color: '#7f1d1d', fontSize: '0.8rem', marginTop: 2 }}>
                        {bedAlert.explanation?.[0] || 'Urgent medical intervention recommended'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {isAlarmSounding && onSilenceAlarm && (
                        <button
                          onClick={onSilenceAlarm}
                          style={{
                            background: '#ffffff',
                            color: '#b91c1c',
                            border: '1px solid #f87171',
                            borderRadius: 6,
                            padding: '0.4rem 0.8rem',
                            fontWeight: 700,
                            fontSize: '0.8rem',
                            cursor: 'pointer'
                          }}
                        >
                          Silence Sound
                        </button>
                      )}
                      {onAcknowledgeAlert && (
                        <button
                          onClick={async () => {
                            await onAcknowledgeAlert(bedAlert.alertId);
                          }}
                          style={{
                            background: '#15803d',
                            color: '#ffffff',
                            border: 'none',
                            borderRadius: 6,
                            padding: '0.4rem 0.8rem',
                            fontWeight: 700,
                            fontSize: '0.8rem',
                            cursor: 'pointer'
                          }}
                        >
                          Acknowledge & Clear
                        </button>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Family Care Link (Espace Proches) Banner */}
              {selectedBed.admission && (
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: 8,
                    background: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 10
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ background: '#10b981', color: '#ffffff', padding: 6, borderRadius: 6, display: 'flex' }}>
                      <HeartHandshake size={18} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-main)' }}>
                        Family Care Link (Espace Proches)
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        Bedside PIN Key: <strong style={{ color: '#10b981', letterSpacing: 1 }}>FAM-9921</strong> • Relatives portal
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText('http://localhost:5174?code=FAM-9921');
                        alert('Copied Family Care Link to clipboard: http://localhost:5174?code=FAM-9921');
                      }}
                      style={{
                        background: 'transparent',
                        border: '1px solid rgba(16, 185, 129, 0.4)',
                        color: '#10b981',
                        padding: '4px 10px',
                        borderRadius: 6,
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4
                      }}
                    >
                      <Copy size={12} /> Copy Link
                    </button>
                    <a
                      href="http://localhost:5174?code=FAM-9921"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        background: '#10b981',
                        color: '#ffffff',
                        padding: '5px 12px',
                        borderRadius: 6,
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        textDecoration: 'none',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4
                      }}
                    >
                      Open Portal ↗
                    </a>
                  </div>
                </div>
              )}

              {/* NEWS2 Summary Banner */}
              <div
                style={{
                  padding: '1rem',
                  borderRadius: 8,
                  backgroundColor: `var(--news2-${selectedBed.news2?.band || 'low'}-bg)`,
                  border: `1px solid var(--news2-${selectedBed.news2?.band || 'low'}-border)`,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)' }}>Total NEWS2 Early-Warning Score</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
                    {selectedBed.news2?.total ?? '—'} ({selectedBed.news2?.band.toUpperCase()})
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', marginTop: 4 }}>
                    {selectedBed.news2?.response}
                  </div>
                  {selectedBed.news2?.confidence && (
                    <div style={{ fontSize: '0.75rem', color: '#0284c7', marginTop: 6, fontWeight: 700 }}>
                      Algorithmic Confidence: {(selectedBed.news2.confidence.value * 100).toFixed(0)}% ({selectedBed.news2.confidence.basis})
                    </div>
                  )}
                </div>
                {onOpenFastEntry && (
                  <button
                    className="btn-primary"
                    onClick={() => {
                      const bedId = selectedBed.bed;
                      setSelectedBed(null);
                      onOpenFastEntry(bedId);
                    }}
                  >
                    Enter Vitals
                  </button>
                )}
              </div>

              {/* Ward Priority Ranking & Clinical Rationale (Bilingual explainability from main) */}
              {selectedBed.priority && (
                <div style={{ padding: '0.75rem 1rem', borderRadius: 8, background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-main)' }}>
                        Clinical Priority Ranking
                      </span>
                      <span style={{ fontSize: '0.72rem', background: '#2563eb', color: '#ffffff', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
                        Rank #{selectedBed.priority.rank} of {selectedBed.priority.of}
                      </span>
                    </div>
                    {selectedBed.news2Trend && selectedBed.news2Trend.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        <span>Trend:</span>
                        {selectedBed.news2Trend.map((t: any) => (
                          <span key={t.minutesAgo} style={{ background: 'var(--bg-body)', padding: '1px 5px', borderRadius: 3, fontWeight: 600 }}>
                            -{t.minutesAgo}m: {t.total}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {selectedBed.priority.reasons?.map((reason: string, idx: number) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                        <span style={{ color: '#2563eb' }}>•</span>
                        <span>{reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Components Breakdown Table */}
              <div>
                <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-main)' }}>Deterministic Parameter Scoring</h4>
                <table className="explainer-table">
                  <thead>
                    <tr>
                      <th>Parameter</th>
                      <th>Observed Value</th>
                      <th>Status</th>
                      <th>Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedBed.news2?.components.map((c: any) => (
                      <tr key={c.param}>
                        <td style={{ fontWeight: 600 }}>{c.param.replace('_', ' ').toUpperCase()}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>
                          {c.value !== undefined ? String(c.value) : 'Absent (Not entered)'}
                        </td>
                        <td>
                          <span style={{
                            fontSize: '0.75rem',
                            padding: '2px 6px',
                            borderRadius: 4,
                            backgroundColor: c.status === 'fresh' ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                            color: c.status === 'fresh' ? '#10b981' : '#f59e0b',
                            textTransform: 'uppercase'
                          }}>
                            {c.status}
                          </span>
                        </td>
                        <td>
                          <span className={`pts-tag ${c.points > 0 ? 'points' : 'zero'}`}>
                            +{c.points}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Local LLM Grounded Explainability (ADR 0013) */}
              <div
                style={{
                  background: 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)',
                  borderRadius: 10,
                  border: '1px solid #3b82f6',
                  padding: '1.1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.8rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Brain size={18} color="#60a5fa" />
                    <span style={{ fontWeight: 800, fontSize: '0.92rem', color: '#f8fafc' }}>
                      Grounded AI Clinical Handover
                    </span>
                    <span style={{ fontSize: '0.7rem', background: '#2563eb', color: '#ffffff', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
                      gemma4-ab-qat:e4b (Local QAT)
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '0.68rem', color: '#10b981', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)', padding: '2px 6px', borderRadius: 4, fontWeight: 700 }}>
                      ADR 0013 Verified
                    </span>
                    <button
                      type="button"
                      onClick={() => fetchLlmExplanation(selectedBed.bed, llmQuestion || undefined)}
                      disabled={llmLoading}
                      title="Re-run local Gemma explainability"
                      style={{
                        background: '#334155',
                        border: 'none',
                        color: '#94a3b8',
                        padding: '3px 8px',
                        borderRadius: 4,
                        fontSize: '0.72rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4
                      }}
                    >
                      <RefreshCw size={12} className={llmLoading ? 'spin' : ''} />
                      {llmLoading ? 'Thinking...' : 'Refresh'}
                    </button>
                  </div>
                </div>

                {/* Body / Result */}
                {llmLoading ? (
                  <div style={{ padding: '1rem', background: '#0b1120', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 10, color: '#94a3b8', fontSize: '0.82rem' }}>
                    <Sparkles size={16} color="#38bdf8" />
                    <span>Querying local Gemma 4 QAT model on ward twin facts (temperature 0.0)...</span>
                  </div>
                ) : llmExplanation ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                    <div style={{ padding: '0.85rem', background: '#0b1120', borderRadius: 8, border: '1px solid #1e293b', fontSize: '0.85rem', lineHeight: 1.5, color: '#e2e8f0' }}>
                      {llmExplanation.summary}
                    </div>

                    {/* Citations & Disclaimer */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem', color: '#94a3b8', flexWrap: 'wrap', gap: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>Citations:</span>
                        {llmExplanation.citations?.map((c: string) => (
                          <span key={c} style={{ background: '#1e3a8a', color: '#93c5fd', padding: '1px 5px', borderRadius: 3, fontWeight: 700, fontFamily: 'monospace' }}>
                            {c}
                          </span>
                        ))}
                      </div>
                      <span style={{ fontStyle: 'italic', color: '#64748b' }}>
                        {llmExplanation.disclaimer}
                      </span>
                    </div>

                    {/* Collapsible Facts */}
                    {llmExplanation.facts?.length > 0 && (
                      <div>
                        <button
                          type="button"
                          onClick={() => setShowFacts(!showFacts)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: '#38bdf8',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '2px 0',
                            fontWeight: 600
                          }}
                        >
                          {showFacts ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                          {showFacts ? 'Hide' : 'Inspect'} Grounded Twin Facts ({llmExplanation.facts.length})
                        </button>
                        {showFacts && (
                          <div style={{ marginTop: 6, padding: '0.6rem', background: '#0b1120', borderRadius: 6, fontSize: '0.72rem', color: '#cbd5e1', display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflowY: 'auto' }}>
                            {llmExplanation.facts.map((f: string, i: number) => (
                              <div key={i} style={{ fontFamily: 'monospace' }}>{f}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => fetchLlmExplanation(selectedBed.bed)}
                    style={{
                      background: '#2563eb',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: 6,
                      padding: '0.5rem 1rem',
                      fontSize: '0.82rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      alignSelf: 'flex-start'
                    }}
                  >
                    <Sparkles size={14} /> Generate Handover Briefing with Local Gemma
                  </button>
                )}

                {/* Free-text Clinical Q&A Bar */}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (llmQuestion.trim()) {
                      fetchLlmExplanation(selectedBed.bed, llmQuestion.trim());
                    }
                  }}
                  style={{ display: 'flex', gap: 6, marginTop: 4 }}
                >
                  <input
                    type="text"
                    value={llmQuestion}
                    onChange={(e) => setLlmQuestion(e.target.value)}
                    placeholder="Ask local Gemma 4 a clinical question about Bed..."
                    style={{
                      flex: 1,
                      background: '#0b1120',
                      border: '1px solid #334155',
                      borderRadius: 6,
                      padding: '6px 10px',
                      color: '#f8fafc',
                      fontSize: '0.78rem'
                    }}
                  />
                  <button
                    type="submit"
                    disabled={llmLoading || !llmQuestion.trim()}
                    style={{
                      background: '#3b82f6',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: 6,
                      padding: '6px 12px',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4
                    }}
                  >
                    <Send size={12} /> Ask
                  </button>
                </form>

                {/* Quick Prompts */}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setLlmQuestion('Résumé clinique en français pour la relève infirmière.');
                      fetchLlmExplanation(selectedBed.bed, 'Résumé clinique en français pour la relève infirmière.');
                    }}
                    style={{ background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', borderRadius: 4, padding: '2px 8px', fontSize: '0.68rem', cursor: 'pointer' }}
                  >
                    🇫🇷 Relève en français
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setLlmQuestion('Why is this bed prioritized and what is the emergency protocol?');
                      fetchLlmExplanation(selectedBed.bed, 'Why is this bed prioritized and what is the emergency protocol?');
                    }}
                    style={{ background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', borderRadius: 4, padding: '2px 8px', fontSize: '0.68rem', cursor: 'pointer' }}
                  >
                    ⚡ Prioritization Rationale
                  </button>
                </div>
              </div>

              {/* Data Invariant Note */}
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic', display: 'flex', gap: 6, alignItems: 'center' }}>
                <Info size={14} />
                <span>Safety Invariant 5: Incomplete parameters are never treated as normal. Scores computed with missing inputs are labelled partial.</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
