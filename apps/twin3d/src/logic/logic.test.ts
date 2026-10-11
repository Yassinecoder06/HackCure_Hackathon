import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { monitorView, glowStrength } from './monitor';
import { callForBed, emptyState, reduce, responseTargets } from './wardStore';
import { along, routeToBed } from './paths';
import type { Bed, Call, Layout, News2, ParamReading } from '../types';

const reading = (status: ParamReading['status']): ParamReading => ({ value: 96, ts: 't', ageS: 5, status, sourceType: 'device' });
const news = (over: Partial<News2> = {}): News2 => ({
  total: 5, complete: true, band: 'medium', anySingleParam3: false, components: [], missing: [], stale: [],
  label: '', confidence: { value: 1, basis: '' }, computedAt: '2026-10-11T10:00:00Z', ...over,
});
const bed = (over: Partial<Bed> = {}): Bed => ({
  bed: 'B01', room: 'R1', admission: { admissionId: 'a', patientRef: 'P', acuity: 2, admittedAt: 't' },
  news2: news(), news2Status: 'ok', vitals: { spo2: reading('fresh') },
  devices: [{ deviceId: 'd', deviceType: 'bedside_monitor', status: 'ok', lastSeen: 't' }], ...over,
});

describe('monitor view (invariant 5: missing or stale is never shown as normal)', () => {
  it('shows a score with its band', () => {
    expect(monitorView(bed())).toMatchObject({ kind: 'score', total: 5, band: 'medium', partial: false });
  });
  it('labels a score computed from incomplete input as partial', () => {
    expect(monitorView(bed({ news2: news({ complete: false, missing: ['consciousness'] }) }))).toMatchObject({ kind: 'score', partial: true });
    expect(monitorView(bed({ news2: news({ stale: ['pulse'] }) }))).toMatchObject({ kind: 'score', partial: true });
  });
  it('shows NO SIGNAL when a device is present but nothing is fresh', () => {
    expect(monitorView(bed({ vitals: { spo2: reading('stale') } }))).toEqual({ kind: 'no_signal' });
    expect(monitorView(bed({ vitals: {} }))).toEqual({ kind: 'no_signal' });
  });
  it('never turns a missing reading into a calm score', () => {
    const v = monitorView(bed({ vitals: { spo2: reading('stale') }, news2: news({ total: 0, band: 'low' }) }));
    expect(v.kind).toBe('no_signal');
    expect(glowStrength(v)).toBeLessThan(1);
  });
  it('shows no device for a bed without one and no fresh data', () => {
    expect(monitorView(bed({ devices: [], vitals: {}, news2: null }))).toEqual({ kind: 'no_device' });
  });
  it('says so when the inference layer is unavailable', () => {
    expect(monitorView(bed({ news2Status: 'unavailable' }))).toEqual({ kind: 'unavailable' });
  });
  it('is dark for a vacant bed', () => {
    expect(monitorView(bed({ admission: null, news2Status: 'not_admitted' }))).toEqual({ kind: 'vacant' });
    expect(monitorView(undefined)).toEqual({ kind: 'vacant' });
    expect(glowStrength({ kind: 'vacant' })).toBe(0);
  });
});

describe('ward store (invariant 6: replaying a message changes nothing)', () => {
  const snap = { type: 'snapshot' as const, data: { ward: 'W1', asOf: 't', clockMode: 'wall' as const, beds: [bed()], staff: [], calls: [], alerts: [] } };
  it('is idempotent', () => {
    const once = reduce(reduce(emptyState, snap), { type: 'bed', data: bed({ news2: news({ total: 7 }) }) });
    const twice = reduce(once, { type: 'bed', data: bed({ news2: news({ total: 7 }) }) });
    expect(twice).toEqual(once);
  });
  it('ignores an older bed message', () => {
    const s = reduce(emptyState, snap);
    const old = bed({ news2: news({ total: 9, computedAt: '2026-10-11T09:00:00Z' }) });
    expect(reduce(s, { type: 'bed', data: old }).beds.B01.news2?.total).toBe(5);
  });
  const call = (state: Call['state'], extra: Partial<Call> = {}): Call => ({
    callId: 'c1', bed: 'B01', kind: 'assist', state, escalationLevel: 0, routedToRole: 'nurse', pressedAt: '2026-10-11T10:00:00Z', ...extra,
  });
  it('tracks a call from pressed to resolved and who answers it', () => {
    let s = reduce(emptyState, snap);
    s = reduce(s, { type: 'call', data: call('pressed') });
    expect(callForBed(s, 'B01')?.state).toBe('pressed');
    s = reduce(s, { type: 'call', data: call('acknowledged', { acknowledgedBy: 'N1' }) });
    expect(responseTargets(s)).toEqual({ N1: 'B01' });
    s = reduce(s, { type: 'call', data: call('resolved') });
    expect(callForBed(s, 'B01')).toBeUndefined();
    expect(responseTargets(s)).toEqual({});
  });
});

describe('walking routes', () => {
  const layout = {
    rooms: [{ id: 'R1', side: 'north', door: { pos: [-12, 0, -1.2], yaw: 0 }, beds: [{ id: 'B01', bedside: { pos: [-9.7, 0, -7.6], yaw: 0 }, via: [-12, 0, -7.6] }] }],
    corridor: { walkY: 0.3, hall: { southZ: 4, westX: -3.2, eastX: 3.2 } },
  } as unknown as Layout;
  it('leaves the bay on the staff side, uses the corridor and ends at the bedside', () => {
    const r = routeToBed(layout, [-1.4, 0, 3.7], 'B01')!;
    expect(r.points[1]).toEqual([-1.4, 4]);
    expect(r.points.at(-1)).toEqual([-9.7, -7.6]);
    expect(r.points.some((p) => p[1] === -0.3)).toBe(true);
    expect(along(r, r.length + 1).done).toBe(true);
    expect(along(r, 0).x).toBeCloseTo(-1.4);
  });
  it('knows nothing about a bed that is not in the layout', () => {
    expect(routeToBed(layout, [0, 0, 0], 'B99')).toBeUndefined();
  });
});

// Safety invariant 1 (advisory only) and ADR 0012 (display only): the twin reads, it never writes. The only
// request it may send to the ward server is the login; the stream is receive-only.
describe('display only', () => {
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((f) => {
      const p = join(dir, f);
      return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx)$/.test(f) && !f.endsWith('.test.ts') ? [p] : [];
    });
  const src = files(join(__dirname, '..')).map((p) => ({ p, text: readFileSync(p, 'utf8') }));

  it('sends nothing to the server except the login request', () => {
    const writes = src.flatMap(({ p, text }) =>
      [...text.matchAll(/method:\s*['"](POST|PUT|PATCH|DELETE)['"]/g)].map(() => p.split('\\').join('/')),
    );
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatch(/net\/connection\.ts$/);
    expect(src.some(({ text }) => /\.send\(/.test(text))).toBe(false); // the WebSocket is receive-only
  });
  it('never touches storage, so no patient data is kept in the browser', () => {
    expect(src.some(({ text }) => /localStorage|sessionStorage|indexedDB/.test(text))).toBe(false);
  });
});
