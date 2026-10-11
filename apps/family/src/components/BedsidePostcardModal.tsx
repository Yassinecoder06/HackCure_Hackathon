import React, { useState } from 'react';
import { Heart, Send, Sparkles, X, CheckCircle, Mail } from 'lucide-react';
import { DICTIONARY, Language } from '../i18n/strings';

interface BedsidePostcardModalProps {
  lang: Language;
}

interface SavedPostcard {
  id: string;
  sender: string;
  message: string;
  sentAt: string;
}

export const BedsidePostcardModal: React.FC<BedsidePostcardModalProps> = ({ lang }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [sender, setSender] = useState<string>('');
  const [message, setMessage] = useState<string>('');
  const [sending, setSending] = useState<boolean>(false);
  const [sentSuccess, setSentSuccess] = useState<boolean>(false);

  const [postcards, setPostcards] = useState<SavedPostcard[]>(() => {
    try {
      const saved = localStorage.getItem('borj_family_postcards');
      return saved ? JSON.parse(saved) : [
        {
          id: 'card-default',
          sender: 'Amina (Fille / Daughter)',
          message: 'On pense fort à toi Baba ❤️ Repose-toi bien ! Les enfants t\'embrassent fort.',
          sentAt: new Date(Date.now() - 3600000 * 3).toISOString()
        }
      ];
    } catch {
      return [];
    }
  });

  const t = DICTIONARY[lang].postcard;

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    setSending(true);
    setTimeout(() => {
      const newCard: SavedPostcard = {
        id: `card-${Date.now()}`,
        sender: sender.trim() || (lang === 'fr' ? 'Famille Proche' : 'Close Relative'),
        message: message.trim(),
        sentAt: new Date().toISOString()
      };

      const updated = [newCard, ...postcards];
      setPostcards(updated);
      try {
        localStorage.setItem('borj_family_postcards', JSON.stringify(updated));
      } catch {}

      setSending(false);
      setSentSuccess(true);
      setTimeout(() => {
        setSentSuccess(false);
        setIsOpen(false);
        setMessage('');
      }, 1800);
    }, 600);
  };

  const addSticker = (sticker: string) => {
    setMessage(prev => prev + ' ' + sticker);
  };

  return (
    <div className="postcard-section">
      <button
        className="postcard-trigger-btn"
        onClick={() => setIsOpen(true)}
        id="btn-open-postcard"
      >
        <Mail size={18} />
        <span>{t.btnOpen}</span>
        <Sparkles size={16} />
      </button>

      {/* List of Sent Postcards */}
      {postcards.length > 0 && (
        <div className="sent-postcards-carousel">
          <div className="sent-cards-header">
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '0.85rem' }}>
              <Heart size={14} color="#e11d48" fill="#e11d48" />
              {lang === 'fr' ? 'Mots Doux Transmis au Chevet' : 'Notes Delivered to Bedside'}
            </span>
            <span className="sent-count-pill">{postcards.length}</span>
          </div>

          <div className="cards-slider">
            {postcards.map(card => (
              <div key={card.id} className="postcard-display-card">
                <div className="postcard-top-meta">
                  <span className="postcard-sender">{card.sender}</span>
                  <span className="postcard-badge-sent">✓ {t.sentBadge}</span>
                </div>
                <p className="postcard-text">"{card.message}"</p>
                <span className="postcard-time">
                  {new Date(card.sentAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Composer Modal */}
      {isOpen && (
        <div className="modal-overlay" onClick={() => setIsOpen(false)}>
          <div className="modal-card postcard-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="modal-icon-badge">💌</div>
                <div>
                  <h3>{t.modalTitle}</h3>
                  <p>{t.modalSubtitle}</p>
                </div>
              </div>
              <button className="modal-close-btn" onClick={() => setIsOpen(false)}>
                <X size={20} />
              </button>
            </div>

            {sentSuccess ? (
              <div className="postcard-success-banner">
                <CheckCircle size={42} color="#10b981" />
                <h4>{t.successMsg}</h4>
              </div>
            ) : (
              <form onSubmit={handleSend} className="postcard-form">
                <div className="form-group">
                  <label>{t.senderLabel}</label>
                  <input
                    type="text"
                    value={sender}
                    onChange={e => setSender(e.target.value)}
                    placeholder={t.senderPlaceholder}
                    className="postcard-input"
                  />
                </div>

                <div className="form-group">
                  <label>{t.messageLabel}</label>
                  <textarea
                    value={message}
                    onChange={e => setMessage(e.target.value)}
                    placeholder={t.messagePlaceholder}
                    rows={3}
                    required
                    className="postcard-textarea"
                  />
                </div>

                {/* Emoji Stickers Bar */}
                <div className="stickers-bar">
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                    {lang === 'fr' ? 'Symboles :' : 'Stickers:'}
                  </span>
                  {['❤️', '🌸', '🤲', '☕', '🕊️', '💪', '✨', '💐'].map(emoji => (
                    <button
                      key={emoji}
                      type="button"
                      className="sticker-btn"
                      onClick={() => addSticker(emoji)}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>

                {/* Quick Templates */}
                <div className="templates-group">
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                    {lang === 'fr' ? 'Modèles Rapides :' : 'Quick Presets:'}
                  </span>
                  <div className="templates-pills">
                    {t.quickTemplates.map((tmpl, idx) => (
                      <button
                        key={idx}
                        type="button"
                        className="template-pill"
                        onClick={() => setMessage(tmpl)}
                      >
                        {tmpl}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Live Card Preview */}
                {message.trim() && (
                  <div className="postcard-preview-box">
                    <span className="preview-tag">{t.previewTitle}</span>
                    <div className="preview-inner">
                      <span className="preview-sender">
                        {sender.trim() || (lang === 'fr' ? 'Famille' : 'Family')}
                      </span>
                      <p className="preview-text">"{message}"</p>
                      <span className="preview-dest">📍 Lit B06 · Service W1</span>
                    </div>
                  </div>
                )}

                <button
                  type="submit"
                  className="btn-send-postcard"
                  disabled={sending || !message.trim()}
                  id="btn-submit-postcard"
                >
                  <Send size={16} />
                  <span>{sending ? t.sending : t.sendBtn}</span>
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
