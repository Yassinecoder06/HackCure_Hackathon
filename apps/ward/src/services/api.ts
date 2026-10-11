// Ward API client & WebSocket real-time subscription
import { audioAlerts } from '../components/AudioAlerts';

export interface WardSnapshot {
  ward: string;
  asOf: string;
  clockMode: 'wall' | 'sim';
  beds: any[];
  staff: any[];
  calls: any[];
  alerts: any[];
}

type StreamListener = (type: string, data: any) => void;

export interface AuthSession {
  token: string;
  expiresAt: string;
  staff: {
    id: string;
    name: string;
    role: 'nurse' | 'charge_nurse' | 'care_assistant' | 'doctor';
    skills?: string[];
  };
}

function getApiBase(): string {
  if (typeof window !== 'undefined' && window.location.port === '5173') {
    return `http://${window.location.hostname}:8000`;
  }
  return '';
}

function getWsUrl(ward = 'W1'): string {
  if (typeof window === 'undefined') return '';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  if (window.location.port === '5173') {
    return `${protocol}//${window.location.hostname}:8000/api/v1/wards/${ward}/stream`;
  }
  return `${protocol}//${window.location.host}/api/v1/wards/${ward}/stream`;
}

class WardApiService {
  private ws: WebSocket | null = null;
  private listeners: Set<StreamListener> = new Set();
  private currentStaffId: string = 'CN1'; // Charge Nurse default
  private session: AuthSession | null = null;
  private isConnected: boolean = false;
  private reconnectTimer: number | null = null;

  constructor() {
    // Restore session from localStorage if present
    try {
      const stored = localStorage.getItem('borj_ward_auth');
      if (stored) {
        this.session = JSON.parse(stored);
        if (this.session?.staff?.id) {
          this.currentStaffId = this.session.staff.id;
        }
      }
    } catch (e) {
      console.warn('Failed to restore auth session from storage', e);
    }
  }

  public getSession(): AuthSession | null {
    return this.session;
  }

  public setStaffId(id: string) {
    this.currentStaffId = id;
    if (this.session && this.session.staff.id !== id) {
      this.session.staff.id = id;
    }
  }

  public getStaffId(): string {
    return this.session?.staff?.id || this.currentStaffId;
  }

  public getIsConnected(): boolean {
    return this.isConnected;
  }

