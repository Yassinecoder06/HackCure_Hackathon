// Bilingual UI strings module for apps/family (Family Care Link)
// Strictly follows Safety Invariant 2: zero mention of clinical vitals, scores, drugs, or staff names.

export type Language = 'fr' | 'en';

export const DICTIONARY = {
  fr: {
    app: {
      title: 'PiCare Family Care Link',
      subtitle: 'Tranquillité & Suivi de Soins pour les Proches',
      welcome: 'Bienvenue sur le portail de suivi de votre proche',
      hospitalName: 'Hôpital Public Tunisien — Service W1',
      patientTag: 'Patient : Lit B06'
    },
    emergency: {
      badge: 'CANAL NON-URGENT',
      notice: 'Ce portail fournit des nouvelles rassurantes de routine. Ce n\'est PAS un canal d\'urgence médicale.',
      instruction: 'En cas d\'urgence médicale vitale, veuillez contacter immédiatement le poste infirmier :',
      phone: '+216 71 888 123',
      callNow: 'Appeler le Poste Infirmier'
    },
    auth: {
      redeemTitle: 'Accès Espace Proches',
      redeemDesc: 'Saisissez le code d\'accès unique remis lors de l\'admission du patient ou flashez le QR code au chevet.',
      pinPlaceholder: 'Ex: CARE2026',
      redeemBtn: 'Accéder aux Nouvelles',
      demoHint: 'Pour la démonstration, saisissez : FAM-9921 ou CARE2026',
      invalidCode: 'Code invalide ou expiré. Veuillez vérifier auprès de l\'équipe soignante.'
    },
    milestones: {
      title: 'Parcours d\'Hospitalisation',
      subtitle: 'Étapes du séjour vers le retour à domicile',
      step1: 'Admission & Accueil',
      step1Desc: 'Installation au lit B06 terminée',
      step2: 'Soins Actifs & Observation',
      step2Desc: 'Surveillance régulière et repos au lit',
      step3: 'Mobilité & Transition',
      step3Desc: 'Reprise progressive d\'autonomie',
      step4: 'Préparation à la Sortie',
      step4Desc: 'Coordination du retour à domicile',
      activeStatus: 'Étape en cours : Patient calme, suivi attentif par l\'équipe soignante.'
    },
    rhythm: {
      title: 'Rythme du Service Aujourd\'hui',
      subtitle: 'Déroulement de la journée au sein de l\'unité',
      activeBadge: 'En cours',
      upcomingBadge: 'À venir',
      passedBadge: 'Terminé',
      slots: [
        { time: '07:30 – 09:00', title: 'Tournée Matinale & Petit-déjeuner', desc: 'Soins d\'hygiène, confort et petit-déjeuner équilibré servis.' },
        { time: '10:00 – 12:00', title: 'Visite de l\'Équipe Médicale', desc: 'Passage des médecins au chevet et revue des dossiers.' },
        { time: '12:30 – 13:30', title: 'Déjeuner Diététique', desc: 'Repas chaud préparé selon le régime prescrit.' },
        { time: '14:00 – 18:00', title: 'Heures de Visite Ouvertes', desc: 'Visites autorisées (maximum 2 personnes par lit simultanément).' },
        { time: '19:30 – 20:30', title: 'Collation & Dîner du Soir', desc: 'Dîner léger et préparation au repos nocturne.' },
        { time: '21:00 – 07:00', title: 'Heures Calmes & Nuitée', desc: 'Éclairage tamisé, repos des patients et permanence soignante.' }
      ]
    },
    postcard: {
      btnOpen: 'Envoyer un Mot Doux au Lit B06 💌',
      modalTitle: 'Envoyer une Carte d\'Encouragement',
      modalSubtitle: 'Votre message sera affiché sur la tablette de soins lors de la prochaine tournée de confort.',
      senderLabel: 'Votre Prénom & Lien familial',
      senderPlaceholder: 'Ex: Amina (Fille)',
      messageLabel: 'Votre Message',
      messagePlaceholder: 'Écrivez un message d\'amour et de réconfort...',
      quickTemplates: [
        'On pense fort à toi Papa ❤️',
        'Que Dieu te donne la santé et la force 🤲',
        'Les petits-enfants t\'embrassent très fort 🌸',
        'Repose-toi bien, on arrive aux heures de visite ☕'
      ],
      previewTitle: 'Aperçu de la Carte Chevet',
      sendBtn: 'Transmettre au Chevet',
      sending: 'Envoi en cours...',
      successMsg: '✓ Carte transmise avec succès ! Elle sera lue/présentée au chevet par l\'équipe.',
      sentBadge: 'Carte transmise au lit B06'
    },
    gratitude: {
      title: 'Remerciements à l\'Équipe Soignante',
      subtitle: 'Envoyez un geste de reconnaissance aux infirmiers et aides-soignants du service W1.',
      countLabel: 'cœurs envoyés par les familles aujourd\'hui',
      sendHeart: 'Envoyer de la Force ❤️',
      sentToast: 'Merci ! Votre message de gratitude a été transmis au poste infirmier.',
      badges: [
        { id: 'kind', label: '🌸 Douceur & Écoute' },
        { id: 'attentive', label: '⚡ Présence Attentive' },
        { id: 'reassuring', label: '🛡️ Réconfort & Patience' }
      ]
    },
    feed: {
      title: 'Journal de Soins & Confort',
      refreshBtn: 'Actualiser',
      lastChecked: 'Mis à jour à l\'instant',
      emptyTitle: 'Aucune mise à jour pour l\'instant',
      emptyDesc: 'L\'équipe soignante publiera des nouvelles rassurantes après les tournées de soins.',
      kinds: {
        visiting_info: 'Horaires & Consignes de Visite',
        meal_served: 'Service des Repas & Nutrition',
        medication_round_completed: 'Étape de Soins Régulière Effectuée',
        nurse_note: 'Message de l\'Équipe Soignante',
        ward_contact: 'Coordonnées de l\'Unité'
      },
      privacyAssurance: 'Protection des Données : Connexion chiffrée autorisée sous protocole hospitalier (Loi tunisienne 2004-63). Les données médicales cliniques restent strictement confidentielles.'
    }
  },
  en: {
    app: {
      title: 'PiCare Family Care Link',
      subtitle: 'Reassurance & Care Updates for Loved Ones',
      welcome: 'Welcome to your patient care window',
      hospitalName: 'Tunisian Public Hospital — Ward W1',
      patientTag: 'Patient: Bed B06'
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
      demoHint: 'For demonstration, enter code: FAM-9921 or CARE2026',
      invalidCode: 'Invalid or expired code. Please verify with the ward nursing team.'
    },
    milestones: {
      title: 'Hospital Care Journey',
      subtitle: 'Progress milestones towards a safe return home',
      step1: 'Admission & Settling In',
      step1Desc: 'Comfortable installation in Bed B06 completed',
      step2: 'Active Care & Monitoring',
      step2Desc: 'Regular nurse presence & bedside rest',
      step3: 'Mobility & Nutrition',
      step3Desc: 'Progressive return to movement & nutrition',
      step4: 'Discharge Preparation',
      step4Desc: 'Planning the safe transition home',
      activeStatus: 'Current Stage: Patient resting comfortably under regular scheduled nursing rounds.'
    },
    rhythm: {
      title: 'Today\'s Ward Rhythm',
      subtitle: 'Routine cadence and schedule inside Ward W1',
      activeBadge: 'Active Now',
      upcomingBadge: 'Upcoming',
      passedBadge: 'Completed',
      slots: [
        { time: '07:30 – 09:00', title: 'Morning Care & Breakfast', desc: 'Hygiene care, routine comfort, and balanced breakfast served.' },
        { time: '10:00 – 12:00', title: 'Medical Team Bedside Rounds', desc: 'Attending physicians clinical review and bedside visits.' },
        { time: '12:30 – 13:30', title: 'Prescribed Dietary Lunch', desc: 'Warm meal served according to personalized nutritional plan.' },
        { time: '14:00 – 18:00', title: 'Open Visiting Hours', desc: 'Visitors welcomed (maximum 2 visitors per bedside simultaneously).' },
        { time: '19:30 – 20:30', title: 'Evening Dinner & Teatime', desc: 'Light evening meal and settling down for the night.' },
        { time: '21:00 – 07:00', title: 'Quiet Hours & Night Rest', desc: 'Dimmed lights, restorative rest with 24/7 on-call nurse coverage.' }
      ]
    },
    postcard: {
      btnOpen: 'Send a Warm Note to Bed B06 💌',
      modalTitle: 'Send Bedside Postcard',
      modalSubtitle: 'Your message will appear on the ward tablet for the next comfort round.',
      senderLabel: 'Your Name & Relation',
      senderPlaceholder: 'e.g. Amina (Daughter)',
      messageLabel: 'Your Encouragement Note',
      messagePlaceholder: 'Write a warm note of love and strength...',
      quickTemplates: [
        'Thinking of you so much Baba ❤️',
        'Wishing you health and strength 🤲',
        'The grandchildren send big hugs and kisses 🌸',
        'Rest well, we will visit during open hours ☕'
      ],
      previewTitle: 'Bedside Postcard Preview',
      sendBtn: 'Send to Patient Nightstand',
      sending: 'Sending...',
      successMsg: '✓ Note delivered! It will be shown to the patient by the care team.',
      sentBadge: 'Delivered to Bed B06'
    },
    gratitude: {
      title: 'Care Team Appreciation Jar',
      subtitle: 'Send a gesture of gratitude to the nurses and care assistants of Ward W1.',
      countLabel: 'hearts sent by relatives today',
      sendHeart: 'Send Appreciation ❤️',
      sentToast: 'Thank you! Your gratitude has been displayed on the nurse station board.',
      badges: [
        { id: 'kind', label: '🌸 Gentle & Caring' },
        { id: 'attentive', label: '⚡ Always Attentive' },
        { id: 'reassuring', label: '🛡️ Patient & Reassuring' }
      ]
    },
    feed: {
      title: 'Daily Care & Comfort Timeline',
      refreshBtn: 'Refresh',
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
      privacyAssurance: 'Data Protection: This connection is encrypted and authorized under hospital consent protocols (Tunisian Law 2004-63). Clinical telemetry is strictly reserved for the attending medical team.'
    }
  }
};

export const STRINGS = DICTIONARY.fr; // Default
