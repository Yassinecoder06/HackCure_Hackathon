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

class WardApiService {
  private ws: WebSocket | null = null;
  private listeners: Set<StreamListener> = new Set();
  private currentStaffId: string = 'CN1'; // Charge Nurse default
  private isConnected: boolean = false;
  private reconnectTimer: number | null = null;

  public setStaffId(id: string) {
    this.currentStaffId = id;
  }

  public getStaffId(): string {
    return this.currentStaffId;
  }

  public getIsConnected(): boolean {
    return this.isConnected;
  }

  private getHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      'X-Staff-Id': this.currentStaffId
    };
  }

  public subscribe(listener: StreamListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public connectWebSocket() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use localhost:8000 if in dev or relative proxy
    const wsUrl = `${protocol}//${window.location.hostname}:8000/api/v1/wards/W1/stream`;

    try {
      this.ws = new WebSocket(wsUrl);

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
            if (msg.data?.priority === 'critical') {
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

      this.ws.onclose = () => {
        this.isConnected = false;
        this.emit('connection', { connected: false });
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
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/snapshot`, {
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch ward snapshot');
    return res.json();
  }

  public async submitObservations(bed: string, observations: any, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/beds/${bed}/observations`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(observations)
    });
    if (!res.ok) throw new Error('Failed to record observation');
    return res.json();
  }

  public async acknowledgeCall(callId: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/calls/${callId}/ack`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to acknowledge call');
    return res.json();
  }

  public async resolveCall(callId: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/calls/${callId}/resolve`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to resolve call');
    return res.json();
  }

  public async acknowledgeAlert(alertId: string, ward = 'W1') {
    audioAlerts.stopCriticalAlarm();
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/alerts/${alertId}/ack`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Failed to acknowledge alert');
    return res.json();
  }

  public async getSuggestions(ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/assignments/suggestions`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async decideSuggestion(suggestionId: string, decision: 'approve' | 'reject', reason?: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/assignments/suggestions/${suggestionId}/decision`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ decision, reason: reason || 'Charge nurse decision' })
    });
    return res.json();
  }

  public async runWhatIf(disruptions: any[], ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/whatif/runs`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ disruptions, seeds: 200, horizonMin: 240 })
    });
    return res.json();
  }

  public async getMedsTimeline(ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/meds/timeline`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async recordAdministration(doseId: string, action: 'given' | 'not_given', ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/doses/${doseId}/administration`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ action, presence: 'wristband_scan' })
    });
    return res.json();
  }

  public async getFamilyUpdates(ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/family/updates`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async createFamilyConsent(admissionId: string, relativeLabel: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/admissions/${admissionId}/family/consents`, {
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
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/admissions/${admissionId}/family/invites`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({})
    });
    return res.json();
  }

  public async draftFamilyUpdate(admissionId: string, kind: string, text: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/admissions/${admissionId}/family/updates`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ kind, text })
    });
    return res.json();
  }

  public async decideFamilyUpdate(updateId: string, decision: 'approve' | 'reject', ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/family/updates/${updateId}/decision`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ decision })
    });
    return res.json();
  }

  public async getDoctorOrders(ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/doctor/orders`, {
      headers: this.getHeaders()
    });
    return res.json();
  }

  public async createDoctorOrder(bed: string, orderText: string, ward = 'W1') {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/wards/${ward}/doctor/orders`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ bed, orderText })
    });
    return res.json();
  }

  public async triggerPeakDemo() {
    const res = await fetch(`http://${window.location.hostname}:8000/api/v1/demo/trigger-peak`, {
      method: 'POST',
      headers: this.getHeaders()
    });
    return res.json();
  }
}

export const wardApi = new WardApiService();
