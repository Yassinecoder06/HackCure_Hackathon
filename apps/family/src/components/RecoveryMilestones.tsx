import React from 'react';
import { Check, Activity, Sparkles, Home } from 'lucide-react';
import { DICTIONARY, Language } from '../i18n/strings';

interface RecoveryMilestonesProps {
  lang: Language;
}

export const RecoveryMilestones: React.FC<RecoveryMilestonesProps> = ({ lang }) => {
  const t = DICTIONARY[lang].milestones;

  const steps = [
    {
      num: 1,
      title: t.step1,
      desc: t.step1Desc,
      status: 'completed',
      icon: <Check size={16} strokeWidth={3} />
    },
    {
      num: 2,
      title: t.step2,
      desc: t.step2Desc,
      status: 'active',
      icon: <Activity size={16} className="animate-pulse" />
    },
    {
      num: 3,
      title: t.step3,
      desc: t.step3Desc,
      status: 'upcoming',
      icon: <Sparkles size={16} />
    },
    {
      num: 4,
      title: t.step4,
      desc: t.step4Desc,
      status: 'upcoming',
      icon: <Home size={16} />
    }
  ];

  return (
    <div className="milestones-card">
      <div className="milestones-header">
        <div>
          <h4>{t.title}</h4>
          <p>{t.subtitle}</p>
        </div>
        <span className="step-counter-badge">
          {lang === 'fr' ? 'Étape 2 sur 4' : 'Stage 2 of 4'}
        </span>
      </div>

      <div className="stepper-track">
        {steps.map((st, idx) => (
          <div key={st.num} className={`stepper-step ${st.status}`}>
            <div className="step-node">
              <div className="step-icon-wrap">
                {st.icon}
              </div>
              {idx < steps.length - 1 && <div className={`step-connector ${st.status === 'completed' ? 'done' : ''}`} />}
            </div>
            <div className="step-label-wrap">
              <span className="step-title">{st.title}</span>
              <span className="step-desc">{st.desc}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="milestones-status-banner">
        <span className="live-dot" />
        <span>{t.activeStatus}</span>
      </div>
    </div>
  );
};
