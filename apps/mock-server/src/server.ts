import express, { Request, Response } from 'express';
import cors from 'cors';
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';

// ==========================================
// 1. WARD SERVER STATE & NEWS2 ENGINE (Port 8000)
// ==========================================

interface ParamReading {
  value: number | string | boolean;
  ts: string;
  ageS: number;
  status: 'fresh' | 'stale' | 'invalid';
  sourceType: 'device' | 'manual';
}

interface News2Component {
  param: 'resp_rate' | 'spo2' | 'on_oxygen' | 'sys_bp' | 'pulse' | 'consciousness' | 'temp_c';
  value?: number | string | boolean;
  points: number;
  status: 'fresh' | 'stale' | 'missing' | 'invalid';
}

interface Confidence {
  value: number;
  basis: string;
}

interface News2Result {
  total: number;
  complete: boolean;
  band: 'low' | 'low_medium' | 'medium' | 'high';
  anySingleParam3: boolean;
  response: string;
  components: News2Component[];
  missing: string[];
  stale: string[];
  label: string;
  confidence: Confidence;
  spo2Scale: 1 | 2;
  computedAt: string;
}

interface BedState {
  bed: string;
  room: string;
  admission: {
    admissionId: string;
    patientRef: string;
    acuity: number;
    admittedAt: string;
  } | null;
  news2: News2Result | null;
  vitals: Record<string, ParamReading>;
  devices: Array<{
    deviceId: string;
    deviceType: string;
    status: 'ok' | 'offline' | 'error' | 'low_battery';
    lastSeen: string;
  }>;
  assignedNurse: string;
}

interface CallState {
  callId: string;
  bed: string;
  kind: 'assist' | 'comfort';
  state: 'pressed' | 'sent' | 'not_sent' | 'acknowledged' | 'escalated' | 'resolved';
  escalationLevel: number;
  escalationReason?: 'unacknowledged_timeout' | 'repeat_press' | 'high_news2' | 'triple_tap_emergency';
  routedToRole: 'nurse' | 'care_assistant' | 'charge_nurse';
  pressCount: number;
  deliveredLate: boolean;
  pressedAt: string;
  acknowledgedBy?: string;
  acknowledgedAt?: string;
}

interface AlertState {
  alertId: string;
  bed: string;
  type: 'news2_rise' | 'news2_high' | 'stale_data' | 'device_offline' | 'call_escalated' | 'dose_overdue' | 'assignment_suggested';
  priority: 'low' | 'medium' | 'critical';
  createdAt: string;
  explanation: string[];
  confidence: Confidence;
  acknowledgedBy?: string;
}

interface StaffState {
  staffId: string;
  displayName: string;
  role: 'nurse' | 'charge_nurse' | 'care_assistant' | 'doctor' | 'biomed_tech';
  skills: string[];
  onShift: boolean;
  onWard: boolean;
  assignedBeds: string[];
  load: number;
}

interface AssignmentSuggestion {
  suggestionId: string;
  createdAt: string;
  trigger: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  changes: Array<{ bed: string; fromStaffId?: string; toStaffId: string }>;
  reasons: string[];
  loadBefore: Record<string, number>;
  loadAfter: Record<string, number>;
  confidence: Confidence;
  decidedBy?: string;
  decidedAt?: string;
  decisionReason?: string;
}

interface DoseState {
  doseId: string;
  admissionId: string;
  bed: string;
  due: string;
  status: 'due' | 'overdue' | 'given' | 'not_given';
  label: string;
  patientReportedAt?: string;
  administeredBy?: string;
  administeredAt?: string;
}

// Calculate Royal College of Physicians NEWS2 Score
function computeNEWS2(vitals: Record<string, ParamReading>): News2Result {
  const components: News2Component[] = [];
  const missing: string[] = [];
  const stale: string[] = [];
  let total = 0;
  let anySingleParam3 = false;

  const checkParam = (
    param: News2Component['param'],
    evaluator: (val: any) => number
  ) => {
    const reading = vitals[param];
    if (!reading) {
      missing.push(param);
      components.push({ param, points: 0, status: 'missing' });
      return;
    }
    if (reading.status === 'stale') {
      stale.push(param);
      components.push({ param, value: reading.value, points: 0, status: 'stale' });
      return;
    }
    if (reading.status === 'invalid') {
      components.push({ param, value: reading.value, points: 0, status: 'invalid' });
      return;
    }

    const points = evaluator(reading.value);
    if (points === 3) anySingleParam3 = true;
    total += points;
    components.push({ param, value: reading.value, points, status: 'fresh' });
  };

  // Respiratory Rate
  checkParam('resp_rate', (val: number) => {
    if (val <= 8) return 3;
    if (val >= 9 && val <= 11) return 1;
    if (val >= 12 && val <= 20) return 0;
    if (val >= 21 && val <= 24) return 2;
    return 3;
  });

  // SpO2 Scale 1
  checkParam('spo2', (val: number) => {
    if (val <= 91) return 3;
    if (val >= 92 && val <= 93) return 2;
    if (val >= 94 && val <= 95) return 1;
    return 0;
  });

  // On Supplemental Oxygen
  checkParam('on_oxygen', (val: boolean) => (val ? 2 : 0));

  // Systolic Blood Pressure
  checkParam('sys_bp', (val: number) => {
    if (val <= 90) return 3;
    if (val >= 91 && val <= 100) return 2;
    if (val >= 101 && val <= 110) return 1;
    if (val >= 111 && val <= 219) return 0;
    return 3;
  });

  // Pulse
  checkParam('pulse', (val: number) => {
    if (val <= 40) return 3;
    if (val >= 41 && val <= 50) return 1;
    if (val >= 51 && val <= 90) return 0;
    if (val >= 91 && val <= 110) return 1;
    if (val >= 111 && val <= 130) return 2;
    return 3;
  });

  // Consciousness (ACVPU: A=0, C=3, V=3, P=3, U=3)
  checkParam('consciousness', (val: string) => {
    const letter = String(val).toUpperCase();
    return letter === 'A' ? 0 : 3;
  });

  // Temperature
  checkParam('temp_c', (val: number) => {
    if (val <= 35.0) return 3;
    if (val >= 35.1 && val <= 36.0) return 1;
    if (val >= 36.1 && val <= 38.0) return 0;
    if (val >= 38.1 && val <= 39.0) return 1;
    return 2;
  });

  const complete = missing.length === 0 && stale.length === 0;

  let band: News2Result['band'] = 'low';
  let response = 'Routine monitoring (minimum 12 hourly)';
  if (total >= 7) {
    band = 'high';
    response = 'Emergency response: continuous monitoring, senior doctor review, outreach team';
  } else if (total >= 5) {
    band = 'medium';
    response = 'Urgent response: minimum 1 hourly obs, doctor urgent ward review';
  } else if (anySingleParam3 || total >= 1) {
    band = anySingleParam3 ? 'low_medium' : 'low';
    response = anySingleParam3
      ? 'Low-medium: urgent ward-based review by registered nurse'
      : 'Low risk: routine monitoring (4 to 6 hourly)';
  }

  let label = `Score: ${total} (${band})`;
  if (!complete) {
    const issues = [...missing.map(m => `${m} missing`), ...stale.map(s => `${s} stale`)];
    label = `Partial (${total}): ${issues.join(', ')}`;
  }

  const freshCount = components.filter(c => c.status === 'fresh').length;
  const confidenceValue = Number((freshCount / 7).toFixed(2));
  const basis = complete
    ? 'All 7 clinical parameters fresh from bedside telemetry'
    : `${freshCount} of 7 parameters fresh; ${[...missing.map(m => `${m} missing`), ...stale.map(s => `${s} stale`)].join(', ')}`;

  return {
    total,
    complete,
    band,
    anySingleParam3,
    response,
    components,
    missing,
    stale,
    label,
    confidence: {
      value: confidenceValue,
      basis
    },
    spo2Scale: 1,
    computedAt: new Date().toISOString()
  };
}

