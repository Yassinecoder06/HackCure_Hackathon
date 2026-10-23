// Bilingual UI strings module for apps/family (Family Care Link).
// Safety invariant 2: nothing here mentions vital signs, scores, drugs, staff, bed or room, and nothing is invented:
// the page shows only what the ward approved (the feed) and a fixed "this is not an emergency channel" notice.

export type Language = 'fr' | 'en';

export const DICTIONARY = {
  fr: {
    app: {
      title: 'PiCare Family Care Link',
      hospitalName: 'Hôpital Public Tunisien — Service W1'
    },
    emergency: {
      badge: 'CANAL NON-URGENT',
      // Fallback only: the gateway sends the notice and the ward's phone number with every feed.
      notice: 'Ce portail n\'est PAS un canal d\'urgence. En cas d\'urgence, appelez le service.',
      phone: '+216 70 000 000',
      callNow: 'Appeler le Poste Infirmier'
    },
    auth: {
      redeemTitle: 'Accès Espace Proches',
      redeemDesc: 'Saisissez le code à usage unique que l\'infirmier(ère) vous a remis, ou scannez le QR code du service.',
      pinPlaceholder: 'Code à 6 chiffres',
      redeemBtn: 'Accéder aux Nouvelles',
      invalidCode: 'Code invalide ou expiré. Veuillez vérifier auprès de l\'équipe soignante.',
      qrHint: 'Le QR code du service ouvre cette page avec votre invitation.'
    },
    feed: {
      title: 'Nouvelles du service',
      refreshBtn: 'Actualiser',
      emptyTitle: 'Aucune nouvelle pour l\'instant',
      emptyDesc: 'Les nouvelles approuvées par l\'équipe soignante apparaîtront ici.',
      kinds: {
        visiting_info: 'Horaires & Consignes de Visite',
        meal_served: 'Repas servi',
        medication_round_completed: 'Tour de soins terminé',
        nurse_note: 'Message de l\'Équipe Soignante',
        ward_contact: 'Coordonnées du service'
      },
      privacyAssurance: 'Connexion chiffrée. Vous ne voyez que ce que le patient a accepté de partager. Aucune donnée médicale n\'est affichée ici. Démonstration : données synthétiques.'
    }
  },
  en: {
    app: {
      title: 'PiCare Family Care Link',
      hospitalName: 'Tunisian Public Hospital — Ward W1'
    },
    emergency: {
      badge: 'NON-EMERGENCY CHANNEL',
      notice: 'This portal is NOT an emergency channel. In an emergency, call the ward.',
      phone: '+216 70 000 000',
      callNow: 'Call the Nursing Desk'
    },
    auth: {
      redeemTitle: 'Family Access',
      redeemDesc: 'Enter the one-time code the nurse gave you, or scan the ward\'s QR code.',
      pinPlaceholder: '6-digit code',
      redeemBtn: 'Access Updates',
      invalidCode: 'Invalid or expired code. Please verify with the ward nursing team.',
      qrHint: 'The ward\'s QR code opens this page with your invitation.'
    },
    feed: {
      title: 'News from the ward',
      refreshBtn: 'Refresh',
      emptyTitle: 'No news yet',
      emptyDesc: 'Updates approved by the nursing team will appear here.',
      kinds: {
        visiting_info: 'Visiting Hours & Ward Guidelines',
        meal_served: 'Meal served',
        medication_round_completed: 'Care round completed',
        nurse_note: 'Message from the Nursing Team',
        ward_contact: 'Ward Contact Information'
      },
      privacyAssurance: 'Encrypted connection. You only see what the patient agreed to share. No medical data is shown here. Demo: synthetic data.'
    }
  }
};

export const STRINGS = DICTIONARY.fr; // Default
