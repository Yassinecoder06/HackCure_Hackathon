import type { Bed, Call, Layout, News2, ParamReading, StreamMessage, WardSnapshot } from '../types';

// A synthetic stream for demos and screenshots, opened ONLY with ?demo=1 and always labelled DEMO DATA in
// the UI. It speaks the same message types as the ward server so every code path is exercised, and it
// includes the awkward cases on purpose: a stale device, a bed with no device, a partial score, a vacant bed.
// Nothing here is real patient data (safety invariant 7).

const PARAMS = ['resp_rate', 'spo2', 'sys_bp', 'pulse', 'temp_c'];

function bandOf(total: number): News2['band'] {
  return total >= 7 ? 'high' : total >= 5 ? 'medium' : total >= 1 ? 'low_medium' : 'low';
}

function reading(value: number, stale = false): ParamReading {
  return { value, ts: new Date().toISOString(), ageS: stale ? 200 : 4, status: stale ? 'stale' : 'fresh', sourceType: 'device' };
}

function makeBed(id: string, room: string, total: number, opts: { stale?: boolean; noDevice?: boolean; partial?: boolean; vacant?: boolean }): Bed {
  if (opts.vacant) return { bed: id, room, admission: null, news2: null, news2Status: 'not_admitted', vitals: {}, devices: [] };
  const vitals: Record<string, ParamReading> = {};
  if (!opts.noDevice) PARAMS.forEach((p) => (vitals[p] = reading(p === 'spo2' ? 96 : 70, opts.stale)));
  const missing = opts.partial ? ['consciousness'] : [];
  const news2: News2 | null = opts.noDevice
    ? null
    : {
        total,
        complete: !opts.partial,
        band: bandOf(total),
        anySingleParam3: total >= 7,
        components: PARAMS.map((p) => ({ param: p, points: 1, status: opts.stale ? 'stale' : 'fresh' as const })),
        missing,
        stale: opts.stale ? PARAMS : [],
        label: opts.partial ? 'Partial score: consciousness missing' : 'Complete score',
        confidence: { value: opts.partial ? 0.78 : 0.97, basis: opts.partial ? '5 of 6 parameters fresh; consciousness missing' : 'all parameters fresh' },
        computedAt: new Date().toISOString(),
      };
  return {
    bed: id,
    room,
    admission: { admissionId: `adm_${id}`, patientRef: `Patient ${id.slice(1)}`, acuity: 2, admittedAt: new Date(Date.now() - 36e5).toISOString() },
    news2,
    news2Status: 'ok',
    vitals,
    devices: opts.noDevice ? [] : [{ deviceId: `dev_${id}`, deviceType: 'bedside_monitor', status: opts.stale ? 'offline' : 'ok', lastSeen: new Date().toISOString() }],
  };
}

export function startDemo(layout: Layout, onMessage: (m: StreamMessage) => void): () => void {
  const scores: Record<string, number> = { B01: 0, B02: 2, B03: 5, B04: 8, B05: 1, B06: 3, B07: 0, B08: 6 };
  const mk = (id: string, room: string): Bed => {
    switch (id) {
      case 'B09': return makeBed(id, room, 2, { stale: true });
      case 'B10': return makeBed(id, room, 4, { partial: true });
      case 'B11': return makeBed(id, room, 0, { vacant: true });
      case 'B12': return makeBed(id, room, 0, { noDevice: true });
      default: return makeBed(id, room, scores[id] ?? 0, {});
    }
  };
  const beds: Bed[] = layout.rooms.flatMap((r) => r.beds.map((b) => mk(b.id, r.id)));
  const snapshot: WardSnapshot = {
    ward: 'W1',
    asOf: new Date().toISOString(),
    clockMode: 'wall',
    beds,
    staff: layout.staff.map((s) => ({ staffId: s.id, displayName: s.name, role: s.role, onShift: true, onWard: true, assignedBeds: [] })),
    calls: [],
    alerts: [],
  };
  onMessage({ type: 'snapshot', data: snapshot });

  let n = 0;
  const live = beds.filter((b) => b.admission && b.news2 && b.news2Status === 'ok' && b.devices[0]?.status === 'ok');
  const tick = window.setInterval(() => {
    n += 1;
    // a score drifts every few seconds
    const b = live[n % live.length];
    const total = Math.max(0, Math.min(9, (b.news2?.total ?? 0) + (n % 3 === 0 ? 1 : -1)));
    const next = makeBed(b.bed, b.room, total, {});
    b.news2 = next.news2;
    onMessage({ type: 'bed', data: { ...next } });
    // a call every ~16 s: pressed, acknowledged by a nurse 4 s later, resolved 12 s after that
    if (n % 5 === 0) {
      const target = live[(n * 7) % live.length].bed;
      const nurse = layout.staff.filter((s) => s.role === 'nurse')[n % 3].id;
      const call: Call = { callId: `c${n}`, bed: target, kind: 'assist', state: 'pressed', escalationLevel: 0, routedToRole: 'nurse', pressedAt: new Date().toISOString() };
      onMessage({ type: 'call', data: call });
      window.setTimeout(() => onMessage({ type: 'call', data: { ...call, state: 'acknowledged', acknowledgedBy: nurse, acknowledgedAt: new Date().toISOString() } }), 4000);
      window.setTimeout(() => onMessage({ type: 'call', data: { ...call, state: 'resolved' } }), 22000);
    }
  }, 3000);
  return () => window.clearInterval(tick);
}
