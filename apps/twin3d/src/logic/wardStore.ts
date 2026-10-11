import type { Bed, Call, Staff, StreamMessage, WardSnapshot } from '../types';

// The twin's whole state is the latest ward snapshot plus incremental messages. Applying the same message
// twice changes nothing (safety invariant 6: replays are idempotent), and an older bed message never
// overwrites a newer one.
export interface WardState {
  ready: boolean;
  asOf: string | null;
  beds: Record<string, Bed>;
  staff: Record<string, Staff>;
  calls: Record<string, Call>;
}

export const emptyState: WardState = { ready: false, asOf: null, beds: {}, staff: {}, calls: {} };

const byKey = <T,>(items: T[], key: (t: T) => string): Record<string, T> =>
  Object.fromEntries(items.map((i) => [key(i), i]));

function newer(old: Bed | undefined, next: Bed): boolean {
  const a = old?.news2?.computedAt;
  const b = next.news2?.computedAt;
  return !(a && b && b < a);
}

export function reduce(state: WardState, msg: StreamMessage): WardState {
  switch (msg.type) {
    case 'snapshot': {
      const s = msg.data as WardSnapshot;
      return {
        ready: true,
        asOf: s.asOf,
        beds: byKey(s.beds ?? [], (b) => b.bed),
        staff: byKey(s.staff ?? [], (p) => p.staffId),
        calls: byKey((s.calls ?? []).filter((c) => c.state !== 'resolved'), (c) => c.callId),
      };
    }
    case 'bed': {
      const b = msg.data as Bed;
      if (!newer(state.beds[b.bed], b)) return state;
      return { ...state, beds: { ...state.beds, [b.bed]: b } };
    }
    case 'staff': {
      const p = msg.data as Staff;
      return { ...state, staff: { ...state.staff, [p.staffId]: p } };
    }
    case 'call': {
      const c = msg.data as Call;
      const calls = { ...state.calls };
      if (c.state === 'resolved') delete calls[c.callId];
      else calls[c.callId] = c;
      return { ...state, calls };
    }
    default:
      return state;
  }
}

// The call that should light a bed (the most urgent open one).
const URGENCY: Record<string, number> = { escalated: 5, not_sent: 4, pressed: 3, sent: 3, acknowledged: 1, resolved: 0 };

export function callForBed(state: WardState, bed: string): Call | undefined {
  return Object.values(state.calls)
    .filter((c) => c.bed === bed && c.state !== 'resolved')
    .sort((a, b) => (URGENCY[b.state] ?? 0) - (URGENCY[a.state] ?? 0))[0];
}

// Which bed each staff member is answering: the open call they acknowledged.
export function responseTargets(state: WardState): Record<string, string> {
  const out: Record<string, string> = {};
  for (const c of Object.values(state.calls).sort((a, b) => a.pressedAt.localeCompare(b.pressedAt))) {
    if (c.acknowledgedBy && (c.state === 'acknowledged' || c.state === 'escalated')) out[c.acknowledgedBy] = c.bed;
  }
  return out;
}
