import React, { useState } from 'react';
import { wardApi } from '../services/api';
import { Lock, Shield, UserCheck, AlertTriangle, KeyRound, CheckCircle2, X } from 'lucide-react';

interface LoginModalProps {
  isOpen: boolean;
  onClose?: () => void;
  onSuccess: () => void;
}

const PRESET_STAFF = [
  { id: 'N1', name: 'Nurse B', role: 'nurse', pin: '185541', badge: 'Nurse (IV)', color: '#34d399' },
  { id: 'CN1', name: 'Charge Nurse A', role: 'charge_nurse', pin: '687463', badge: 'Charge Nurse', color: '#38bdf8' },
  { id: 'N2', name: 'Nurse C', role: 'nurse', pin: '009612', badge: 'Nurse (Resp/IV)', color: '#34d399' },
  { id: 'CA1', name: 'Care Assistant E', role: 'care_assistant', pin: '227072', badge: 'Care Assistant', color: '#fbbf24' },
  { id: 'DR1', name: 'Doctor F', role: 'doctor', pin: '783818', badge: 'On-Call Doctor', color: '#a78bfa' }
];

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [staffId, setStaffId] = useState<string>('N1');
  const [pin, setPin] = useState<string>('185541');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleSelectPreset = (preset: typeof PRESET_STAFF[0]) => {
    setStaffId(preset.id);
    setPin(preset.pin);
    setError(null);
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!staffId.trim() || !pin.trim()) {
      setError('Staff ID and PIN are required');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await wardApi.login(staffId.trim(), pin.trim());
      onSuccess();
      onClose?.();
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" style={{ zIndex: 9999 }}>
      <div className="modal-card" style={{ maxWidth: 480, width: '92%' }}>
        <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: 'rgba(56,189,248,0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8'
            }}>
              <Shield size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc' }}>
                Clinical Staff Authentication
              </h3>
              <p style={{ margin: 0, fontSize: '0.75rem', color: '#94a3b8' }}>
                Safety Invariant 11 & ADR 0010: Audited Bearer Token
              </p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
          )}
        </div>

        <div className="modal-body" style={{ padding: '1.25rem 0 0 0' }}>
          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              color: '#f87171',
              padding: '0.65rem 0.85rem',
              borderRadius: 8,
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: '1rem'
            }}>
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.75rem', textTransform: 'uppercase', color: '#94a3b8', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
              Quick Demo Staff Selection
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
              {PRESET_STAFF.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  style={{
                    background: staffId === p.id ? 'rgba(56,189,248,0.15)' : 'rgba(30,41,59,0.7)',
                    border: staffId === p.id ? '1px solid #38bdf8' : '1px solid rgba(148,163,184,0.2)',
                    borderRadius: 8,
                    padding: '0.6rem 0.75rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                    transition: 'all 0.15s ease'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{p.id}</span>
                    <span style={{ fontSize: '0.65rem', padding: '1px 5px', borderRadius: 4, background: 'rgba(0,0,0,0.3)', color: p.color, fontWeight: 600 }}>
                      {p.badge}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{p.name}</span>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: 4, fontWeight: 600 }}>
                Staff Identifier
              </label>
              <div style={{ position: 'relative' }}>
                <UserCheck size={16} style={{ position: 'absolute', left: 12, top: 11, color: '#64748b' }} />
                <input
                  type="text"
                  value={staffId}
                  onChange={(e) => setStaffId(e.target.value)}
                  placeholder="e.g. CN1, N1, DOC1"
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.75rem 0.6rem 2.25rem',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: '0.9rem',
                    boxSizing: 'border-box'
                  }}
                  required
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: 4, fontWeight: 600 }}>
                Argon2id Staff PIN
              </label>
              <div style={{ position: 'relative' }}>
                <KeyRound size={16} style={{ position: 'absolute', left: 12, top: 11, color: '#64748b' }} />
                <input
                  type="password"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="Enter 4-6 digit PIN"
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.75rem 0.6rem 2.25rem',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: '0.9rem',
                    boxSizing: 'border-box'
                  }}
                  required
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  style={{
                    flex: 1,
                    padding: '0.65rem 1rem',
                    background: 'rgba(51, 65, 85, 0.4)',
                    border: '1px solid #475569',
                    borderRadius: 8,
                    color: '#cbd5e1',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
              )}
              <button
                type="submit"
                disabled={loading}
                style={{
                  flex: 2,
                  padding: '0.65rem 1rem',
                  background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                  border: 'none',
                  borderRadius: 8,
                  color: '#ffffff',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  boxShadow: '0 4px 12px rgba(2, 132, 199, 0.35)'
                }}
              >
                {loading ? (
                  <span>Authenticating...</span>
                ) : (
                  <>
                    <Lock size={16} />
                    <span>Sign In & Verify Token</span>
                  </>
                )}
              </button>
            </div>
          </form>

          <div style={{
            marginTop: '1.25rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid rgba(51, 65, 85, 0.5)',
            fontSize: '0.7rem',
            color: '#64748b',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}>
            <CheckCircle2 size={13} color="#10b981" />
            <span>Tokens are signed with HS256 & bound to WebSocket subprotocol ["bearer", token]</span>
          </div>
        </div>
      </div>
    </div>
  );
};
