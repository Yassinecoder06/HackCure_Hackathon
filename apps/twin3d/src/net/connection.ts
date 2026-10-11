import type { StreamMessage } from '../types';

// Login and the live stream. Same contract as the ward app (contracts/openapi.yaml): POST /api/v1/auth/login
// gives a bearer token; the WebSocket offers the subprotocols ["bearer", token] because browsers cannot set
// an Authorization header on a WebSocket and a query-string token would leak into access logs.
export interface Session {
  token: string;
  staffId: string;
  name: string;
  role: string;
}

export type LinkStatus = 'connecting' | 'live' | 'reconnecting' | 'closed';

export async function login(staffId: string, secret: string): Promise<Session> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ staffId, secret }),
  });
  if (!res.ok) throw new Error('login failed');
  const data = await res.json();
  return { token: data.token, staffId: data.staff?.id ?? staffId, name: data.staff?.name ?? staffId, role: data.staff?.role ?? '' };
}

export function streamUrl(ward = 'W1'): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/api/v1/wards/${ward}/stream`;
}

// Opens the stream and keeps it open (back-off reconnect). The server sends a full snapshot after every
// (re)connect, so state is rebuilt, not guessed. Returns a function that closes it for good.
export function connectStream(
  token: string,
  onMessage: (m: StreamMessage) => void,
  onStatus: (s: LinkStatus) => void,
  onAuthError: () => void,
): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let timer: number | undefined;

  const open = () => {
    onStatus(attempt === 0 ? 'connecting' : 'reconnecting');
    ws = new WebSocket(streamUrl(), ['bearer', token]);
    ws.onopen = () => {
      attempt = 0;
      onStatus('live');
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data) as StreamMessage);
      } catch {
        /* a malformed frame is dropped, never shown */
      }
    };
    ws.onclose = (e) => {
      if (stopped) return;
      if (e.code === 4401) {
        onStatus('closed');
        onAuthError();
        return;
      }
      attempt += 1;
      onStatus('reconnecting');
      timer = window.setTimeout(open, Math.min(8000, 500 * 2 ** attempt));
    };
    ws.onerror = () => ws?.close();
  };
  open();

  return () => {
    stopped = true;
    window.clearTimeout(timer);
    ws?.close();
    onStatus('closed');
  };
}
