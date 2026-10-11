import React, { useState } from 'react';
import { Heart, Sparkles } from 'lucide-react';
import { DICTIONARY, Language } from '../i18n/strings';

interface CareTeamGratitudeProps {
  lang: Language;
}

export const CareTeamGratitude: React.FC<CareTeamGratitudeProps> = ({ lang }) => {
  const [heartsCount, setHeartsCount] = useState<number>(() => {
    try {
      const stored = localStorage.getItem('borj_family_hearts_count');
      return stored ? parseInt(stored, 10) : 24;
    } catch {
      return 24;
    }
  });

  const [selectedBadge, setSelectedBadge] = useState<string | null>(null);
  const [justSent, setJustSent] = useState<boolean>(false);

  const t = DICTIONARY[lang].gratitude;

  const handleSendHeart = (badgeId?: string) => {
    const nextCount = heartsCount + 1;
    setHeartsCount(nextCount);
    if (badgeId) setSelectedBadge(badgeId);
    try {
      localStorage.setItem('borj_family_hearts_count', nextCount.toString());
    } catch {}

    setJustSent(true);
    setTimeout(() => {
      setJustSent(false);
    }, 2500);
  };

  return (
    <div className="gratitude-card">
      <div className="gratitude-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="gratitude-heart-icon">
            <Heart size={20} fill="#e11d48" color="#e11d48" className={justSent ? 'scale-bump' : ''} />
          </div>
          <div>
            <h4>{t.title}</h4>
            <p>{t.subtitle}</p>
          </div>
        </div>

        <div className="hearts-counter-bubble">
          <span className="count-number">{heartsCount}</span>
          <span className="count-text">{t.countLabel}</span>
        </div>
      </div>

      <div className="gratitude-badges-grid">
        {t.badges.map(b => (
          <button
            key={b.id}
            type="button"
            className={`gratitude-badge-pill ${selectedBadge === b.id ? 'active' : ''}`}
            onClick={() => handleSendHeart(b.id)}
          >
            <span>{b.label}</span>
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
        <button
          className="btn-send-heart"
          onClick={() => handleSendHeart()}
          id="btn-send-gratitude-heart"
        >
          <Heart size={16} fill="white" />
          <span>{t.sendHeart}</span>
          <Sparkles size={14} />
        </button>

        {justSent && (
          <div className="gratitude-toast animate-fade-in">
            ✓ {t.sentToast}
          </div>
        )}
      </div>
    </div>
  );
};
