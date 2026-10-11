import React, { useState } from 'react';
import { Clock, Sun, Stethoscope, Utensils, Users, Moon, ChevronDown, ChevronUp } from 'lucide-react';
import { DICTIONARY, Language } from '../i18n/strings';

interface WardRhythmScheduleProps {
  lang: Language;
}

export const WardRhythmSchedule: React.FC<WardRhythmScheduleProps> = ({ lang }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const t = DICTIONARY[lang].rhythm;

  // Determine current active slot based on local hours
  const now = new Date();
  const currentHour = now.getHours();
  const currentMin = now.getMinutes();
  const currentTimeDec = currentHour + currentMin / 60;

  const slotIcons = [
    <Sun size={16} key="sun" />,
    <Stethoscope size={16} key="steth" />,
    <Utensils size={16} key="utensils" />,
    <Users size={16} key="users" />,
    <Utensils size={16} key="dinner" />,
    <Moon size={16} key="moon" />
  ];

  const slotRanges = [
    { start: 7.5, end: 9.0 },
    { start: 10.0, end: 12.0 },
    { start: 12.5, end: 13.5 },
    { start: 14.0, end: 18.0 },
    { start: 19.5, end: 20.5 },
    { start: 21.0, end: 31.0 } // overnight
  ];

  const getSlotState = (idx: number) => {
    const range = slotRanges[idx];
    if (range.start === 21.0) {
      if (currentTimeDec >= 21.0 || currentTimeDec < 7.0) return 'active';
      return currentTimeDec >= 7.0 ? 'passed' : 'upcoming';
    }
    if (currentTimeDec >= range.start && currentTimeDec < range.end) return 'active';
    if (currentTimeDec >= range.end) return 'passed';
    return 'upcoming';
  };

  // Find active slot
  const activeIdx = t.slots.findIndex((_, idx) => getSlotState(idx) === 'active');
  const highlightedIdx = activeIdx >= 0 ? activeIdx : 3; // fallback to visiting hours

  return (
    <div className="rhythm-card">
      <div className="rhythm-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="rhythm-icon-wrap">
            <Clock size={18} />
          </div>
          <div>
            <h4>{t.title}</h4>
            <p>{t.subtitle}</p>
          </div>
        </div>

        <button
          className="rhythm-expand-btn"
          onClick={() => setExpanded(!expanded)}
          title={expanded ? 'Collapse' : 'View all'}
        >
          <span>{expanded ? (lang === 'fr' ? 'Réduire' : 'Collapse') : (lang === 'fr' ? 'Voir Tout' : 'View All')}</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Active Spotlight Card */}
      <div className="active-slot-spotlight">
        <div className="spotlight-top">
          <span className="live-status-pill">
            <span className="live-pulse" />
            {t.activeBadge}
          </span>
          <span className="spotlight-time">{t.slots[highlightedIdx].time}</span>
        </div>
        <div className="spotlight-body">
          <div className="spotlight-icon">{slotIcons[highlightedIdx]}</div>
          <div>
            <div className="spotlight-title">{t.slots[highlightedIdx].title}</div>
            <div className="spotlight-desc">{t.slots[highlightedIdx].desc}</div>
          </div>
        </div>
      </div>

      {/* Expanded Timeline View */}
      {expanded && (
        <div className="rhythm-timeline-list">
          {t.slots.map((slot, idx) => {
            const state = getSlotState(idx);
            return (
              <div key={idx} className={`rhythm-item ${state}`}>
                <div className="rhythm-time-col">
                  <span className="rhythm-time-text">{slot.time}</span>
                  <span className={`rhythm-state-badge ${state}`}>
                    {state === 'active' ? t.activeBadge : state === 'passed' ? t.passedBadge : t.upcomingBadge}
                  </span>
                </div>
                <div className="rhythm-desc-col">
                  <div className="rhythm-item-title">
                    <span className="rhythm-item-icon">{slotIcons[idx]}</span>
                    <span>{slot.title}</span>
                  </div>
                  <div className="rhythm-item-desc">{slot.desc}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
