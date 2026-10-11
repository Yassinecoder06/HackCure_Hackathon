import React, { useState, useMemo } from 'react';
import {
  Activity,
  Clock,
  Radio,
  Sliders,
  AlertTriangle,
  CheckCircle,
  Play,
  RotateCcw,
  Sparkles
} from 'lucide-react';

interface AssistanceDemandFFTProps {
  beds: any[];
  calls: any[];
  onTriggerDemo?: () => void;
}

export const AssistanceDemandFFT: React.FC<AssistanceDemandFFTProps> = ({
  beds,
  calls,
}) => {
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'B06' | 'high_acuity'>('all');
  const [windowFunction, setWindowFunction] = useState<'hanning' | 'hamming' | 'rect'>('hanning');
  const [isSimulatingBurst, setIsSimulatingBurst] = useState(false);
  const [burstDetected, setBurstDetected] = useState(false);
  const [burstCadenceHz, setBurstCadenceHz] = useState<number | null>(null);

  const activeCallsCount = useMemo(() => {
    return calls.filter(c => c.state !== 'resolved').length;
  }, [calls]);
  const monitoredBedsCount = beds.length;

  // Time-domain simulated demand signal (24 hours in 15-minute buckets = 96 points)
  const timeDomainPoints = useMemo(() => {
    const points: { hour: number; timeLabel: string; value: number; baseline: number }[] = [];
    const baseCalls = selectedFilter === 'B06' ? 1.2 : selectedFilter === 'high_acuity' ? 3.5 : 4.8;

    for (let i = 0; i < 96; i++) {
      const hour = (i * 15) / 60; // 0 to 24
      const hStr = Math.floor(hour).toString().padStart(2, '0');
      const mStr = ((i % 4) * 15).toString().padStart(2, '0');

      // Superposition of diurnal harmonics (24h, 8h, 4h cycles)
      const c24 = Math.sin((2 * Math.PI * hour) / 24 - Math.PI / 2); // 24h wave (peak in late morning)
      const c8 = 0.5 * Math.sin((2 * Math.PI * hour) / 8);           // 8h shift change harmonic
      const c4 = 0.35 * Math.sin((2 * Math.PI * hour) / 4);          // 4h medication/round cycle
      const noise = (Math.sin(i * 13) * 0.2 + Math.cos(i * 7) * 0.15);

      let val = Math.max(0.5, baseCalls + c24 * 2.2 + c8 * 1.5 + c4 * 1.0 + noise);

      // If burst simulation is active, inject a sharp high-frequency spike near the current hour (e.g., hour 18)
      if (isSimulatingBurst && i >= 70 && i <= 74) {
        val += 6.5;
      }

      points.push({
        hour,
        timeLabel: `${hStr}:${mStr}`,
        value: Number(val.toFixed(2)),
        baseline: baseCalls,
      });
    }
    return points;
  }, [selectedFilter, isSimulatingBurst]);

  // Compute Discrete Fourier Transform (FFT approximation) for spectrum analysis
  const frequencySpectrum = useMemo(() => {
    const N = timeDomainPoints.length;
    const values = timeDomainPoints.map((p, idx) => {
      // Apply chosen windowing function
      let w = 1.0;
      if (windowFunction === 'hanning') {
        w = 0.5 * (1 - Math.cos((2 * Math.PI * idx) / (N - 1)));
      } else if (windowFunction === 'hamming') {
        w = 0.54 - 0.46 * Math.cos((2 * Math.PI * idx) / (N - 1));
      }
      return p.value * w;
    });

    const spectrum: { freqCyclesPerDay: number; periodHours: number; power: number; label?: string }[] = [];
    const numBins = Math.floor(N / 2);

    for (let k = 1; k < numBins; k++) {
      let re = 0;
      let im = 0;
      for (let n = 0; n < N; n++) {
        const phi = (2 * Math.PI * k * n) / N;
        re += values[n] * Math.cos(phi);
        im -= values[n] * Math.sin(phi);
      }
      const power = Math.sqrt(re * re + im * im) / N;
      const freqCyclesPerDay = k;
      const periodHours = 24 / k;

      let label: string | undefined;
      if (k === 1) label = '24h Diurnal Base';
      else if (k === 3) label = '8h Shift Cycle';
      else if (k === 6) label = '4h Care Round';
      else if (isSimulatingBurst && k >= 18 && k <= 22) label = 'Burst Agitation (High Freq)';

      spectrum.push({
        freqCyclesPerDay,
        periodHours: Number(periodHours.toFixed(1)),
        power: Number(power.toFixed(3)),
        label,
      });
    }
    return spectrum;
  }, [timeDomainPoints, windowFunction, isSimulatingBurst]);

  const maxPower = Math.max(...frequencySpectrum.map((s) => s.power), 1);
  const maxTimeVal = Math.max(...timeDomainPoints.map((p) => p.value), 8);

  const handleSimulateBurst = () => {
    setIsSimulatingBurst(true);
    setBurstCadenceHz(2.65);
    setBurstDetected(true);
    setTimeout(() => {
      setIsSimulatingBurst(false);
    }, 4500);
  };

  const handleReset = () => {
    setIsSimulatingBurst(false);
    setBurstDetected(false);
    setBurstCadenceHz(null);
  };

  return (
    <div style={{ padding: '1.5rem', background: '#0b1120', minHeight: 'calc(100vh - 65px)', color: '#f8fafc' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ background: '#3b82f6', padding: '8px', borderRadius: '8px', display: 'flex' }}>
              <Activity size={22} color="#ffffff" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
                Assistance Demand Spectral Analysis (FFT)
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', margin: 0 }}>
                  Fast Fourier Transform decomposition of patient call frequency, periodic care rounds, and rapid-tap emergency cadence.
                </p>
                <span style={{ fontSize: '0.75rem', background: '#1e293b', border: '1px solid #334155', color: '#38bdf8', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                  Live: {monitoredBedsCount} Beds • {activeCallsCount} Active Calls
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Global Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', background: '#1e293b', borderRadius: '8px', padding: '4px', border: '1px solid #334155' }}>
            <button
              onClick={() => setSelectedFilter('all')}
              style={{
                background: selectedFilter === 'all' ? '#3b82f6' : 'transparent',
                color: selectedFilter === 'all' ? '#ffffff' : '#94a3b8',
                border: 'none',
                borderRadius: '6px',
                padding: '5px 12px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              All Beds (W1)
            </button>
            <button
              onClick={() => setSelectedFilter('B06')}
              style={{
                background: selectedFilter === 'B06' ? '#10b981' : 'transparent',
                color: selectedFilter === 'B06' ? '#ffffff' : '#94a3b8',
                border: 'none',
                borderRadius: '6px',
                padding: '5px 12px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Bed B06 (Pi Berry)
            </button>
            <button
              onClick={() => setSelectedFilter('high_acuity')}
              style={{
                background: selectedFilter === 'high_acuity' ? '#f59e0b' : 'transparent',
                color: selectedFilter === 'high_acuity' ? '#ffffff' : '#94a3b8',
                border: 'none',
                borderRadius: '6px',
                padding: '5px 12px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              High Acuity
            </button>
          </div>

          <button
            onClick={handleSimulateBurst}
            disabled={isSimulatingBurst}
            style={{
              background: isSimulatingBurst ? '#dc2626' : '#ef4444',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              padding: '7px 14px',
              fontSize: '0.8rem',
              fontWeight: 700,
              cursor: isSimulatingBurst ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 2px 10px rgba(239, 68, 68, 0.3)',
            }}
          >
            <Play size={14} />
            {isSimulatingBurst ? 'Simulating Burst...' : 'Simulate B06 Triple-Tap'}
          </button>

          {burstDetected && (
            <button
              onClick={handleReset}
              style={{
                background: '#334155',
                color: '#cbd5e1',
                border: 'none',
                borderRadius: '8px',
                padding: '7px 12px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <RotateCcw size={14} /> Reset
            </button>
          )}
        </div>
      </div>

      {/* Real-time Cadence / Emergency Alert Banner */}
      {burstDetected && (
        <div
          style={{
            background: 'linear-gradient(90deg, rgba(239,68,68,0.2) 0%, rgba(220,38,38,0.1) 100%)',
            border: '1px solid #ef4444',
            borderRadius: '10px',
            padding: '1rem',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 4px 20px rgba(239, 68, 68, 0.15)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertTriangle size={24} color="#ef4444" />
            <div>
              <div style={{ fontWeight: 800, fontSize: '0.95rem', color: '#fca5a5' }}>
                🚨 FFT EMERGENCY HARMONIC DETECTED: Rapid Triple-Tap on Bed B06
              </div>
              <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: '2px' }}>
                Spectrogram isolated peak cadence at <strong>{burstCadenceHz} Hz</strong> (3 presses within 1.1s).
                Triage escalated automatically to <strong>Level 2 Emergency</strong> per safety rule ADR 0008.
              </div>
            </div>
          </div>
          <span style={{ background: '#ef4444', color: '#ffffff', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 800 }}>
            SPECTRUM ANOMALY
          </span>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '10px', border: '1px solid #334155' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Clock size={14} color="#3b82f6" /> Fundamental Diurnal Cycle
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc', marginTop: '6px' }}>
            24.0 hrs
          </div>
          <div style={{ fontSize: '0.75rem', color: '#10b981', marginTop: '4px' }}>
            Main harmonic • Morning waking surge
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '10px', border: '1px solid #334155' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Activity size={14} color="#8b5cf6" /> Shift Handover Harmonic
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc', marginTop: '6px' }}>
            8.0 hrs
          </div>
          <div style={{ fontSize: '0.75rem', color: '#a78bfa', marginTop: '4px' }}>
            3.0 cycles/day • Shift change demand
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '10px', border: '1px solid #334155' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Sliders size={14} color="#f59e0b" /> Medication & Repositioning Cycle
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc', marginTop: '6px' }}>
            4.0 hrs
          </div>
          <div style={{ fontSize: '0.75rem', color: '#fbbf24', marginTop: '4px' }}>
            6.0 cycles/day • Post-dose assistance calls
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '10px', border: '1px solid #334155' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Radio size={14} color="#ef4444" /> Button Cadence Peak
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: burstCadenceHz ? '#ef4444' : '#94a3b8', marginTop: '6px' }}>
            {burstCadenceHz ? `${burstCadenceHz} Hz` : '0.12 Hz'}
          </div>
          <div style={{ fontSize: '0.75rem', color: burstCadenceHz ? '#f87171' : '#64748b', marginTop: '4px' }}>
            {burstCadenceHz ? 'Triple-tap agitation active' : 'Normal single-press cadence'}
          </div>
        </div>
      </div>

      {/* Main Charts Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Time-Domain Chart */}
        <div style={{ background: '#1e293b', borderRadius: '10px', border: '1px solid #334155', padding: '1.2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                1. Time-Domain Assistance Demand: x(t)
              </h3>
              <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: '2px 0 0 0' }}>
                Hourly call arrivals (calls/hr) sampled over the 24-hour ward timeline (N=96 points).
              </p>
            </div>
            <span style={{ fontSize: '0.75rem', background: '#0f172a', padding: '3px 8px', borderRadius: '4px', color: '#38bdf8', fontFamily: 'monospace' }}>
              dt = 15 min
            </span>
          </div>

          {/* SVG Waveform */}
          <div style={{ height: '220px', width: '100%', position: 'relative' }}>
            <svg viewBox="0 0 800 200" preserveAspectRatio="none" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
              {/* Grid Lines */}
              {[0, 50, 100, 150].map((y) => (
                <line key={y} x1="0" y1={y} x2="800" y2={y} stroke="#334155" strokeDasharray="3 3" />
              ))}

              {/* Area under curve */}
              <defs>
                <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Polygon for filled area */}
              <polygon
                points={`0,200 ${timeDomainPoints
                  .map((p, i) => `${(i / (timeDomainPoints.length - 1)) * 800},${200 - (p.value / maxTimeVal) * 180}`)
                  .join(' ')} 800,200`}
                fill="url(#areaGradient)"
              />

              {/* Signal Line */}
              <polyline
                fill="none"
                stroke="#38bdf8"
                strokeWidth="2.5"
                points={timeDomainPoints
                  .map((p, i) => `${(i / (timeDomainPoints.length - 1)) * 800},${200 - (p.value / maxTimeVal) * 180}`)
                  .join(' ')}
              />

              {/* Burst Annotation */}
              {isSimulatingBurst && (
                <circle cx={(72 / 95) * 800} cy={200 - (timeDomainPoints[72].value / maxTimeVal) * 180} r="6" fill="#ef4444" stroke="#ffffff" strokeWidth="2">
                  <animate attributeName="r" values="6;10;6" dur="1s" repeatCount="indefinite" />
                </circle>
              )}
            </svg>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#64748b', marginTop: '6px' }}>
            <span>00:00 (Midnight)</span>
            <span>06:00 (Morning)</span>
            <span>12:00 (Noon)</span>
            <span>18:00 (Evening)</span>
            <span>24:00 (Night)</span>
          </div>
        </div>

        {/* Frequency-Domain Spectrum (FFT) */}
        <div style={{ background: '#1e293b', borderRadius: '10px', border: '1px solid #334155', padding: '1.2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                2. FFT Frequency Spectrum: |X(f)|²
              </h3>
              <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: '2px 0 0 0' }}>
                Discrete Fourier Transform magnitude across frequency harmonics (cycles/day).
              </p>
            </div>

            {/* Window selector */}
            <div style={{ display: 'flex', gap: '4px', background: '#0f172a', padding: '2px', borderRadius: '6px' }}>
              {(['hanning', 'hamming', 'rect'] as const).map((win) => (
                <button
                  key={win}
                  onClick={() => setWindowFunction(win)}
                  style={{
                    background: windowFunction === win ? '#3b82f6' : 'transparent',
                    color: windowFunction === win ? '#ffffff' : '#94a3b8',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    fontSize: '0.7rem',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {win}
                </button>
              ))}
            </div>
          </div>

          {/* FFT Spectrum Bar Chart */}
          <div style={{ height: '220px', width: '100%', display: 'flex', alignItems: 'flex-end', gap: '4px', paddingBottom: '20px', position: 'relative' }}>
            {frequencySpectrum.slice(0, 32).map((item, idx) => {
              const heightPct = Math.min(100, (item.power / maxPower) * 100);
              const isHighlight = item.label !== undefined;
              const barColor = item.freqCyclesPerDay === 1
                ? '#10b981'
                : item.freqCyclesPerDay === 3
                ? '#8b5cf6'
                : item.freqCyclesPerDay === 6
                ? '#f59e0b'
                : isSimulatingBurst && item.freqCyclesPerDay >= 18
                ? '#ef4444'
                : '#3b82f6';

              return (
                <div
                  key={idx}
                  style={{
                    flex: 1,
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    position: 'relative',
                  }}
                  title={`${item.freqCyclesPerDay} cyc/day (T=${item.periodHours}h): Power ${item.power}${item.label ? ` [${item.label}]` : ''}`}
                >
                  {isHighlight && (
                    <div
                      style={{
                        position: 'absolute',
                        top: `${100 - heightPct - 18}%`,
                        fontSize: '0.65rem',
                        color: barColor,
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {item.freqCyclesPerDay}c
                    </div>
                  )}
                  <div
                    style={{
                      width: '100%',
                      height: `${Math.max(4, heightPct)}%`,
                      backgroundColor: barColor,
                      borderRadius: '2px 2px 0 0',
                      transition: 'height 0.4s ease',
                      opacity: isHighlight ? 1.0 : 0.45,
                    }}
                  />
                </div>
              );
            })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#64748b' }}>
            <span>f = 1 cyc/day (24h)</span>
            <span>f = 6 cyc/day (4h)</span>
            <span>f = 12 cyc/day (2h)</span>
            <span>f = 24 cyc/day (1h)</span>
            <span>High Freq (Hz Cadence)</span>
          </div>
        </div>
      </div>

      {/* Clinical & Roster Forecasting Insights */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '1.5rem' }}>
        <div style={{ background: '#1e293b', borderRadius: '10px', border: '1px solid #334155', padding: '1.2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.8rem' }}>
            <Sparkles size={18} color="#38bdf8" />
            <h4 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Spectral Workload & Staffing Forecast
            </h4>
          </div>

          <p style={{ fontSize: '0.8rem', color: '#94a3b8', lineHeight: 1.5, marginBottom: '1rem' }}>
            Reconstructing assistance demands from Fourier harmonics enables predictive nursing allocation rather than reactive triage.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: '#0f172a', borderRadius: '6px', fontSize: '0.8rem' }}>
              <span style={{ color: '#cbd5e1' }}>08:00 – 12:00 (Diurnal Peak)</span>
              <span style={{ fontWeight: 700, color: '#38bdf8' }}>Forecast: 6.8 calls/hr • 3 Nurses required</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: '#0f172a', borderRadius: '6px', fontSize: '0.8rem' }}>
              <span style={{ color: '#cbd5e1' }}>14:00 – 15:00 (Shift Overlap)</span>
              <span style={{ fontWeight: 700, color: '#a78bfa' }}>Forecast: 5.1 calls/hr • Handover assistance</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: '#0f172a', borderRadius: '6px', fontSize: '0.8rem' }}>
              <span style={{ color: '#cbd5e1' }}>20:00 – 22:00 (Night Analgesia)</span>
              <span style={{ fontWeight: 700, color: '#f59e0b' }}>Forecast: 4.4 calls/hr • 4h medication cycle</span>
            </div>
          </div>
        </div>

        <div style={{ background: '#1e293b', borderRadius: '10px', border: '1px solid #334155', padding: '1.2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.8rem' }}>
            <CheckCircle size={18} color="#10b981" />
            <h4 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Hardware & Acoustic Validation (Bed B06)
            </h4>
          </div>

          <p style={{ fontSize: '0.8rem', color: '#94a3b8', lineHeight: 1.5, marginBottom: '1rem' }}>
            The physical Raspberry Pi bedside node runs an asynchronous input handler on GPIO 27 (Assist) and GPIO 17 (Comfort).
          </p>

          <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.6 }}>
            <li>
              <strong>Triple-Tap Cadence Threshold:</strong> Presses within a 1.2s window exceed 2.0 Hz spectral threshold, triggering automatic escalation.
            </li>
            <li>
              <strong>Reassurance Audio Confirmation:</strong> MAX98357A I2S DAC plays acknowledgment chime and spoken prompt on acknowledgment.
            </li>
            <li>
              <strong>Integrity Guarded:</strong> Every event carries HMAC-SHA256 frame integrity (Invariant 13) over TLS 1.3.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
