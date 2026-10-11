import * as THREE from 'three';
import { S } from '../strings';
import { BAND_COLOUR, glowColour, glowStrength, type MonitorView } from '../logic/monitor';
import type { Band } from '../types';

// A screen is a flat mesh from the Blender model (screen_<bed>, screen_tv_station ...). We give it a canvas
// texture and draw into the canvas; the texture is the screen's emissive map, so bright pixels feed bloom.
export interface Screen {
  mesh: THREE.Mesh;
  canvas: HTMLCanvasElement;
  texture: THREE.CanvasTexture;
  material: THREE.MeshStandardMaterial;
  key: string;
}

export function makeScreen(mesh: THREE.Mesh, size = 256): Screen {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.flipY = false; // the Blender quad's UVs are already 0..1 with the origin at the bottom left
  const material = new THREE.MeshStandardMaterial({
    color: '#040506', roughness: 0.25, metalness: 0, emissive: '#ffffff', emissiveMap: texture, emissiveIntensity: 0,
  });
  mesh.material = material;
  return { mesh, canvas, texture, material, key: '' };
}

function ctxOf(s: Screen) {
  const ctx = s.canvas.getContext('2d')!;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, s.canvas.width, s.canvas.height);
  return ctx;
}

function finish(s: Screen, intensity: number, key: string) {
  s.texture.needsUpdate = true;
  s.material.emissiveIntensity = intensity;
  s.key = key;
}

export function drawMonitor(s: Screen, bedId: string, view: MonitorView) {
  const key = bedId + JSON.stringify(view);
  if (s.key === key) return;
  const W = s.canvas.width;
  const ctx = ctxOf(s);
  // The quad is mapped with a flipped v in glTF; draw upright and let the texture flag handle it.
  ctx.fillStyle = '#05070a';
  ctx.fillRect(0, 0, W, W);
  const glow = glowColour(view);
  if (view.kind === 'vacant') return finish(s, 0, key);

  // frame glow
  ctx.strokeStyle = glow;
  ctx.lineWidth = 14;
  ctx.strokeRect(7, 7, W - 14, W - 14);
  ctx.fillStyle = '#9aa4b2';
  ctx.font = '600 26px system-ui, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(bedId, 22, 44);
  ctx.textAlign = 'center';

  if (view.kind === 'score') {
    ctx.fillStyle = BAND_COLOUR[view.band];
    ctx.font = '800 118px system-ui, sans-serif';
    ctx.fillText(String(view.total), W / 2, 150);
    ctx.font = '700 28px system-ui, sans-serif';
    ctx.fillText(`${S.monitor.news2} ${S.band[view.band]}`, W / 2, 190);
    if (view.partial) {
      ctx.fillStyle = '#05070a';
      ctx.fillRect(W / 2 - 62, 204, 124, 34);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 3;
      ctx.setLineDash([8, 6]);
      ctx.strokeRect(W / 2 - 62, 204, 124, 34);
      ctx.setLineDash([]);
      ctx.fillStyle = '#ffffff';
      ctx.font = '700 22px system-ui, sans-serif';
      ctx.fillText(S.monitor.partial, W / 2, 229);
    }
  } else {
    const text = view.kind === 'no_signal' ? S.monitor.noSignal : view.kind === 'no_device' ? S.monitor.noDevice : S.monitor.unavailable;
    ctx.fillStyle = glow;
    ctx.font = '800 36px system-ui, sans-serif';
    wrap(ctx, text, W / 2, 130, 36);
    ctx.strokeStyle = '#8a94a6';
    ctx.lineWidth = 3;
    ctx.beginPath(); // diagonal hatching: reads as "no data" even in monochrome
    for (let x = -W; x < W * 2; x += 28) {
      ctx.moveTo(x, W - 14);
      ctx.lineTo(x + 60, W - 70);
    }
    ctx.stroke();
  }
  finish(s, glowStrength(view), key);
}

function wrap(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, lh: number) {
  const words = text.split(' ');
  words.forEach((w, i) => ctx.fillText(w, x, y + i * lh));
}

export function drawTv(s: Screen, counts: Record<Band, number>, vacant: number, noSignal: number, calls: number) {
  const key = JSON.stringify([counts, vacant, noSignal, calls]);
  if (s.key === key) return;
  const W = s.canvas.width;
  const ctx = ctxOf(s);
  ctx.fillStyle = '#05070a';
  ctx.fillRect(0, 0, W, W);
  ctx.fillStyle = '#c8d0dc';
  ctx.font = '700 30px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('WARD W1', W / 2, 44);
  const rows: [string, number, string][] = [
    [S.band.high, counts.high, BAND_COLOUR.high],
    [S.band.medium, counts.medium, BAND_COLOUR.medium],
    [S.band.low_medium, counts.low_medium, BAND_COLOUR.low_medium],
    [S.band.low, counts.low, BAND_COLOUR.low],
    [S.monitor.noSignal, noSignal, '#8a94a6'],
  ];
  rows.forEach(([label, n, colour], i) => {
    const y = 84 + i * 30;
    ctx.fillStyle = colour;
    ctx.fillRect(24, y - 18, 10, 22);
    ctx.textAlign = 'left';
    ctx.font = '600 22px system-ui, sans-serif';
    ctx.fillText(label, 44, y);
    ctx.textAlign = 'right';
    ctx.fillText(String(n), W - 24, y);
  });
  ctx.textAlign = 'left';
  ctx.fillStyle = '#8a94a6';
  ctx.font = '500 20px system-ui, sans-serif';
  ctx.fillText(`${S.monitor.vacant}: ${vacant}`, 24, 250 - 40);
  ctx.fillStyle = calls ? '#ff6b6b' : '#8a94a6';
  ctx.fillText(`${S.bed.call}s: ${calls}`, 24, 250 - 12);
  finish(s, 1.1, key);
}

// Screens that have nothing real to show stay dark (the twin never invents content).
export function drawOff(s: Screen) {
  if (s.key === 'off') return;
  const ctx = ctxOf(s);
  ctx.fillStyle = '#05070a';
  ctx.fillRect(0, 0, s.canvas.width, s.canvas.height);
  finish(s, 0, 'off');
}
