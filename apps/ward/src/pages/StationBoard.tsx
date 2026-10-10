import React, { useState } from 'react';
import { STRINGS } from '../i18n/strings';
import { AlertCircle, Info, ShieldCheck, X, Bell, User } from 'lucide-react';

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
}

export const StationBoard: React.FC<StationBoardProps> = ({
  beds,
  calls,
  alerts: _alerts,
  triageMetrics,
  onOpenFastEntry
}) => {
  const [selectedBed, setSelectedBed] = useState<any | null>(null);

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
        onClick={() => setSelectedBed(bed)}
        id={`bed-card-${bedId}`}
      >
        {call && (
          <div className={`bed-call-banner ${call.state}`}>
            <span>
              <Bell size={12} style={{ display: 'inline', marginRight: 4 }} />
              {call.kind === 'assist' ? STRINGS.calls.assistCall : STRINGS.calls.comfortCall}
            </span>
            <span style={{ textTransform: 'uppercase' }}>{call.state}</span>
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
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{prioritySortedBeds.length} Patients</span>
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
                    <strong style={{ fontSize: '1rem', color: '#fff' }}>{bed.bed}</strong>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                      ({bed.assignedNurse})
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
                    {bed.admission?.patientRef || 'Empty'}
                  </div>
                  {isPartial && (
                    <span style={{ fontSize: '0.65rem', color: '#f59e0b', fontWeight: 700 }}>
                      ⚠ Partial: {bed.news2?.missing?.join(', ')}
                    </span>
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
                <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                  {selectedBed.admission?.patientRef || 'Empty'} | Acuity {selectedBed.admission?.acuity || 1}
                </span>
              </div>
              <button className="modal-close-btn" onClick={() => setSelectedBed(null)}>
                <X size={20} />
              </button>
            </div>

            <div className="modal-body">
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
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#94a3b8' }}>Total NEWS2 Early-Warning Score</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#fff' }}>
                    {selectedBed.news2?.total ?? '—'} ({selectedBed.news2?.band.toUpperCase()})
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#e2e8f0', marginTop: 4 }}>
                    {selectedBed.news2?.response}
                  </div>
                  {selectedBed.news2?.confidence && (
                    <div style={{ fontSize: '0.75rem', color: '#38bdf8', marginTop: 6, fontWeight: 700 }}>
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

              {/* Components Breakdown Table */}
              <div>
                <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', color: '#cbd5e1' }}>Deterministic Parameter Scoring</h4>
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

              {/* Data Invariant Note */}
              <div style={{ fontSize: '0.75rem', color: '#64748b', fontStyle: 'italic', display: 'flex', gap: 6, alignItems: 'center' }}>
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
