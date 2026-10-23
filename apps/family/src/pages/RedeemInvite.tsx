import React, { useState, useEffect } from 'react';
import { DICTIONARY, Language } from '../i18n/strings';
import { familyApi } from '../services/familyApi';
import { KeyRound, QrCode } from 'lucide-react';

interface RedeemInviteProps {
  lang: Language;
  onSuccess: () => void;
}

export const RedeemInvite: React.FC<RedeemInviteProps> = ({ lang, onSuccess }) => {
  const [code, setCode] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('code') || '';
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const t = DICTIONARY[lang].auth;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryCode = params.get('code');
    if (queryCode) {
      const clean = queryCode.trim().toUpperCase();
      setCode(clean);
      setLoading(true);
      familyApi.redeemInvite(clean)
        .then(() => onSuccess())
        .catch(err => setError(err.message || t.invalidCode))
        .finally(() => setLoading(false));
    }
  }, [onSuccess, t.invalidCode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await familyApi.redeemInvite(code.trim());
      onSuccess();
    } catch (err: any) {
      setError(err.message || t.invalidCode);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="redeem-container">
      <div className="auth-card">
        <div className="auth-icon-wrap">
          <KeyRound size={28} />
        </div>

        <div>
          <h2>{t.redeemTitle}</h2>
          <p style={{ marginTop: 6 }}>{t.redeemDesc}</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input
            type="text"
            className="pin-input"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\s/g, ''))}
            placeholder={t.pinPlaceholder}
            maxLength={12}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            id="input-family-code"
          />

          {error && (
            <div style={{ color: 'var(--emergency-tag)', fontSize: '0.85rem', fontWeight: 600 }}>
              {error}
            </div>
          )}

          <button type="submit" className="btn-redeem" disabled={loading} id="btn-redeem-submit">
            {loading ? (lang === 'fr' ? 'Vérification du code...' : 'Verifying Code...') : t.redeemBtn}
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 8 }}>
          <QrCode size={16} />
          <span>{t.qrHint}</span>
        </div>
      </div>
    </div>
  );
};
