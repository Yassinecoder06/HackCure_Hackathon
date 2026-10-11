import { Suspense, useEffect, useReducer, useState } from 'react';
import { emptyState, reduce } from './logic/wardStore';
import { connectStream, login, type LinkStatus, type Session } from './net/connection';
import { startDemo } from './net/demoSource';
import { WardScene, type CameraView, type LabelPos, type QualityLevel } from './scene/WardScene';
import { Hud } from './ui/Hud';
import { S } from './strings';
import type { Layout } from './types';

const DEMO = new URLSearchParams(location.search).has('demo');

function LoginPanel({ onSession, onDemo }: { onSession: (s: Session) => void; onDemo: () => void }) {
  const [staffId, setStaffId] = useState('CN1');
  const [pin, setPin] = useState('');
  const [error, setError] = useState(false);
  return (
    <form
      className="login"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          onSession(await login(staffId, pin));
        } catch {
          setError(true);
        }
      }}
    >
      <h1>{S.title}</h1>
      <h2>{S.login.heading}</h2>
      <label>{S.login.staffId}<input value={staffId} onChange={(e) => setStaffId(e.target.value)} autoComplete="username" /></label>
      <label>{S.login.pin}<input type="password" value={pin} onChange={(e) => setPin(e.target.value)} autoComplete="current-password" /></label>
      {error && <p className="error">{S.login.failed}</p>}
      <button type="submit">{S.login.submit}</button>
      <button type="button" className="secondary" onClick={onDemo}>{S.login.demo}</button>
      <p className="advisory">{S.advisory}</p>
    </form>
  );
}

export function App() {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [state, dispatch] = useReducer(reduce, emptyState);
  const [session, setSession] = useState<Session | null>(null);
  const [demo, setDemo] = useState(DEMO);
  const [status, setStatus] = useState<LinkStatus>('connecting');
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<CameraView>('overview');
  const [viewNonce, setViewNonce] = useState(0);
  const [quality, setQuality] = useState<QualityLevel>(2);
  const [photo, setPhoto] = useState(false);
  const [labels, setLabels] = useState<LabelPos[]>([]);

  useEffect(() => {
    fetch('/models/ward-layout.json').then((r) => r.json()).then(setLayout);
  }, []);

  useEffect(() => {
    if (!layout) return undefined;
    if (demo) {
      setStatus('live');
      return startDemo(layout, dispatch);
    }
    if (!session) return undefined;
    return connectStream(session.token, dispatch, setStatus, () => setSession(null));
  }, [layout, demo, session]);

  if (!layout) return <div className="center">{S.loading}</div>;
  if (!session && !demo) return <LoginPanel onSession={setSession} onDemo={() => setDemo(true)} />;

  const pick = (bed: string | null) => {
    setSelected(bed);
    if (bed) {
      setView('follow');
      setViewNonce((n) => n + 1);
    } else if (view === 'follow') setView('overview');
  };

  return (
    <>
      <Suspense fallback={<div className="center">{S.loading}</div>}>
        <WardScene
          layout={layout} state={state} selected={selected} onSelect={pick}
          view={view} viewNonce={viewNonce} quality={quality} onQuality={setQuality} photo={photo} onProject={setLabels}
        />
      </Suspense>
      <Hud
        state={state} status={status} demo={demo} selected={selected} onSelect={pick}
        view={view} onView={(v) => { setView(v); setViewNonce((n) => n + 1); }}
        quality={quality} photo={photo} onPhoto={setPhoto} labels={photo ? [] : labels}
      />
    </>
  );
}
