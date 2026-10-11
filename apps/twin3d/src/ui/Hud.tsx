import { useProgress } from '@react-three/drei';
import { BAND_COLOUR, monitorView } from '../logic/monitor';
import { callForBed, type WardState } from '../logic/wardStore';
import type { LinkStatus } from '../net/connection';
import type { CameraView, LabelPos, QualityLevel } from '../scene/WardScene';
import { S } from '../strings';
import type { Band } from '../types';

interface HudProps {
  state: WardState;
  status: LinkStatus;
  demo: boolean;
  selected: string | null;
  onSelect: (b: string | null) => void;
  view: CameraView;
  onView: (v: CameraView) => void;
  quality: QualityLevel;
  photo: boolean;
  onPhoto: (p: boolean) => void;
  labels: LabelPos[];
}

const BANDS: Band[] = ['high', 'medium', 'low_medium', 'low'];

export function Hud(p: HudProps) {
  const { active, progress } = useProgress();
  const link = { live: S.link.live, connecting: S.link.connecting, reconnecting: S.link.reconnecting, closed: S.link.closed }[p.status];
  if (p.photo) {
    return (
      <div className="hud photo-bar">
        <button onClick={() => savePng()}>{S.photoSave}</button>
        <button onClick={() => p.onPhoto(false)}>{S.bed.close}</button>
      </div>
    );
  }
  return (
    <div className="hud">
      {active && <div className="loading-bar">{S.loading} {Math.round(progress)}%</div>}
      {p.labels.map((l) => <BedLabel key={l.id} l={l} state={p.state} selected={p.selected === l.id} onSelect={p.onSelect} />)}
      <header>
        <h1>{S.title}</h1>
        <span className={`link ${p.status}`}>{p.demo ? 'DEMO' : link}</span>
        <p className="advisory">{S.advisory}</p>
        {p.demo && <p className="demo">{S.demoBanner}</p>}
      </header>

      <div className="legend" aria-label={S.legend}>
        <strong>{S.legend}</strong>
        {BANDS.map((b) => (
          <span key={b}><i style={{ background: BAND_COLOUR[b] }} />{S.band[b]}</span>
        ))}
        <span><i className="hatch" />{S.monitor.noSignal}</span>
        <span><i className="dash" />{S.monitor.partial}</span>
      </div>

      <nav className="controls">
        {(['overview', 'station'] as const).map((v) => (
          <button key={v} className={p.view === v ? 'on' : ''} onClick={() => p.onView(v)}>{S.cameras[v]}</button>
        ))}
        <button className={p.view === 'follow' ? 'on' : ''} disabled={!p.selected} onClick={() => p.onView('follow')}>{S.cameras.follow}</button>
        <button onClick={() => p.onPhoto(true)}>{S.photo}</button>
        <span className="q">{S.quality} {['low', 'medium', 'high', 'photo'][p.quality]}</span>
      </nav>

      {p.selected && <BedPanel bed={p.selected} state={p.state} onClose={() => p.onSelect(null)} />}
    </div>
  );
}

function savePng() {
  const canvas = document.getElementById('twin-canvas')?.querySelector('canvas') ?? document.querySelector('canvas');
  if (!canvas) return;
  const a = document.createElement('a');
  a.download = 'ward-twin.png';
  a.href = (canvas as HTMLCanvasElement).toDataURL('image/png');
  a.click();
}

function BedPanel({ bed, state, onClose }: { bed: string; state: WardState; onClose: () => void }) {
  const b = state.beds[bed];
  const v = monitorView(b);
  const call = callForBed(state, bed);
  return (
    <aside className="bedpanel">
      <button className="close" onClick={onClose} aria-label={S.bed.close}>×</button>
      <h2>{S.bed.heading} {bed}</h2>
      {b?.admission && <p>{S.bed.patient}: {b.admission.patientRef}</p>}
      {v.kind === 'score' && b?.news2 && (
        <>
          <p className="score" style={{ color: BAND_COLOUR[v.band] }}>
            {S.bed.score} {v.total} · {S.band[v.band]}
            {v.partial && <em> ({S.bed.partial})</em>}
          </p>
          <p>{b.news2.label}</p>
          <p>{S.bed.confidence}: {Math.round(b.news2.confidence.value * 100)}% — {b.news2.confidence.basis}</p>
          <p>{S.bed.why}:</p>
          <ul>
            {b.news2.components.map((c) => (
              <li key={c.param}>{c.param}: {c.status === 'fresh' ? `${String(c.value ?? '')} → ${c.points ?? 0} pt` : c.status}</li>
            ))}
          </ul>
          {v.missing.length > 0 && <p>{S.bed.missing}: {v.missing.join(', ')}</p>}
          {v.stale.length > 0 && <p>{S.bed.stale}: {v.stale.join(', ')}</p>}
        </>
      )}
      {v.kind === 'no_signal' && <p className="score muted">{S.monitor.noSignal}</p>}
      {v.kind === 'no_device' && <p className="score muted">{S.monitor.noDevice}</p>}
      {v.kind === 'unavailable' && <p className="score muted">{S.monitor.unavailable}</p>}
      {v.kind === 'vacant' && <p className="score muted">{S.monitor.vacant}</p>}
      {call && <p>{S.bed.call}: {S.calls[call.state]}{call.acknowledgedBy ? ` (${call.acknowledgedBy})` : ''}</p>}
      <p className="advisory">{S.bed.advisory}</p>
    </aside>
  );
}

function BedLabel({ l, state, selected, onSelect }: { l: LabelPos; state: WardState; selected: boolean; onSelect: (b: string | null) => void }) {
  if (!l.visible) return null;
  const v = monitorView(state.beds[l.id]);
  const colour = v.kind === 'score' ? BAND_COLOUR[v.band] : v.kind === 'vacant' ? '#4a5260' : '#8a94a6';
  const text =
    v.kind === 'score' ? `${l.id} · ${v.total}${v.partial ? '*' : ''}`
    : v.kind === 'vacant' ? l.id
    : `${l.id} · ${v.kind === 'no_signal' ? S.monitor.noSignal : v.kind === 'no_device' ? S.monitor.noDevice : '?'}`;
  return (
    <button className={`bed-label${selected ? ' sel' : ''}`} style={{ left: l.x, top: l.y, borderColor: colour, color: colour }} onClick={() => onSelect(selected ? null : l.id)}>
      {text}
    </button>
  );
}
