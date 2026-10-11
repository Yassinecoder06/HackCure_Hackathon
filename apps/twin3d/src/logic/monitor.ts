import type { Band, Bed } from '../types';

// What a bed's monitor in the 3D ward shows. Safety invariant 5: missing or stale data is shown as missing
// or stale, never as a normal value, and a score computed from incomplete input is labelled partial.
export type MonitorView =
  | { kind: 'vacant' }
  | { kind: 'no_device' }
  | { kind: 'no_signal' }
  | { kind: 'unavailable' }
  | {
      kind: 'score';
      total: number;
      band: Band;
      partial: boolean;
      stale: string[];
      missing: string[];
      singleParam3: boolean;
    };

export function monitorView(bed: Bed | undefined): MonitorView {
  if (!bed || !bed.admission || bed.news2Status === 'not_admitted') return { kind: 'vacant' };
  if (bed.news2Status === 'unavailable') return { kind: 'unavailable' };

  const readings = Object.values(bed.vitals ?? {});
  const fresh = readings.filter((r) => r.status === 'fresh').length;
  const hasDevice = (bed.devices ?? []).length > 0;

  // Nothing fresh at all: a device that stopped talking is "no signal"; a bed with no device and no
  // fresh manual reading simply has no device data.
  if (fresh === 0 || !bed.news2) return hasDevice ? { kind: 'no_signal' } : { kind: 'no_device' };

  const n = bed.news2;
  return {
    kind: 'score',
    total: n.total,
    band: n.band,
    partial: !n.complete || n.stale.length > 0 || n.missing.length > 0,
    stale: n.stale,
    missing: n.missing,
    singleParam3: n.anySingleParam3,
  };
}

// Glow colours per band (display only). Chosen to stay distinguishable without relying on red/green alone:
// each band also has a text label on the screen.
export const BAND_COLOUR: Record<Band, string> = {
  low: '#3ddc84',
  low_medium: '#ffd23f',
  medium: '#ff9f1c',
  high: '#ff3b3b',
};

export function glowColour(view: MonitorView): string {
  switch (view.kind) {
    case 'score':
      return BAND_COLOUR[view.band];
    case 'no_signal':
    case 'unavailable':
      return '#8a94a6';
    default:
      return '#000000';
  }
}

// How strongly the screen emits light (feeds bloom). A vacant monitor is dark, never "calm green".
export function glowStrength(view: MonitorView): number {
  switch (view.kind) {
    case 'score':
      return view.band === 'high' ? 2.2 : view.band === 'medium' ? 1.8 : 1.4;
    case 'no_signal':
    case 'unavailable':
      return 0.6;
    case 'no_device':
      return 0.35;
    default:
      return 0;
  }
}
