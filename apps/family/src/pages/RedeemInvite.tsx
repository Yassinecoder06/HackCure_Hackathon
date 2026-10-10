import React, { useState } from 'react';
import { STRINGS } from '../i18n/strings';
import { familyApi } from '../services/familyApi';
import { KeyRound, QrCode } from 'lucide-react';

interface RedeemInviteProps {
  onSuccess: () => void;
}

export const RedeemInvite: React.FC<RedeemInviteProps> = ({ onSuccess }) => {
  const [code, setCode] = useState<string>('CARE2026');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await familyApi.redeemInvite(code.trim().toUpperCase());
      onSuccess();
    } catch (err: any) {
      setError(err.message || STRINGS.auth.invalidCode);
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
          <h2>{STRINGS.auth.redeemTitle}</h2>
          <p style={{ marginTop: 6 }}>{STRINGS.auth.redeemDesc}</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input
            type="text"
            className="pin-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder={STRINGS.auth.pinPlaceholder}
            maxLength={10}
            required
            id="input-family-code"
          />

          {error && (
            <div style={{ color: 'var(--emergency-tag)', fontSize: '0.85rem', fontWeight: 600 }}>
              {error}
            </div>
          )}

          <button type="submit" className="btn-redeem" disabled={loading} id="btn-redeem-submit">
            {loading ? 'Verifying Code...' : STRINGS.auth.redeemBtn}
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 8 }}>
          <QrCode size={16} />
          <span>Bedside QR codes automatically pre-fill this access key.</span>
        </div>
      </div>
    </div>
  );
};