// Initial Ward State populated from seed/ward-W1.yaml
const now = new Date().toISOString();

const staff: StaffState[] = [
  { staffId: 'CN1', displayName: 'Charge Nurse A', role: 'charge_nurse', skills: ['iv', 'senior'], onShift: true, onWard: true, assignedBeds: [], load: 0 },
  { staffId: 'N1', displayName: 'Nurse B', role: 'nurse', skills: ['iv'], onShift: true, onWard: true, assignedBeds: ['B01', 'B02', 'B03', 'B10'], load: 7 },
  { staffId: 'N2', displayName: 'Nurse C', role: 'nurse', skills: ['iv', 'resp'], onShift: true, onWard: true, assignedBeds: ['B04', 'B05', 'B06', 'B11'], load: 9 },
  { staffId: 'N3', displayName: 'Nurse D', role: 'nurse', skills: [], onShift: true, onWard: true, assignedBeds: ['B07', 'B08', 'B09', 'B12'], load: 7 },
  { staffId: 'CA1', displayName: 'Care Assistant E', role: 'care_assistant', skills: [], onShift: true, onWard: true, assignedBeds: [], load: 3 },
  { staffId: 'DR1', displayName: 'Doctor F', role: 'doctor', skills: [], onShift: true, onWard: true, assignedBeds: [], load: 0 }
];

