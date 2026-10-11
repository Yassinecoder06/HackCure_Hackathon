// The parts of contracts/openapi.yaml (StreamMessage, WardSnapshot, Bed, Staff, Call) that the twin reads.
// Everything is read-only: this app never writes to the ward server except to log in.

export type Band = 'low' | 'low_medium' | 'medium' | 'high';
export type Role = 'nurse' | 'charge_nurse' | 'care_assistant' | 'doctor';

export interface ParamReading {
  value: number | string | boolean;
  ts: string;
  ageS: number;
  status: 'fresh' | 'stale' | 'invalid';
  sourceType: 'device' | 'manual';
}

export interface News2 {
  total: number;
  complete: boolean;
  band: Band;
  anySingleParam3: boolean;
  response?: string;
  components: { param: string; value?: unknown; points?: number; status: 'fresh' | 'stale' | 'missing' | 'invalid' }[];
  missing: string[];
  stale: string[];
  label: string;
  confidence: { value: number; basis: string };
  computedAt: string;
}

export interface Device {
  deviceId: string;
  deviceType: string;
  status: 'ok' | 'offline' | 'error' | 'low_battery';
  lastSeen: string;
}

export interface Bed {
  bed: string;
  room: string;
  admission?: { admissionId: string; patientRef: string; acuity: number; admittedAt: string } | null;
  news2?: News2 | null;
  news2Status: 'ok' | 'unavailable' | 'not_admitted';
  vitals: Record<string, ParamReading>;
  devices: Device[];
  priority?: { rank: number; of: number; reasons: string[] };
}

export interface Staff {
  staffId: string;
  displayName: string;
  role: Role;
  onShift: boolean;
  onWard?: boolean;
  assignedBeds: string[];
}

export type CallState = 'pressed' | 'sent' | 'not_sent' | 'acknowledged' | 'escalated' | 'resolved';

export interface Call {
  callId: string;
  bed: string;
  kind: 'assist' | 'comfort';
  state: CallState;
  escalationLevel: number;
  routedToRole: string;
  pressedAt: string;
  acknowledgedBy?: string;
  acknowledgedAt?: string;
}

export interface WardSnapshot {
  ward: string;
  asOf: string;
  clockMode: 'wall' | 'sim';
  beds: Bed[];
  staff: Staff[];
  calls: Call[];
  alerts: unknown[];
}

export type StreamMessage =
  | { type: 'snapshot'; data: WardSnapshot }
  | { type: 'bed'; data: Bed }
  | { type: 'call'; data: Call }
  | { type: 'staff'; data: Staff }
  | { type: 'alert' | 'assignment_suggestion' | 'clock' | 'metrics' | 'doctor_order'; data: unknown };

export type Point = [number, number, number]; // three.js axes: x, up, z

export interface Anchor {
  pos: Point;
  yaw: number;
}

export interface Layout {
  version: number;
  rooms: {
    id: string;
    side: 'north' | 'south';
    door: Anchor;
    beds: { id: string; bedside: Anchor; via: Point }[];
  }[];
  staff: { id: string; name: string; role: Role }[];
  home: Record<string, { kind: 'seat' | 'stand'; index: number }>;
  station: {
    pos: Point;
    seats: { pos: Point; lift: number; yaw: number }[];
    standing: Anchor[];
    exit: Point;
  };
  corridor: { walkY: number; hall: { southZ: number; westX: number; eastX: number } };
  tv: { pos: Point; facing: Point };
  outfits: Record<Role, { top: Point; bottom: Point; hat: Point }>;
  clips: string[];
}