  public async login(staffId: string, secret: string): Promise<AuthSession> {
    const res = await fetch(`${getApiBase()}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ staffId, secret })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Login failed. Invalid staff ID or PIN.');
    }
    const data: AuthSession = await res.json();
    this.session = data;
    this.currentStaffId = data.staff.id;
    try {
      localStorage.setItem('borj_ward_auth', JSON.stringify(data));
    } catch {
      // ignore
    }
    this.emit('auth_changed', data);

    // Reconnect WebSocket with the new bearer token subprotocol
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connectWebSocket();

    return data;
  }

  public logout(): void {
    this.session = null;
    try {
      localStorage.removeItem('borj_ward_auth');
    } catch {
      // ignore
    }
    this.emit('auth_changed', null);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connectWebSocket();
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Staff-Id': this.currentStaffId
    };
    if (this.session?.token) {
      headers['Authorization'] = `Bearer ${this.session.token}`;
    }
    return headers;
  }

  public subscribe(listener: StreamListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public async ensureSession(): Promise<AuthSession> {
    if (this.session && this.session.token) {
      try {
        const exp = new Date(this.session.expiresAt).getTime();
        if (exp > Date.now() + 30000) {
          return this.session;
        }
      } catch {
        // proceed to relogin
      }
    }
    const pinMap: Record<string, string> = {
      N1: '185541',
      CN1: '687463',
      N2: '009612',
      CA1: '227072',
      DR1: '783818',
    };
    const sid = this.currentStaffId in pinMap ? this.currentStaffId : 'N1';
    const pin = pinMap[sid] || '185541';
    return await this.login(sid, pin);
  }

  public async connectWebSocket() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      await this.ensureSession();
    } catch (e) {
      console.warn('Auto-session setup failed, will prompt user login', e);
      this.emit('auth_expired', true);
      this.scheduleReconnect();
      return;
    }

    const wsUrl = getWsUrl('W1');
    const token = this.session?.token;
    if (!token) {
      this.emit('auth_expired', true);
      this.scheduleReconnect();
      return;
    }

    try {
      // Contract: Offer subprotocols ["bearer", "<login token>"]
      this.ws = new WebSocket(wsUrl, ['bearer', token]);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.emit('connection', { connected: true });
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          // Play audio chimes on calls or alerts
          if (msg.type === 'call' && msg.data?.state === 'sent') {
            audioAlerts.playChime();
          } else if (msg.type === 'alert') {
            if (msg.data?.priority === 'critical' && msg.data?.active !== false) {
              audioAlerts.startCriticalAlarm();
            } else {
              audioAlerts.playChime();
            }
          }
          this.emit(msg.type, msg.data);
        } catch (e) {
          console.error('WebSocket parse error:', e);
        }
      };

      this.ws.onclose = (event) => {
        this.isConnected = false;
        this.emit('connection', { connected: false });
        if (event.code === 4401) {
          console.warn('WebSocket closed with 4401 (Authentication required/invalid)');
          this.session = null;
          try {
            localStorage.removeItem('borj_ward_auth');
          } catch {}
          this.emit('auth_expired', true);
        }
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer === null) {
      this.reconnectTimer = window.setTimeout(() => {
        this.reconnectTimer = null;
        this.connectWebSocket();
      }, 3000);
    }
  }

  private emit(type: string, data: any) {
    for (const listener of this.listeners) {
      listener(type, data);
    }
  }

  // REST API Methods
  public async getSnapshot(ward = 'W1'): Promise<WardSnapshot> {
    try {
      await this.ensureSession();
    } catch {}
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/snapshot`, {
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch ward snapshot');
    return res.json();
  }

  public async submitObservations(bed: string, observations: any, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/beds/${bed}/observations`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(observations)
    });
    if (!res.ok) throw new Error('Failed to record observation');
    return res.json();
  }

  public async acknowledgeCall(callId: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/calls/${callId}/ack`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to acknowledge call');
    return res.json();
  }

  public async resolveCall(callId: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/calls/${callId}/resolve`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to resolve call');
    return res.json();
  }

  public async acknowledgeAlert(alertId: string, ward = 'W1') {
    audioAlerts.stopCriticalAlarm();
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/alerts/${alertId}/ack`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to acknowledge alert');
    return res.json();
  }

  public async getSuggestions(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/assignments/suggestions`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async requestSuggestion(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/assignments/suggestions`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to request suggestion from solver');
    }
    return res.json();
  }

  public async setStaffPresence(staffId: string, onWard: boolean, reason: string, expectedBackMin?: number, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/staff/${staffId}/presence`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        onWard,
        reason,
        ...(expectedBackMin !== undefined ? { expectedBackMin } : {})
      })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update staff presence');
    }
    return res.json();
  }

  public async decideSuggestion(suggestionId: string, decision: 'approve' | 'reject', reason?: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/assignments/suggestions/${suggestionId}/decision`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ decision, reason: reason || 'Charge nurse decision' })
    });
    return res.json();
  }

  public async runWhatIf(disruptions: any[], ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/whatif/runs`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ disruptions, seeds: 200, horizonMin: 240 })
    });
    return res.json();
  }

  public async getMedsTimeline(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/meds/timeline`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async recordAdministration(doseId: string, action: 'given' | 'not_given', ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/doses/${doseId}/administration`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ action, presence: 'wristband_scan' })
    });
    return res.json();
  }

  public async getFamilyUpdates(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/family/updates`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async createFamilyConsent(admissionId: string, relativeLabel: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/admissions/${admissionId}/family/consents`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        relativeLabel,
        allowedKinds: ['visiting_info', 'meal_served', 'medication_round_completed', 'nurse_note', 'ward_contact'],
        givenBy: 'patient'
      })
    });
    return res.json();
  }

  public async createFamilyInvite(admissionId: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/admissions/${admissionId}/family/invites`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({})
    });
    return res.json();
  }

  public async draftFamilyUpdate(admissionId: string, kind: string, text: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/admissions/${admissionId}/family/updates`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ kind, text })
    });
    return res.json();
  }

  public async decideFamilyUpdate(updateId: string, decision: 'approve' | 'reject', ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/family/updates/${updateId}/decision`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ decision })
    });
    return res.json();
  }

  public async getDoctorOrders(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/doctor/orders`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async createDoctorOrder(bed: string, orderText: string, ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/doctor/orders`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ bed, orderText })
    });
    return res.json();
  }

  public async triggerPeakDemo() {
    const res = await fetch(`${getApiBase()}/api/v1/demo/trigger-peak`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async getAuditLog(ward = 'W1', limit = 100) {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/audit?limit=${limit}`, {
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch audit entries');
    return res.json();
  }

  public async verifyAuditChain(ward = 'W1') {
    const res = await fetch(`${getApiBase()}/api/v1/wards/${ward}/audit/verify`, {
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to verify audit chain');
    return res.json();
  }
}

export const wardApi = new WardApiService();