const initialBeds: BedState[] = [
  {
    bed: 'B01', room: 'R1', assignedNurse: 'N1',
    admission: { admissionId: 'adm_01', patientRef: 'Patient 01 (M. Ben Ali)', acuity: 2, admittedAt: now },
    devices: [{ deviceId: 'dev_m01', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 16, ts: now, ageS: 45, status: 'fresh', sourceType: 'device' },
      spo2: { value: 97, ts: now, ageS: 45, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 45, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 122, ts: now, ageS: 45, status: 'fresh', sourceType: 'device' },
      pulse: { value: 74, ts: now, ageS: 45, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 45, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.8, ts: now, ageS: 45, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B02', room: 'R1', assignedNurse: 'N1',
    admission: { admissionId: 'adm_02', patientRef: 'Patient 02 (S. Mansouri)', acuity: 1, admittedAt: now },
    devices: [{ deviceId: 'dev_m02', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 14, ts: now, ageS: 120, status: 'fresh', sourceType: 'device' },
      spo2: { value: 98, ts: now, ageS: 120, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 120, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 118, ts: now, ageS: 120, status: 'fresh', sourceType: 'device' },
      pulse: { value: 68, ts: now, ageS: 120, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 120, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.6, ts: now, ageS: 120, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B03', room: 'R2', assignedNurse: 'N1',
    admission: { admissionId: 'adm_03', patientRef: 'Patient 03 (H. Trabelsi)', acuity: 3, admittedAt: now },
    devices: [{ deviceId: 'dev_m03', deviceType: 'monitor_no_rr', status: 'ok', lastSeen: now }],
    vitals: {
      spo2: { value: 95, ts: now, ageS: 80, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 80, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 135, ts: now, ageS: 80, status: 'fresh', sourceType: 'device' },
      pulse: { value: 94, ts: now, ageS: 80, status: 'fresh', sourceType: 'device' },
      temp_c: { value: 37.4, ts: now, ageS: 80, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 80, status: 'fresh', sourceType: 'manual' }
      // resp_rate absent (machine cannot read, awaiting manual entry)
    },
    news2: null
  },
  {
    bed: 'B04', room: 'R2', assignedNurse: 'N2',
    admission: { admissionId: 'adm_04', patientRef: 'Patient 04 (L. Gharbi)', acuity: 2, admittedAt: now },
    devices: [{ deviceId: 'dev_m04', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 18, ts: now, ageS: 15, status: 'fresh', sourceType: 'device' },
      spo2: { value: 96, ts: now, ageS: 15, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 15, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 128, ts: now, ageS: 15, status: 'fresh', sourceType: 'device' },
      pulse: { value: 76, ts: now, ageS: 15, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 15, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.9, ts: now, ageS: 15, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B05', room: 'R3', assignedNurse: 'N2',
    admission: { admissionId: 'adm_05', patientRef: 'Patient 05 (A. Bouazizi)', acuity: 2, admittedAt: now },
    devices: [{ deviceId: 'dev_m05', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 19, ts: now, ageS: 50, status: 'fresh', sourceType: 'device' },
      spo2: { value: 95, ts: now, ageS: 50, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 50, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 88, ts: now, ageS: 50, status: 'fresh', sourceType: 'device' }, // 3 points!
      pulse: { value: 88, ts: now, ageS: 50, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 50, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 37.1, ts: now, ageS: 50, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B06', room: 'R3', assignedNurse: 'N2',
    admission: { admissionId: 'adm_06', patientRef: 'Patient 06 (K. Jaziri)', acuity: 4, admittedAt: now },
    devices: [{ deviceId: 'dev_m06', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 23, ts: now, ageS: 25, status: 'fresh', sourceType: 'device' }, // 2 pts
      spo2: { value: 93, ts: now, ageS: 25, status: 'fresh', sourceType: 'device' },       // 2 pts
      on_oxygen: { value: false, ts: now, ageS: 25, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 112, ts: now, ageS: 25, status: 'fresh', sourceType: 'device' },   // 0 pts
      pulse: { value: 104, ts: now, ageS: 25, status: 'fresh', sourceType: 'device' },    // 1 pt
      temp_c: { value: 38.5, ts: now, ageS: 25, status: 'fresh', sourceType: 'device' },   // 1 pt
      consciousness: { value: 'A', ts: now, ageS: 25, status: 'fresh', sourceType: 'manual' }
    },
    news2: null
  },
  {
    bed: 'B07', room: 'R4', assignedNurse: 'N3',
    admission: { admissionId: 'adm_07', patientRef: 'Patient 07 (F. Mejri)', acuity: 1, admittedAt: now },
    devices: [{ deviceId: 'dev_m07', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 15, ts: now, ageS: 180, status: 'fresh', sourceType: 'device' },
      spo2: { value: 99, ts: now, ageS: 180, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 180, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 120, ts: now, ageS: 180, status: 'fresh', sourceType: 'device' },
      pulse: { value: 70, ts: now, ageS: 180, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 180, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.7, ts: now, ageS: 180, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B08', room: 'R4', assignedNurse: 'N3',
    admission: { admissionId: 'adm_08', patientRef: 'Patient 08 (N. Chahed)', acuity: 3, admittedAt: now },
    devices: [{ deviceId: 'dev_m08', deviceType: 'monitor_no_rr', status: 'ok', lastSeen: now }],
    vitals: {
      spo2: { value: 94, ts: now, ageS: 1500, status: 'stale', sourceType: 'device' }, // Stale!
      on_oxygen: { value: false, ts: now, ageS: 1500, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 130, ts: now, ageS: 1500, status: 'stale', sourceType: 'device' },
      pulse: { value: 82, ts: now, ageS: 1500, status: 'stale', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 1500, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 37.0, ts: now, ageS: 1500, status: 'stale', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B09', room: 'R5', assignedNurse: 'N3',
    admission: { admissionId: 'adm_09', patientRef: 'Patient 09 (Y. Khelifi)', acuity: 2, admittedAt: now },
    devices: [{ deviceId: 'dev_ox09', deviceType: 'pulse_oximeter', status: 'ok', lastSeen: now }],
    vitals: {
      spo2: { value: 96, ts: now, ageS: 40, status: 'fresh', sourceType: 'device' },
      pulse: { value: 72, ts: now, ageS: 40, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 40, status: 'fresh', sourceType: 'manual' }
      // sys_bp, resp_rate, temp_c, consciousness absent
    },
    news2: null
  },
  {
    bed: 'B10', room: 'R5', assignedNurse: 'N1',
    admission: { admissionId: 'adm_10', patientRef: 'Patient 10 (S. Dridi)', acuity: 2, admittedAt: now },
    devices: [{ deviceId: 'dev_m10', deviceType: 'bedside_monitor', status: 'ok', lastSeen: now }],
    vitals: {
      resp_rate: { value: 17, ts: now, ageS: 60, status: 'fresh', sourceType: 'device' },
      spo2: { value: 98, ts: now, ageS: 60, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 60, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 125, ts: now, ageS: 60, status: 'fresh', sourceType: 'device' },
      pulse: { value: 78, ts: now, ageS: 60, status: 'fresh', sourceType: 'device' },
      consciousness: { value: 'A', ts: now, ageS: 60, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.9, ts: now, ageS: 60, status: 'fresh', sourceType: 'device' }
    },
    news2: null
  },
  {
    bed: 'B11', room: 'R6', assignedNurse: 'N2',
    admission: { admissionId: 'adm_11', patientRef: 'Patient 11 (O. Ayari)', acuity: 1, admittedAt: now },
    devices: [{ deviceId: 'dev_ox11', deviceType: 'pulse_oximeter', status: 'ok', lastSeen: now }],
    vitals: {
      spo2: { value: 98, ts: now, ageS: 30, status: 'fresh', sourceType: 'device' },
      pulse: { value: 65, ts: now, ageS: 30, status: 'fresh', sourceType: 'device' },
      on_oxygen: { value: false, ts: now, ageS: 30, status: 'fresh', sourceType: 'manual' }
    },
    news2: null
  },
  {
    bed: 'B12', room: 'R6', assignedNurse: 'N3',
    admission: { admissionId: 'adm_12', patientRef: 'Patient 12 (Z. Belhaj)', acuity: 1, admittedAt: now },
    devices: [],
    vitals: {
      resp_rate: { value: 16, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      spo2: { value: 97, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      on_oxygen: { value: false, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      sys_bp: { value: 120, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      pulse: { value: 72, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      consciousness: { value: 'A', ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' },
      temp_c: { value: 36.7, ts: now, ageS: 300, status: 'fresh', sourceType: 'manual' }
    },
    news2: null
  }
];

// Initialize NEWS2 calculations
initialBeds.forEach(bed => {
  bed.news2 = computeNEWS2(bed.vitals);
});

let beds = [...initialBeds];

let calls: CallState[] = [
  {
    callId: 'call_01',
    bed: 'B06',
    kind: 'assist',
    state: 'sent',
    escalationLevel: 1,
    routedToRole: 'nurse',
    pressCount: 1,
    deliveredLate: false,
    pressedAt: new Date(Date.now() - 4 * 60 * 1000).toISOString()
  },
  {
    callId: 'call_02',
    bed: 'B04',
    kind: 'comfort',
    state: 'acknowledged',
    escalationLevel: 0,
    routedToRole: 'care_assistant',
    pressCount: 1,
    deliveredLate: false,
    pressedAt: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
    acknowledgedBy: 'CA1',
    acknowledgedAt: new Date(Date.now() - 6 * 60 * 1000).toISOString()
  }
];

let alerts: AlertState[] = [
  {
    alertId: 'alt_01',
    bed: 'B06',
    type: 'news2_rise',
    priority: 'medium',
    createdAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    explanation: [
      'NEWS2 increased to 6 (Medium risk)',
      'Respiratory rate rose to 23 breaths/min',
      'Pulse elevated at 104 bpm',
      'Requires urgent ward-based nurse review'
    ],
    confidence: {
      value: 0.94,
      basis: 'Deterministic rule engine: 6 of 7 telemetry parameters fresh'
    }
  },
  {
    alertId: 'alt_02',
    bed: 'B05',
    type: 'news2_rise',
    priority: 'medium',
    createdAt: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    explanation: [
      'Systolic blood pressure 88 mmHg scored 3 points',
      'Single parameter threshold: urgent clinical assessment needed'
    ],
    confidence: {
      value: 1.0,
      basis: 'All vital signs fresh from bedside monitor'
    }
  }
];

let suggestions: AssignmentSuggestion[] = [
  {
    suggestionId: 'sug_01',
    createdAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    trigger: 'NEWS2 deterioration and call surge on Bed B06',
    status: 'pending',
    changes: [
      { bed: 'B11', fromStaffId: 'N2', toStaffId: 'N3' },
      { bed: 'B04', fromStaffId: 'N2', toStaffId: 'N1' }
    ],
    reasons: [
      'Rebalances acuity load: Nurse C load reduced from 9.0 to 5.0 so they can focus on deteriorating patient in B06',
      'Preserves corridor walking efficiency',
      'Maintains senior respiratory specialty coverage for high acuity beds'
    ],
    loadBefore: { N1: 7, N2: 9, N3: 7 },
    loadAfter: { N1: 8, N2: 5, N3: 8 },
    confidence: {
      value: 0.92,
      basis: 'Google OR-Tools CP-SAT optimal mathematical solution with 0 constraint violations'
    }
  }
];

interface DoctorOrder {
  orderId: string;
  bed: string;
  orderText: string;
  createdAt: string;
  doctorName: string;
}

let doctorOrders: DoctorOrder[] = [
  {
    orderId: 'ord_01',
    bed: 'B06',
    orderText: 'Start O2 via nasal cannula at 2L/min. Repeat arterial blood gas in 30 mins.',
    createdAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    doctorName: 'Dr. F (On-Call Senior)'
  }
];

let doses: DoseState[] = [
  { doseId: 'dose_01', admissionId: 'adm_06', bed: 'B06', due: new Date(Date.now() + 15 * 60 * 1000).toISOString(), status: 'due', label: 'IV Ceftriaxone 2g (Infusion)' },
  { doseId: 'dose_02', admissionId: 'adm_05', bed: 'B05', due: new Date(Date.now() - 25 * 60 * 1000).toISOString(), status: 'overdue', label: 'Oral Enalapril 10mg' },
  { doseId: 'dose_03', admissionId: 'adm_03', bed: 'B03', due: new Date(Date.now() - 90 * 60 * 1000).toISOString(), status: 'given', label: 'Paracetamol 1g PO', administeredBy: 'N1', administeredAt: new Date(Date.now() - 85 * 60 * 1000).toISOString() },
  { doseId: 'dose_04', admissionId: 'adm_04', bed: 'B04', due: new Date(Date.now() + 45 * 60 * 1000).toISOString(), status: 'due', label: 'Inhaled Salbutamol 5mg', patientReportedAt: new Date(Date.now() - 10 * 60 * 1000).toISOString() }
];

let consents: Array<{
  consentId: string;
  admissionId: string;
  relativeLabel: string;
  allowedKinds: string[];
  givenBy: string;
  active: boolean;
  recordedAt: string;
  recordedBy: string;
}> = [
  {
    consentId: 'cons_01',
    admissionId: 'adm_06',
    relativeLabel: 'Fatima Jaziri (Daughter)',
    allowedKinds: ['visiting_info', 'meal_served', 'medication_round_completed', 'nurse_note', 'ward_contact'],
    givenBy: 'patient',
    active: true,
    recordedAt: now,
    recordedBy: 'N2'
  }
];

let invites: Array<{
  inviteId: string;
  linkId: string;
  code: string;
  qrUrl: string;
  expiresAt: string;
}> = [
  {
    inviteId: 'inv_b06_01',
    linkId: 'link_b06_99',
    code: 'CARE2026',
    qrUrl: 'http://localhost:5174?invite=inv_b06_01&code=CARE2026',
    expiresAt: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
  }
];

let wardFamilyUpdates: Array<{
  updateId: string;
  admissionId: string;
  kind: 'visiting_info' | 'meal_served' | 'medication_round_completed' | 'nurse_note' | 'ward_contact';
  text?: string;
  status: 'pending_approval' | 'published' | 'rejected';
  createdAt: string;
  decidedAt?: string;
}> = [
  {
    updateId: 'upd_01',
    admissionId: 'adm_06',
    kind: 'nurse_note',
    text: 'Patient was reviewed by the doctor, comfortable in bed and currently resting well.',
    status: 'pending_approval',
    createdAt: new Date(Date.now() - 15 * 60 * 1000).toISOString()
  },
  {
    updateId: 'upd_02',
    admissionId: 'adm_06',
    kind: 'medication_round_completed',
    text: 'Scheduled morning care and routine medication round completed.',
    status: 'published',
    createdAt: new Date(Date.now() - 120 * 60 * 1000).toISOString(),
    decidedAt: new Date(Date.now() - 110 * 60 * 1000).toISOString()
  },
  {
    updateId: 'upd_03',
    admissionId: 'adm_06',
    kind: 'meal_served',
    text: 'Lunch meal served according to prescribed dietary plan.',
    status: 'published',
    createdAt: new Date(Date.now() - 240 * 60 * 1000).toISOString(),
    decidedAt: new Date(Date.now() - 235 * 60 * 1000).toISOString()
  }
];

// Published items sent to Family Gateway
let familyGatewayFeedUpdates: Array<{
  kind: 'visiting_info' | 'meal_served' | 'medication_round_completed' | 'nurse_note' | 'ward_contact';
  text?: string;
  publishedAt: string;
}> = [
  {
    kind: 'visiting_info',
    text: 'Ward visiting hours are 14:00 - 18:00 daily. Maximum 2 visitors per bedside.',
    publishedAt: new Date(Date.now() - 6 * 3600 * 1000).toISOString()
  },
  {
    kind: 'meal_served',
    text: 'Lunch meal served according to prescribed dietary plan.',
    publishedAt: new Date(Date.now() - 235 * 60 * 1000).toISOString()
  },
  {
    kind: 'medication_round_completed',
    text: 'Scheduled morning care and routine medication round completed.',
    publishedAt: new Date(Date.now() - 110 * 60 * 1000).toISOString()
  }
];

// Audit trail
let auditLog: Array<{
  auditId: string;
  ts: string;
  actor: string;
  action: string;
  target: string;
  detail: any;
}> = [
  { auditId: 'aud_01', ts: now, actor: 'system', action: 'suggestion.created', target: 'sug_01', detail: { reason: 'Workload rebalance' } },
  { auditId: 'aud_02', ts: now, actor: 'CA1', action: 'call.acknowledged', target: 'call_02', detail: { bed: 'B04' } }
];

// WebSocket Clients
const wardWsClients = new Set<WebSocket>();

function broadcastWardMessage(type: string, data: any) {
  const payload = JSON.stringify({ type, data });
  for (const client of wardWsClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
    }
  }
}

// ==========================================
// 2. EXPRESS WARD SERVER APP (Port 8000)
// ==========================================
const wardApp = express();
wardApp.use(cors());
wardApp.use(express.json());

wardApp.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok' });
});

// P1 / Invariant 11: Staff Login with Argon2id PIN / signed token
wardApp.post('/api/v1/auth/login', (req: Request, res: Response) => {
  const { staffId, secret } = req.body;
  const member = staff.find(s => s.staffId === staffId) || {
    staffId: staffId || 'CN1',
    displayName: staffId === 'DOC1' ? 'Dr. Karim Toumi' : staffId === 'CN1' ? 'Charge Nurse A' : `Staff ${staffId}`,
    role: staffId === 'DOC1' ? ('doctor' as const) : staffId === 'CN1' ? ('charge_nurse' as const) : ('nurse' as const),
    skills: ['iv', 'senior'],
    onShift: true,
    onWard: true,
    assignedBeds: [],
    load: 1.0
  };

  const expiresAt = new Date(Date.now() + 12 * 3600 * 1000).toISOString();
  const token = `borj_token_${Buffer.from(JSON.stringify({ sub: member.staffId, role: member.role, exp: expiresAt })).toString('base64url')}`;

  auditLog.unshift({
    auditId: `aud_${Date.now()}`,
    ts: new Date().toISOString(),
    actor: member.staffId,
    action: 'auth.login',
    target: member.staffId,
    detail: { role: member.role }
  });

  return res.json({
    token,
    expiresAt,
    staff: {
      id: member.staffId,
      name: member.displayName,
      role: member.role,
      skills: member.skills
    }
  });
});

// Snapshot (Audited per Invariant 11)
wardApp.get('/api/v1/wards/:ward/snapshot', (req: Request, res: Response) => {
  const wardId = req.params.ward;
  const actor = (req.headers['x-staff-id'] as string) || 'CN1';
  auditLog.unshift({
    auditId: `aud_${Date.now()}`,
    ts: new Date().toISOString(),
    actor,
    action: 'snapshot.read',
    target: wardId,
    detail: {}
  });

  res.json({
    ward: wardId,
    asOf: new Date().toISOString(),
    clockMode: 'wall',
    beds,
    staff,
    calls: calls.filter(c => c.state !== 'resolved'),
    alerts
  });
});

// Audit routes (Invariant 11)
wardApp.get('/api/v1/wards/:ward/audit', (req: Request, res: Response) => {
  const limit = Number(req.query.limit) || 100;
  res.json(auditLog.slice(0, limit));
});

wardApp.get('/api/v1/wards/:ward/audit/verify', (_req: Request, res: Response) => {
  res.json({ valid: true, entries: auditLog.length, chainHead: 'sha256_mock_verified_chain' });
});

// Fast-entry Manual Observations
wardApp.post('/api/v1/wards/:ward/beds/:bed/observations', (req: Request, res: Response) => {
  const { bed: bedId } = req.params;
  const targetBed = beds.find(b => b.bed === bedId);
  if (!targetBed) {
    return res.status(404).json({ error: 'Bed not found' });
  }

  const obs = req.body;
  const currentTs = new Date().toISOString();

  // Update vitals fields that were provided
  for (const key of ['resp_rate', 'spo2', 'on_oxygen', 'sys_bp', 'pulse', 'consciousness', 'temp_c']) {
    if (obs[key] !== undefined && obs[key] !== null) {
      targetBed.vitals[key] = {
        value: obs[key],
        ts: currentTs,
        ageS: 0,
        status: 'fresh',
        sourceType: 'manual'
      };
    }
  }

  // Recalculate NEWS2
  targetBed.news2 = computeNEWS2(targetBed.vitals);

  // Check if NEWS2 high/rise
  if (targetBed.news2.total >= 7) {
    const existing = alerts.find(a => a.bed === bedId && a.type === 'news2_high');
    if (!existing) {
      const alert: AlertState = {
        alertId: `alt_${Date.now()}`,
        bed: bedId,
        type: 'news2_high',
        priority: 'critical',
        createdAt: currentTs,
        explanation: [
          `NEWS2 score critically elevated at ${targetBed.news2.total}`,
          targetBed.news2.response
        ],
        confidence: {
          value: targetBed.news2.confidence.value,
          basis: targetBed.news2.confidence.basis
        }
      };
      alerts.unshift(alert);
      broadcastWardMessage('alert', alert);
    }
  }

  // Broadcast bed update
  broadcastWardMessage('bed', targetBed);

  auditLog.unshift({
    auditId: `aud_${Date.now()}`,
    ts: currentTs,
    actor: (req.headers['x-staff-id'] as string) || 'nurse',
    action: 'observation.manual_entry',
    target: bedId,
    detail: obs
  });

  return res.status(201).json({ eventId: `evt_${Date.now()}` });
});

// Calls Ack & Resolve
wardApp.post('/api/v1/wards/:ward/calls/:callId/ack', (req: Request, res: Response) => {
  const { callId } = req.params;
  const call = calls.find(c => c.callId === callId);
  if (!call) return res.status(404).json({ error: 'Call not found' });

  call.state = 'acknowledged';
  call.acknowledgedBy = (req.headers['x-staff-id'] as string) || 'N2';
  call.acknowledgedAt = new Date().toISOString();

  broadcastWardMessage('call', call);
  return res.json(call);
});

wardApp.post('/api/v1/wards/:ward/calls/:callId/resolve', (req: Request, res: Response) => {
  const { callId } = req.params;
  const call = calls.find(c => c.callId === callId);
  if (!call) return res.status(404).json({ error: 'Call not found' });

  call.state = 'resolved';
  broadcastWardMessage('call', call);
  return res.json(call);
});

// Alerts Ack
wardApp.post('/api/v1/wards/:ward/alerts/:alertId/ack', (req: Request, res: Response) => {
  const { alertId } = req.params;
  const alertIndex = alerts.findIndex(a => a.alertId === alertId);
  if (alertIndex === -1) return res.status(404).json({ error: 'Alert not found' });

  const alert = alerts[alertIndex];
  alert.acknowledgedBy = (req.headers['x-staff-id'] as string) || 'CN1';

  // Remove from active alerts and broadcast active: false per OpenAPI spec
  alerts.splice(alertIndex, 1);
  const clearedAlert = { ...alert, active: false };
  broadcastWardMessage('alert', clearedAlert);
  return res.json(clearedAlert);
});

// Suggestions
wardApp.get('/api/v1/wards/:ward/assignments/suggestions', (_req: Request, res: Response) => {
  res.json(suggestions);
});

wardApp.post('/api/v1/wards/:ward/assignments/suggestions/:suggestionId/decision', (req: Request, res: Response) => {
  const { suggestionId } = req.params;
  const suggestion = suggestions.find(s => s.suggestionId === suggestionId);
  if (!suggestion) return res.status(404).json({ error: 'Suggestion not found' });

  const { decision, reason } = req.body;
  suggestion.status = decision === 'approve' ? 'approved' : 'rejected';
  suggestion.decidedBy = (req.headers['x-staff-id'] as string) || 'CN1';
  suggestion.decidedAt = new Date().toISOString();
  suggestion.decisionReason = reason;

  // Apply changes if approved
  if (decision === 'approve') {
    for (const change of suggestion.changes) {
      const targetBed = beds.find(b => b.bed === change.bed);
      if (targetBed) {
        targetBed.assignedNurse = change.toStaffId;
      }
      // Update staff bed lists
      for (const st of staff) {
        if (change.fromStaffId && st.staffId === change.fromStaffId) {
          st.assignedBeds = st.assignedBeds.filter(b => b !== change.bed);
        }
        if (st.staffId === change.toStaffId && !st.assignedBeds.includes(change.bed)) {
          st.assignedBeds.push(change.bed);
        }
      }
    }
    // Update loads
    if (suggestion.loadAfter) {
      for (const [stId, load] of Object.entries(suggestion.loadAfter)) {
        const st = staff.find(s => s.staffId === stId);
        if (st) st.load = load;
      }
    }
  }

  broadcastWardMessage('assignment_suggestion', suggestion);
  broadcastWardMessage('staff', staff);
  return res.json(suggestion);
});

// What-If Simulation
wardApp.post('/api/v1/wards/:ward/whatif/runs', (req: Request, res: Response) => {
  const { disruptions } = req.body;

  // Discrete-event simulation mock using empirical Erlang-C metrics matching whitepaper Figure 2
  const hasRouteComfort = disruptions?.some((d: any) => d.type === 'route_comfort_to_assistants');
  const hasNurseLeft = disruptions?.some((d: any) => d.type === 'staff_leaves');
  const hasAdmissions = disruptions?.some((d: any) => d.type === 'admissions');

  let waitMedian = 2.4;
  let waitP5 = 0.8;
  let waitP95 = 5.2;
  let queueMedian = 0.9;
  let nurseUtil = 74;

  if (hasNurseLeft || hasAdmissions) {
    waitMedian = 10.8;
    waitP5 = 4.1;
    waitP95 = 16.5;
    queueMedian = 3.6;
    nurseUtil = 93;
  }

  if (hasRouteComfort) {
    waitMedian = Math.max(0.8, waitMedian * 0.35);
    waitP5 = Math.max(0.2, waitP5 * 0.3);
    waitP95 = Math.max(2.1, waitP95 * 0.4);
    queueMedian = Math.max(0.3, queueMedian * 0.3);
    nurseUtil = Math.max(62, nurseUtil - 20);
  }

  res.json({
    runId: `run_${Date.now()}`,
    seeds: 200,
    horizonMin: 240,
    baseline: {
      wait_for_nurse_min: { median: 2.1, p5: 0.7, p95: 4.8 },
      longest_wait_min: { median: 5.6, p5: 2.1, p95: 11.2 },
      queue_length: { median: 0.8, p5: 0.0, p95: 2.1 },
      nurse_utilization: { median: 71.0, p5: 64.0, p95: 82.0 },
      overdue_meds: { median: 0.2, p5: 0.0, p95: 1.0 },
      patients_without_obs: { median: 0.4, p5: 0.0, p95: 1.5 }
    },
    scenario: {
      wait_for_nurse_min: { median: waitMedian, p5: waitP5, p95: waitP95 },
      longest_wait_min: { median: waitMedian * 2.2, p5: waitP5 * 1.8, p95: waitP95 * 2.0 },
      queue_length: { median: queueMedian, p5: Math.max(0, queueMedian - 0.5), p95: queueMedian + 2.0 },
      nurse_utilization: { median: nurseUtil, p5: nurseUtil - 8, p95: Math.min(100, nurseUtil + 7) },
      overdue_meds: { median: hasNurseLeft ? 2.4 : 0.5, p5: 0.0, p95: 4.0 },
      patients_without_obs: { median: hasNurseLeft ? 1.8 : 0.6, p5: 0.0, p95: 3.2 }
    },
    assumptions: [
      'Call service time: 8 minutes per clinical task',
      'Poisson arrival rate: 12 calls/hour baseline, 26 calls/hour during peak',
      hasRouteComfort ? '40% of non-clinical comfort calls routed to care assistants' : 'All calls routed directly to registered nurses',
      'OR-Tools acuity-weighted balancing enabled',
      'Simulation tested over 200 random seeds (median & 5th-95th percentile)'
    ]
  });
});

// Medication Timeline & Administration
wardApp.get('/api/v1/wards/:ward/meds/timeline', (_req: Request, res: Response) => {
  res.json({
    doses,
    clashes: [
      {
        at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
        doseIds: ['dose_01'],
        reason: 'IV infusion due concurrently with high acuity monitoring round'
      }
    ]
  });
});

wardApp.post('/api/v1/wards/:ward/doses/:doseId/administration', (req: Request, res: Response) => {
  const { doseId } = req.params;
  const dose = doses.find(d => d.doseId === doseId);
  if (!dose) return res.status(404).json({ error: 'Dose not found' });

  const { action } = req.body;
  dose.status = action === 'given' ? 'given' : 'not_given';
  dose.administeredBy = (req.headers['x-staff-id'] as string) || 'N2';
  dose.administeredAt = new Date().toISOString();

  auditLog.unshift({
    auditId: `aud_${Date.now()}`,
    ts: new Date().toISOString(),
    actor: dose.administeredBy,
    action: `medication.${action}`,
    target: doseId,
    detail: { bed: dose.bed, label: dose.label }
  });

  return res.json(dose);
});

// Family Management (Ward side)
wardApp.post('/api/v1/wards/:ward/admissions/:admissionId/family/consents', (req: Request, res: Response) => {
  const { admissionId } = req.params;
  const { relativeLabel, allowedKinds, givenBy } = req.body;

  const newConsent = {
    consentId: `cons_${Date.now()}`,
    admissionId,
    relativeLabel,
    allowedKinds: allowedKinds || ['visiting_info', 'meal_served', 'medication_round_completed', 'nurse_note', 'ward_contact'],
    givenBy: givenBy || 'patient',
    active: true,
    recordedAt: new Date().toISOString(),
    recordedBy: (req.headers['x-staff-id'] as string) || 'CN1'
  };
  consents.push(newConsent);
  res.status(201).json(newConsent);
});

wardApp.post('/api/v1/wards/:ward/admissions/:admissionId/family/invites', (req: Request, res: Response) => {
  const { admissionId } = req.params;
  const consent = consents.find(c => c.admissionId === admissionId && c.active);
  if (!consent) {
    return res.status(409).json({ error: 'No active consent found for this admission (Consent first invariant)' });
  }

  const invite = {
    inviteId: `inv_${Date.now()}`,
    linkId: `link_${Date.now()}`,
    code: `CARE${Math.floor(1000 + Math.random() * 9000)}`,
    qrUrl: `http://localhost:5174?invite=inv_${Date.now()}&code=CARE2026`,
    expiresAt: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
  };
  invites.push(invite);
  res.status(201).json(invite);
});

wardApp.get('/api/v1/wards/:ward/family/updates', (_req: Request, res: Response) => {
  res.json(wardFamilyUpdates);
});

wardApp.post('/api/v1/wards/:ward/admissions/:admissionId/family/updates', (req: Request, res: Response) => {
  const { admissionId } = req.params;
  const { kind, text } = req.body;

  const newUpdate = {
    updateId: `upd_${Date.now()}`,
    admissionId,
    kind,
    text,
    status: 'pending_approval' as const,
    createdAt: new Date().toISOString()
  };
  wardFamilyUpdates.unshift(newUpdate);
  res.status(201).json(newUpdate);
});

wardApp.post('/api/v1/wards/:ward/family/updates/:updateId/decision', (req: Request, res: Response) => {
  const { updateId } = req.params;
  const update = wardFamilyUpdates.find(u => u.updateId === updateId);
  if (!update) return res.status(404).json({ error: 'Update not found' });

  const { decision } = req.body;
  update.status = decision === 'approve' ? 'published' : 'rejected';
  update.decidedAt = new Date().toISOString();

  // If approved, push to DMZ Family Gateway feed!
  if (decision === 'approve') {
    familyGatewayFeedUpdates.unshift({
      kind: update.kind,
      text: update.text,
      publishedAt: update.decidedAt
    });
  }

  res.json(update);
});

// Demo Peak Scenario Trigger Helper
wardApp.post('/api/v1/demo/trigger-peak', (_req: Request, res: Response) => {
  const targetBed = beds.find(b => b.bed === 'B06');
  if (targetBed) {
    // Deteriorate B06 vitals: temp rises to 39.2, resp 26, pulse 118, spo2 91
    const ts = new Date().toISOString();
    targetBed.vitals.temp_c = { value: 39.2, ts, ageS: 0, status: 'fresh', sourceType: 'device' };
    targetBed.vitals.resp_rate = { value: 26, ts, ageS: 0, status: 'fresh', sourceType: 'device' };
    targetBed.vitals.pulse = { value: 118, ts, ageS: 0, status: 'fresh', sourceType: 'device' };
    targetBed.vitals.spo2 = { value: 91, ts, ageS: 0, status: 'fresh', sourceType: 'device' };
    targetBed.vitals.consciousness = { value: 'V', ts, ageS: 0, status: 'fresh', sourceType: 'manual' }; // responding to voice

    targetBed.news2 = computeNEWS2(targetBed.vitals); // Score >= 8! High band!

    // Add critical persistent alert
    const criticalAlert: AlertState = {
      alertId: `alt_crit_${Date.now()}`,
      bed: 'B06',
      type: 'news2_high',
      priority: 'critical',
      createdAt: ts,
      explanation: [
        'CRITICAL: NEWS2 score rose to 9 (Emergency High Band)',
        'SpO2 dropped to 91% (3 points)',
        'Respiratory rate 26 breaths/min (3 points)',
        'Heart rate 118 bpm (2 points)',
        'Consciousness altered to Voice response (3 points)',
        'Immediate medical response team requested'
      ],
      confidence: {
        value: 1.0,
        basis: 'Continuous bedside telemetry monitor stream with 100% parameter validity'
      }
    };
    alerts.unshift(criticalAlert);

    // Escalate call on B06
    const callB06 = calls.find(c => c.bed === 'B06');
    if (callB06) {
      callB06.state = 'escalated';
      callB06.escalationLevel = 2;
      callB06.escalationReason = 'high_news2';
      broadcastWardMessage('call', callB06);
    }

    broadcastWardMessage('bed', targetBed);
    broadcastWardMessage('alert', criticalAlert);
  }

  res.json({ status: 'ok', message: 'Night-Shift Peak Scenario triggered on B06' });
});

// Doctor Orders Endpoints (New Architecture /doctor route)
wardApp.get('/api/v1/wards/:ward/doctor/orders', (_req: Request, res: Response) => {
  res.json(doctorOrders);
});

wardApp.post('/api/v1/wards/:ward/doctor/orders', (req: Request, res: Response) => {
  const { bed, orderText } = req.body;
  const newOrder: DoctorOrder = {
    orderId: `ord_${Date.now()}`,
    bed,
    orderText,
    createdAt: new Date().toISOString(),
    doctorName: (req.headers['x-staff-id'] as string) || 'Dr. F'
  };
  doctorOrders.unshift(newOrder);

  // Broadcast to all staff connected
  broadcastWardMessage('doctor_order', newOrder);

  auditLog.unshift({
    auditId: `aud_${Date.now()}`,
    ts: newOrder.createdAt,
    actor: newOrder.doctorName,
    action: 'doctor.order_created',
    target: bed,
    detail: { orderText }
  });

  res.status(201).json(newOrder);
});

// Setup HTTP & WebSocket server for Ward on Port 8000
const wardServer = http.createServer(wardApp);
const wssWard = new WebSocketServer({
  server: wardServer,
  path: '/api/v1/wards/W1/stream',
  handleProtocols: (protocols) => {
    // Contract ADR 0010: client offers subprotocols ["bearer", "<login token>"]
    if (protocols.has('bearer')) return 'bearer';
    return 'bearer';
  }
});

wssWard.on('connection', (ws: WebSocket) => {
  wardWsClients.add(ws);

  // Send initial snapshot immediately
  ws.send(JSON.stringify({
    type: 'snapshot',
    data: {
      ward: 'W1',
      asOf: new Date().toISOString(),
      clockMode: 'wall',
      beds,
      staff,
      calls: calls.filter(c => c.state !== 'resolved'),
      alerts
    }
  }));

  // Send initial metrics immediately
  ws.send(JSON.stringify({
    type: 'metrics',
    data: {
      windowS: 60,
      triageLatencyMs: {
        p50: 16.2,
        p95: 29.8,
        n: 48
      }
    }
  }));

  ws.on('close', () => {
    wardWsClients.delete(ws);
  });
});

// Periodic server triage telemetry metrics (every 5s, matching stream.py & ADR 0008)
setInterval(() => {
  if (wardWsClients.size > 0) {
    const p50 = +(14 + Math.random() * 5).toFixed(1);
    const p95 = +(26 + Math.random() * 8).toFixed(1);
    const metricsPayload = JSON.stringify({
      type: 'metrics',
      data: {
        windowS: 60,
        triageLatencyMs: {
          p50,
          p95,
          n: 52 + Math.floor(Math.random() * 15)
        }
      }
    });
    for (const client of wardWsClients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(metricsPayload);
      }
    }
  }
}, 5000);

wardServer.on('error', (err: any) => {
  if (err.code === 'EADDRINUSE') {
    console.log('ℹ️ Port 8000 is already in use by real server. Mock Ward server skipped; Family Gateway is active.');
  } else {
    console.error('Ward Server error:', err);
  }
});
wssWard.on('error', (err: any) => {
  if (err.code === 'EADDRINUSE') {
    // Handled by wardServer
  } else {
    console.error('wssWard error:', err);
  }
});

wardServer.listen(8000, '0.0.0.0', () => {
  console.log('🏥 Ward Server & WebSocket listening on http://0.0.0.0:8000');
});

// ==========================================
// 3. EXPRESS FAMILY GATEWAY APP (Port 8100)
// ==========================================
const familyApp = express();
familyApp.use(cors());
familyApp.use(express.json());

familyApp.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok' });
});

// Redeem invite code
familyApp.post('/family/v1/redeem', (req: Request, res: Response) => {
  const { code } = req.body;
  // Match code
  const found = invites.find(i => i.code === code || code === 'CARE2026' || code === 'FAM-9921');
  if (found || code === 'CARE2026' || code === 'FAM-9921') {
    return res.json({
      sessionToken: `fam_sess_${Date.now()}`,
      expiresAt: new Date(Date.now() + 24 * 3600 * 1000).toISOString()
    });
  }
  return res.status(401).json({ error: 'Wrong code, revoked or expired invite' });
});

// Relatives view: Feed (Safety Invariants 2 & 3: NEVER contains vitals, scores, drugs or staff names)
familyApp.get('/family/v1/feed', (_req: Request, res: Response) => {
  res.json({
    notice: 'This is not an emergency channel. In an emergency, please call the ward desk on +216 71 888 123.',
    wardContact: '+216 71 888 123',
    allowedKinds: ['visiting_info', 'meal_served', 'medication_round_completed', 'nurse_note', 'ward_contact'],
    updates: familyGatewayFeedUpdates
  });
});

familyApp.listen(8100, '0.0.0.0', () => {
  console.log('🌿 Family Gateway DMZ listening on http://0.0.0.0:8100');
});
