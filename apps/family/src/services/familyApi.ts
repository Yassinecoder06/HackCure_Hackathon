// Family Gateway API Client (Safety Invariants 2 & 3)
// Strictly talks to family-gateway port 8100. Never imports ward contracts or endpoints.

export interface FamilyFeedUpdate {
  kind: 'visiting_info' | 'meal_served' | 'medication_round_completed' | 'nurse_note' | 'ward_contact';
  text?: string;
  publishedAt: string;
}

export interface FamilyFeedResponse {
  notice: string;
  wardContact: string;
  allowedKinds: string[];
  updates: FamilyFeedUpdate[];
}

class FamilyGatewayService {
  private sessionToken: string | null = null;

  constructor() {
    this.sessionToken = localStorage.getItem('borj_family_token');
  }

  public hasSession(): boolean {
    return Boolean(this.sessionToken);
  }

  public clearSession() {
    this.sessionToken = null;
    localStorage.removeItem('borj_family_token');
  }

  public async redeemInvite(code: string): Promise<boolean> {
    const res = await fetch(`http://${window.location.hostname}:8100/family/v1/redeem`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });

    if (!res.ok) {
      throw new Error('Invalid or expired code. Please check with ward staff.');
    }

    const data = await res.json();
    this.sessionToken = data.sessionToken;
    localStorage.setItem('borj_family_token', data.sessionToken);
    return true;
  }

  public async getFeed(): Promise<FamilyFeedResponse> {
    const res = await fetch(`http://${window.location.hostname}:8100/family/v1/feed`, {
      headers: {
        'Authorization': `Bearer ${this.sessionToken || ''}`
      }
    });

    if (!res.ok) {
      if (res.status === 401) {
        this.clearSession();
        throw new Error('Session expired. Please re-enter your invite code.');
      }
      throw new Error('Could not load family updates.');
    }

    return res.json();
  }
}

export const familyApi = new FamilyGatewayService();
