// Centralized UI strings module for apps/family (Family Care Link)
// Strictly follows Invariant 2: zero mention of vitals, scores, drugs, or staff names.

export const STRINGS = {
  app: {
    title: 'Borj Family Care Link',
    subtitle: 'Reassurance & Care Updates for Loved Ones',
    welcome: 'Welcome to your patient care window',
    hospitalName: 'Tunisian Public Hospital — Ward W1'
  },
  emergency: {
    badge: 'NON-EMERGENCY CHANNEL',
    notice: 'This portal provides routine reassurance updates. It is NOT an emergency channel.',
    instruction: 'If you have an urgent medical emergency, call the nursing desk immediately:',
    phone: '+216 71 888 123',
    callNow: 'Call Nursing Desk'
  },
  auth: {
    redeemTitle: 'Enter Your Care Access PIN',
    redeemDesc: 'Enter the one-time code provided on your patient admission invitation letter or scan the bedside QR code.',
    pinPlaceholder: 'e.g. CARE2026',
    redeemBtn: 'Access Care Updates',
    demoHint: 'For demonstration, enter code: CARE2026',
    invalidCode: 'Invalid or expired code. Please verify with the ward nursing team.'
  },
  feed: {
    title: 'Daily Care & Comfort Timeline',
    refreshBtn: 'Check for Updates',
    lastChecked: 'Updated just now',
    emptyTitle: 'No updates posted yet',
    emptyDesc: 'The ward nursing staff will post updates following scheduled rounds.',
    kinds: {
      visiting_info: 'Visiting Hours & Ward Guidelines',
      meal_served: 'Meal & Dietary Service',
      medication_round_completed: 'Routine Care Milestone',
      nurse_note: 'Message from the Nursing Team',
      ward_contact: 'Ward Contact Information'
    },
    privacyAssurance: 'Data Protection: This connection is encrypted and authorized under hospital consent protocols (Law 2004-63). Clinical telemetry is strictly reserved for the attending medical team.'
  }
};
