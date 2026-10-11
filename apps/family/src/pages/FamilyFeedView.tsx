import React, { useState, useEffect } from 'react';
import { DICTIONARY, Language } from '../i18n/strings';
import { familyApi, FamilyFeedResponse } from '../services/familyApi';
import { RecoveryMilestones } from '../components/RecoveryMilestones';
import { WardRhythmSchedule } from '../components/WardRhythmSchedule';
import { BedsidePostcardModal } from '../components/BedsidePostcardModal';
import { CareTeamGratitude } from '../components/CareTeamGratitude';
import {
  PhoneCall,
  Clock,
  Utensils,
  CheckCircle2,
  MessageSquareHeart,
  Info,
  RotateCw,
  LogOut,
  ShieldCheck,
  AlertOctagon,
  CalendarCheck
} from 'lucide-react';

interface FamilyFeedViewProps {
  lang: Language;
  onLogout: () => void;
}

export const FamilyFeedView: React.FC<FamilyFeedViewProps> = ({ lang, onLogout }) => {
  const [feedData, setFeedData] = useState<FamilyFeedResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const t = DICTIONARY[lang];

  const fetchFeed = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await familyApi.getFeed();
      setFeedData(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFeed();
  }, []);

  const getKindIcon = (kind: string) => {
    switch (kind) {
      case 'visiting_info':
        return <Clock size={16} />;
      case 'meal_served':
        return <Utensils size={16} />;
      case 'medication_round_completed':
        return <CheckCircle2 size={16} />;
      case 'nurse_note':
        return <MessageSquareHeart size={16} />;
      default:
        return <Info size={16} />;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: '1.25rem', paddingBottom: '2rem' }}>
      {/* 1. Prominent Emergency Safety Warning Banner (Mandatory Safety Invariant) */}
      <div className="emergency-banner">
        <div className="emergency-tag">
          <AlertOctagon size={16} />
          <span>{t.emergency.badge}</span>
        </div>
        <p className="emergency-text">
          {feedData?.notice || t.emergency.notice}
        </p>
        <a
          href={`tel:${feedData?.wardContact || t.emergency.phone}`}
          className="emergency-phone-btn"
          id="btn-emergency-call"
        >
          <PhoneCall size={16} />
          <span>{t.emergency.callNow}: {feedData?.wardContact || t.emergency.phone}</span>
        </a>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '0 1.25rem' }}>
        {/* 2. Recovery Milestones (Discharge Readiness Stepper) */}
        <RecoveryMilestones lang={lang} />

        {/* 3. Today's Ward Rhythm (Real-Time Live Schedule) */}
        <WardRhythmSchedule lang={lang} />

        {/* 4. Bedside Postcard (Send Encouragement Message to Bed B06) */}
        <BedsidePostcardModal lang={lang} />

        {/* 5. Main Timeline Feed */}
        <div className="feed-box-container">
          <div className="feed-title-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CalendarCheck size={18} color="var(--primary-teal)" />
              <h3>{t.feed.title}</h3>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={fetchFeed}
                className="feed-action-btn"
                title={t.feed.refreshBtn}
                id="btn-refresh-feed"
              >
                <RotateCw size={14} className={loading ? 'animate-spin' : ''} />
                <span>{t.feed.refreshBtn}</span>
              </button>
              <button
                onClick={onLogout}
                className="feed-action-btn"
                title="Disconnect"
                id="btn-logout-family"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>

          {error && (
            <div className="feed-error-box">
              {error}
            </div>
          )}

          {feedData && feedData.updates.length > 0 ? (
            <div className="timeline-list">
              {feedData.updates.map((item, idx) => (
                <div key={idx} className="timeline-card">
                  <div className="timeline-card-header">
                    <span className="kind-badge">
                      {getKindIcon(item.kind)}
                      <span>{(t.feed.kinds as any)[item.kind] || item.kind.replace('_', ' ')}</span>
                    </span>
                    <span className="time-stamp">
                      {new Date(item.publishedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="update-body-text">
                    {item.text || (lang === 'fr' ? 'Nouvelle de routine enregistrée par l\'équipe soignante.' : 'Status update logged by the ward staff.')}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            !loading && (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <p style={{ fontWeight: 600 }}>{t.feed.emptyTitle}</p>
                <p style={{ fontSize: '0.85rem', marginTop: 4 }}>{t.feed.emptyDesc}</p>
              </div>
            )
          )}
        </div>

        {/* 6. Care Team Gratitude (Nurse Appreciation Jar) */}
        <CareTeamGratitude lang={lang} />
      </div>

      {/* 7. Data Protection Footer (Tunisian Law 2004-63) */}
      <footer className="footer-privacy">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 4, fontWeight: 700 }}>
          <ShieldCheck size={16} color="#0d9488" />
          <span>{lang === 'fr' ? 'Protection des Données & Secret Médical' : 'Patient Privacy & Medical Data Protection'}</span>
        </div>
        <p>{t.feed.privacyAssurance}</p>
      </footer>
    </div>
  );
};
