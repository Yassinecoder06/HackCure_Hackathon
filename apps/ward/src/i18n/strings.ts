// Centralized UI strings module for apps/ward
// All UI strings are kept in this file to enable future translations (French / Tunisian Arabic).

export const STRINGS = {
  app: {
    title: 'Borj-PiCare',
    subtitle: 'Ward Control Tower',
    wardName: 'Ward W1 — Internal Medicine',
    principle: 'Advisory only. A human decides every clinical action.',
    connectionOnline: 'Live Stream Connected',
    connectionOffline: 'Reconnecting to Ward Server...',
    mockActive: 'Simulation Mode (Mock Server)'
  },
  nav: {
    stationBoard: 'Station Board (2D Plan)',
    staffView: 'Staff & Decisions',
    doctorConsole: 'Doctor Console',
    digitalTwin: '3D Digital Twin',
    triggerPeakDemo: 'Trigger Night Peak Demo',
    currentStaff: 'Active Staff Member'
  },
  board: {
    header: 'Ward Floor Plan & Acuity Triage',
    floorPlanTitle: 'Corridor & Bed Layout (seed/ward-W1.yaml)',
    nurseStation: 'Nurse Station (x=0)',
    roomLabel: 'Room',
    bedLabel: 'Bed',
    priorityListTitle: 'Clinical Acuity Ranking (NEWS2)',
    partialWarning: 'PARTIAL',
    staleIndicator: 'STALE',
    missingIndicator: 'MISSING',
    dataAge: 'Obs age',
    inspectBed: 'Inspect Parameters',
    clickToView: 'Click any bed to view score components & explanation',
    emptyTriage: 'No active admissions in triage queue',
    threeMeterFriendly: 'Scale 100% (Optimized for 3-meter display)'
  },
  news2: {
    score: 'NEWS2 Score',
    low: 'Low Risk (0-4)',
    lowMedium: 'Low-Medium (Single 3)',
    medium: 'Medium Risk (5-6)',
    high: 'High Risk (7+)',
    respRate: 'Resp Rate',
    spo2: 'SpO2',
    onOxygen: 'Supplemental O2',
    sysBp: 'Systolic BP',
    pulse: 'Pulse',
    consciousness: 'Consciousness (ACVPU)',
    temp: 'Temperature',
    points: 'pts',
    responseProtocol: 'Clinical Response Protocol'
  },
  calls: {
    title: 'Bedside Calls',
    assistCall: 'Assistance Needed',
    comfortCall: 'Comfort / Service',
    stateSent: 'Waiting for Nurse',
    stateAck: 'Accepted (Nurse Coming)',
    stateEscalated: 'ESCALATED',
    ackBtn: 'Accept Call',
    resolveBtn: 'Mark Resolved (Bedside)',
    noCalls: 'No open bedside calls'
  },
  alerts: {
    title: 'Escalation Ladder Alerts',
    criticalTakeoverTitle: 'CRITICAL ALERT — URGENT ACTION REQUIRED',
    criticalTakeoverDesc: 'Patient deterioration or unacknowledged emergency alarm requires immediate bedside presence.',
    ackAlertBtn: 'Acknowledge Alarm',
    escalationLevels: {
      low: 'Low (Silent Badge)',
      medium: 'Medium (Chime Notification)',
      critical: 'Critical (Persistent Alarm)'
    }
  },
  fastEntry: {
    button: 'Quick Observation Entry',
    title: '10-Second Bedside Observation Form',
    subtitle: 'Pre-filled from device. Enter only parameters not supplied by monitor.',
    selectBed: 'Target Bed',
    consciousnessLabel: 'Consciousness (ACVPU)',
    acvpuA: 'A — Alert',
    acvpuC: 'C — New Confusion',
    acvpuV: 'V — Responds to Voice',
    acvpuP: 'P — Responds to Pain',
    acvpuU: 'U — Unresponsive',
    oxygenLabel: 'Supplemental Oxygen',
    oxygenYes: 'Yes (On O2)',
    oxygenNo: 'No (Room Air)',
    respRateLabel: 'Respiratory Rate (breaths/min)',
    respRatePlaceholder: 'e.g. 18',
    submit: 'Submit & Recalculate NEWS2',
    cancel: 'Cancel',
    successToast: 'Observations recorded and NEWS2 recomputed in real time.'
  },
  assignments: {
    title: 'OR-Tools Assignment Rebalancing',
    advisoryBadge: 'Advisory Suggestion — You Decide',
    nurseWorkload: 'Nurse Workload (Acuity Weighted)',
    before: 'Before',
    after: 'After',
    reasonsTitle: 'Optimizer Clinical Rationale',
    approveBtn: 'Approve Reassignment',
    rejectBtn: 'Reject Suggestion',
    approvedToast: 'Reassignment approved by Charge Nurse and logged in audit.',
    rejectedToast: 'Suggestion dismissed.'
  },
  whatIf: {
    title: 'SimPy Digital Twin What-If Sandbox',
    subtitle: 'Simulate disruptions forward without touching live ward data.',
    disruptionType: 'Disruption Event',
    runBtn: 'Run Forward Simulation (200 Seeds)',
    running: 'Simulating 200 random trajectories...',
    baseline: 'Baseline Practice',
    scenario: 'Disruption Scenario',
    metrics: {
      wait: 'Mean Wait for Nurse',
      longestWait: 'Longest Patient Wait',
      queue: 'Queue Length',
      utilization: 'Nurse Utilization',
      overdueMeds: 'Overdue Medications'
    },
    percentiles: 'Reporting Median (5th – 95th Percentile Band)',
    assumptionsTitle: 'Simulation Assumptions (Transparent Model)'
  },
  meds: {
    title: 'Shift Medication Timeline',
    overdueWarning: 'OVERDUE DOSE',
    clashWarning: 'Infusion Clash Detected',
    markGiven: 'Mark Given',
    markNotGiven: 'Omit / Not Given',
    patientReported: 'Patient pressed bedside confirmation button (Informational only, does not close dose)'
  },
  family: {
    title: 'Family Care Link Coordination',
    consentTitle: 'Record Patient Consent',
    generateInviteTitle: 'Generate Relative Invite',
    queueTitle: 'Nurse Approval Queue for Family Updates',
    oneTimeCode: 'One-Time PIN Code',
    copyInvite: 'Copy Invite Link',
    approveUpdate: 'Approve & Push to DMZ',
    rejectUpdate: 'Reject Update',
    safetyNotice: 'Invariant 2: Vitals, scores, and drug names are physically prohibited from being sent.'
  }
};
