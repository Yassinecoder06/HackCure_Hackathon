import React, { useState, useEffect } from 'react';
import { STRINGS } from '../i18n/strings';
import { familyApi, FamilyFeedResponse } from '../services/familyApi';
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
  AlertOctagon
} from 'lucide-react';

interface FamilyFeedViewProps {
  onLogout: () => void;
}

export const FamilyFeedView: React.FC<FamilyFeedViewProps> = ({ onLogout }) => {
  const [feedData, setFeedData] = useState<FamilyFeedResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

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
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
      {/* Prominent Emergency Safety Warning Banner (Mandatory Safety Invariant) */}
      <div className="emergency-banner">
        <div className="emergency-tag">
          <AlertOctagon size={16} />
          <span>{STRINGS.emergency.badge}</span>
        </div>
        <p className="emergency-text">
          {feedData?.notice || STRINGS.emergency.notice}
        </p>
        <a
          href={`tel:${feedData?.wardContact || STRINGS.emergency.phone}`}
          className="emergency-phone-btn"
          id="btn-emergency-call"
        >
          <PhoneCall size={16} />
          <span>{STRINGS.emergency.callNow}: {feedData?.wardContact || STRINGS.emergency.phone}</span>
        </a>
      </div>

      {/* Main Timeline Feed */}
      <div className="feed-content">
        <div className="feed-title-bar">
          <h3>{STRINGS.feed.title}</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={fetchFeed}
              style={{
                background: 'transparent',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                padding: '4px 8px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}
              title="Refresh"
              id="btn-refresh-feed"
            >
              <RotateCw size={14} className={loading ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
            <button
              onClick={onLogout}
              style={{
                background: 'transparent',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                padding: '4px 8px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}
              title="Disconnect Session"
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
                    <span>{STRINGS.feed.kinds[item.kind] || item.kind.replace('_', ' ')}</span>
                  </span>
                  <span className="time-stamp">
                    {new Date(item.publishedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className="update-body-text">
                  {item.text || 'Status update logged by the ward staff.'}
                </div>
              </div>
            ))}
          </div>
        ) : (
          !loading && (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <p style={{ fontWeight: 600 }}>{STRINGS.feed.emptyTitle}</p>
              <p style={{ fontSize: '0.85rem', marginTop: 4 }}>{STRINGS.feed.emptyDesc}</p>
            </div>
          )
        )}
      </div>

      {/* Data Protection Footer */}
      <footer className="footer-privacy">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 4, fontWeight: 700 }}>
          <ShieldCheck size={16} color="#0d9488" />
          <span>Patient Privacy Protected</span>
        </div>
        <p>{STRINGS.feed.privacyAssurance}</p>
      </footer>
    </div>
  );
};
