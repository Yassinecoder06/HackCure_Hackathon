import React, { useState } from 'react';
import { wardApi } from '../services/api';
import { Lock, Shield, UserCheck, AlertTriangle, KeyRound, CheckCircle2, X, Check } from 'lucide-react';

interface LoginModalProps {
  isOpen: boolean;
  onClose?: () => void;
  onSuccess: () => void;
}

const PRESET_STAFF = [
  {
    id: 'N1',
    name: 'Nurse B',
    role: 'nurse',
    pin: '185541',
    badge: 'Nurse (IV)',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)'
  },
  {
    id: 'CN1',
    name: 'Charge Nurse A',
    role: 'charge_nurse',
    pin: '687463',
    badge: 'Charge Nurse',
    color: '#0284c7',
    bg: 'rgba(2, 132, 199, 0.12)'
  },
  {
    id: 'N2',
    name: 'Nurse C',
    role: 'nurse',
    pin: '009612',
    badge: 'Nurse (Resp/IV)',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)'
  },
  {
    id: 'CA1',
    name: 'Care Assistant E',
    role: 'care_assistant',
    pin: '227072',
    badge: 'Care Assistant',
    color: '#d97706',
    bg: 'rgba(217, 119, 6, 0.12)'
  },
  {
    id: 'DR1',
    name: 'Doctor F',
    role: 'doctor',
    pin: '783818',
    badge: 'On-Call Doctor',
    color: '#7c3aed',
    bg: 'rgba(124, 58, 237, 0.12)'
  }
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
    <div className="modal-backdrop" style={{ zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div
        className="modal-card"
        style={{
          maxWidth: 500,
          width: '100%',
          borderRadius: 16,
          background: 'var(--bg-card, #ffffff)',
          border: '1px solid var(--border-subtle, #cbd5e1)',
          boxShadow: '0 20px 45px -10px rgba(0, 0, 0, 0.25)',
          overflow: 'hidden',
          padding: '1.75rem'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '1.25rem', borderBottom: '1px solid var(--border-subtle, #e2e8f0)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              background: 'rgba(2, 132, 199, 0.12)',
              border: '1px solid rgba(2, 132, 199, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#0284c7'
            }}>
              <Shield size={24} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main, #0f172a)' }}>
                Clinical Staff Authentication
              </h3>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.78rem', color: 'var(--text-muted, #64748b)' }}>
                Safety Invariant 11 & ADR 0010 • Audited Bearer Token
              </p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: 'var(--bg-surface, rgba(0,0,0,0.05))',
                border: '1px solid var(--border-subtle, transparent)',
                borderRadius: '50%',
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted, #64748b)',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
              title="Close"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Modal Body */}
        <div style={{ paddingTop: '1.25rem' }}>
          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#dc2626',
              padding: '0.75rem 1rem',
              borderRadius: 10,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: '1.25rem'
            }}>
              <AlertTriangle size={18} style={{ flexShrink: 0 }} />
              <span style={{ fontWeight: 500 }}>{error}</span>
            </div>
          )}

          {/* Quick Demo Staff Selection */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
              <label style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-muted, #64748b)', fontWeight: 700, letterSpacing: '0.05em' }}>
                Quick Demo Staff Selection
              </label>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #94a3b8)' }}>
                Click to load credentials
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
              {PRESET_STAFF.map(p => {
                const isSelected = staffId === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSelectPreset(p)}
                    style={{
                      background: isSelected ? 'rgba(2, 132, 199, 0.08)' : 'var(--bg-surface, #f8fafc)',
                      border: isSelected ? `2px solid ${p.color}` : '1px solid var(--border-subtle, #e2e8f0)',
                      borderRadius: 10,
                      padding: '0.65rem 0.85rem',
                      textAlign: 'left',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      transition: 'all 0.18s ease',
                      position: 'relative',
                      boxShadow: isSelected ? `0 4px 12px ${p.color}22` : '0 1px 3px rgba(0,0,0,0.03)'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: '0.92rem', fontWeight: 800, color: 'var(--text-main, #0f172a)' }}>
                          {p.id}
                        </span>
                        {isSelected && (
                          <span style={{
                            width: 16,
                            height: 16,
                            borderRadius: '50%',
                            background: p.color,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#ffffff'
                          }}>
                            <Check size={11} strokeWidth={3} />
                          </span>
                        )}
                      </div>
                      <span style={{
                        fontSize: '0.68rem',
                        padding: '2px 7px',
                        borderRadius: 6,
                        background: p.bg,
                        color: p.color,
                        fontWeight: 700,
                        border: `1px solid ${p.color}33`
                      }}>
                        {p.badge}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #64748b)', fontWeight: 500 }}>
                      {p.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-main, #0f172a)', marginBottom: 6, fontWeight: 600 }}>
                Staff Identifier
              </label>
              <div style={{ position: 'relative' }}>
                <UserCheck size={18} style={{ position: 'absolute', left: 12, top: 12, color: 'var(--text-muted, #64748b)' }} />
                <input
                  type="text"
                  value={staffId}
                  onChange={(e) => setStaffId(e.target.value)}
                  placeholder="e.g. CN1, N1, DR1"
                  style={{
                    width: '100%',
                    padding: '0.7rem 0.85rem 0.7rem 2.5rem',
                    background: 'var(--bg-surface, #f8fafc)',
                    border: '1px solid var(--border-subtle, #cbd5e1)',
                    borderRadius: 10,
                    color: 'var(--text-main, #0f172a)',
                    fontSize: '0.92rem',
                    fontWeight: 600,
                    boxSizing: 'border-box',
                    outline: 'none',
                    transition: 'border-color 0.15s ease'
                  }}
                  required
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-main, #0f172a)', marginBottom: 6, fontWeight: 600 }}>
                Argon2id Staff PIN
              </label>
              <div style={{ position: 'relative' }}>
                <KeyRound size={18} style={{ position: 'absolute', left: 12, top: 12, color: 'var(--text-muted, #64748b)' }} />
                <input
                  type="password"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="Enter 4-6 digit clinical PIN"
                  style={{
                    width: '100%',
                    padding: '0.7rem 0.85rem 0.7rem 2.5rem',
                    background: 'var(--bg-surface, #f8fafc)',
                    border: '1px solid var(--border-subtle, #cbd5e1)',
                    borderRadius: 10,
                    color: 'var(--text-main, #0f172a)',
                    fontSize: '0.92rem',
                    boxSizing: 'border-box',
                    outline: 'none',
                    letterSpacing: '0.15em',
                    transition: 'border-color 0.15s ease'
                  }}
                  required
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  style={{
                    flex: 1,
                    padding: '0.75rem 1rem',
                    background: 'var(--bg-surface, #f1f5f9)',
                    border: '1px solid var(--border-subtle, #cbd5e1)',
                    borderRadius: 10,
                    color: 'var(--text-muted, #475569)',
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
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
                  padding: '0.75rem 1.25rem',
                  background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                  border: 'none',
                  borderRadius: 10,
                  color: '#ffffff',
                  fontSize: '0.9rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  boxShadow: '0 4px 14px rgba(2, 132, 199, 0.35)',
                  transition: 'all 0.15s ease'
                }}
              >
                {loading ? (
                  <span>Authenticating...</span>
                ) : (
                  <>
                    <Lock size={17} />
                    <span>Sign In & Verify Token</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Security Guarantee Footnote */}
          <div style={{
            marginTop: '1.4rem',
            padding: '0.65rem 0.85rem',
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.22)',
            borderRadius: 8,
            fontSize: '0.74rem',
            color: 'var(--text-muted, #475569)',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            <CheckCircle2 size={15} color="#10b981" style={{ flexShrink: 0 }} />
            <span>Tokens are signed with HS256 & bound to WebSocket subprotocol <code style={{ color: '#059669', fontWeight: 600 }}>["bearer", token]</code></span>
          </div>
        </div>
      </div>
    </div>
  );
};
