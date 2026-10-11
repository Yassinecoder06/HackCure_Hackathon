import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { callForBed, type WardState } from '../logic/wardStore';
import { monitorView } from '../logic/monitor';
import type { Band, Layout } from '../types';
import { drawMonitor, drawOff, drawTv, makeScreen, type Screen } from './screens';

useGLTF.setDecoderPath('/draco/');

interface Prepared {
  monitors: Map<string, Screen>;
  extraScreens: { tv?: Screen; pcs: Screen[] };
  callLights: Map<string, THREE.Mesh>;
  doorLights: Map<string, THREE.Mesh>;
  patients: Map<string, THREE.Object3D>;
  cutaways: { obj: THREE.Object3D; normal: THREE.Vector3; centre: THREE.Vector3 }[];
}

const bedOf = (name: string, prefix: string) => (name.startsWith(prefix) ? name.slice(prefix.length) : null);

// Finds the named nodes the Blender build exports (see apps/twin3d/blender/07_assemble_ward.py) and gives
// the ones the app drives their own material, so changing one bed's screen never touches another's.
function prepare(root: THREE.Object3D): Prepared {
  const p: Prepared = { monitors: new Map(), extraScreens: { pcs: [] }, callLights: new Map(), doorLights: new Map(), patients: new Map(), cutaways: [] };
  const off = new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: '#ff3b2f', emissiveIntensity: 0, roughness: 0.4 });
  root.traverse((o) => {
    const name = o.name;
    const mesh = o as THREE.Mesh;
    if (mesh.isMesh) {
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      mats.forEach((m) => {
        // Hair, gloves and eyelashes have cut-out transparency: alpha-test them (no sorting problems).
        if (['nurse_hair', 'nurse_gloves', 'nurse_body'].includes(m.name)) {
          m.transparent = false;
          m.alphaTest = 0.5;
          m.depthWrite = true;
        }
      });
    }
    const bed = bedOf(name, 'screen_');
    if (mesh.isMesh && bed && /^B\d+$/.test(bed)) p.monitors.set(bed, makeScreen(mesh));
    else if (mesh.isMesh && name === 'screen_tv_station') p.extraScreens.tv = makeScreen(mesh, 256);
    else if (mesh.isMesh && name.startsWith('screen_station_pc_')) p.extraScreens.pcs.push(makeScreen(mesh, 64));
    else if (mesh.isMesh && name.startsWith('callLightDoor_')) {
      mesh.material = off.clone();
      p.doorLights.set(name.slice('callLightDoor_'.length), mesh);
    } else if (mesh.isMesh && name.startsWith('callLight_')) {
      mesh.material = off.clone();
      p.callLights.set(name.slice('callLight_'.length), mesh);
    } else if (name.startsWith('patient_B')) p.patients.set(name.slice('patient_'.length), o);
    if (o.userData?.twin_cutaway && Array.isArray(o.userData.twin_normal)) {
      const [x, y, z] = o.userData.twin_normal as number[];
      p.cutaways.push({ obj: o, normal: new THREE.Vector3(x, y, z), centre: new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3()) });
    }
  });
  return p;
}

const CALL_COLOUR: Record<string, string> = { pressed: '#ff2d2d', sent: '#ff2d2d', not_sent: '#ff2dff', escalated: '#ff2d2d', acknowledged: '#ffb020' };

interface Props {
  layout: Layout;
  state: WardState;
  selected: string | null;
  onSelect: (bed: string | null) => void;
}

export function WardModel({ layout, state, selected, onSelect }: Props) {
  const gltf = useGLTF('/models/ward.glb');
  const prepared = useMemo(() => prepare(gltf.scene), [gltf.scene]);
  const camera = useThree((t) => t.camera);
  const tick = useRef(0);
  const urgent = useRef<Map<string, string>>(new Map());

  // Screens and patients follow the bed data. Redrawn only when what a screen shows actually changes.
  useEffect(() => {
    const counts: Record<Band, number> = { low: 0, low_medium: 0, medium: 0, high: 0 };
    let vacant = 0;
    let noSignal = 0;
    for (const room of layout.rooms) {
      for (const b of room.beds) {
        const bed = state.beds[b.id];
        const view = monitorView(bed);
        const screen = prepared.monitors.get(b.id);
        if (screen) drawMonitor(screen, b.id, view);
        const patient = prepared.patients.get(b.id);
        if (patient) patient.visible = view.kind !== 'vacant';
        if (view.kind === 'vacant') vacant += 1;
        else if (view.kind === 'no_signal') noSignal += 1;
        else if (view.kind === 'score') counts[view.band] += 1;
      }
    }
    if (prepared.extraScreens.tv) drawTv(prepared.extraScreens.tv, counts, vacant, noSignal, Object.keys(state.calls).length);
    prepared.extraScreens.pcs.forEach(drawOff);
  }, [state, layout, prepared]);

  // Which light colour each bed's call light shows right now.
  useEffect(() => {
    const m = new Map<string, string>();
    for (const room of layout.rooms) {
      for (const b of room.beds) {
        const c = callForBed(state, b.id);
        if (c) m.set(b.id, c.state);
      }
    }
    urgent.current = m;
  }, [state, layout]);

  useFrame((s) => {
    const t = s.clock.elapsedTime;
    // call lights: fast pulse while unanswered, steady once acknowledged
    for (const room of layout.rooms) {
      let doorState: string | undefined;
      for (const b of room.beds) {
        const st = urgent.current.get(b.id);
        const light = prepared.callLights.get(b.id);
        if (light) setLight(light, st, t);
        if (st && (!doorState || rank(st) > rank(doorState))) doorState = st;
      }
      const door = prepared.doorLights.get(room.id);
      if (door) setLight(door, doorState, t);
    }
    // doll-house view: hide walls and ceilings that face the camera (checked ~6 times a second)
    tick.current += 1;
    if (tick.current % 10 === 0) {
      const v = new THREE.Vector3();
      for (const c of prepared.cutaways) {
        v.copy(camera.position).sub(c.centre).normalize();
        c.obj.visible = c.normal.dot(v) < 0.25 && !(c.normal.y > 0.5 && camera.position.y > 2.4);
      }
    }
  });

  const pick = (e: ThreeEvent<MouseEvent>) => {
    let o: THREE.Object3D | null = e.object;
    while (o) {
      const m = /^(?:screen_|callLight_|patient_)(B\d+)$/.exec(o.name);
      if (m) {
        e.stopPropagation();
        onSelect(m[1] === selected ? null : m[1]);
        return;
      }
      o = o.parent;
    }
  };

  return <primitive object={gltf.scene} onClick={pick} onPointerMissed={() => onSelect(null)} />;
}

const rank = (s: string) => ({ escalated: 4, not_sent: 3, pressed: 2, sent: 2, acknowledged: 1 }[s] ?? 0);

function setLight(mesh: THREE.Mesh, state: string | undefined, t: number) {
  const m = mesh.material as THREE.MeshStandardMaterial;
  if (!state) {
    m.emissiveIntensity = 0;
    return;
  }
  m.emissive.set(CALL_COLOUR[state] ?? '#ff2d2d');
  const fast = state === 'escalated' || state === 'not_sent';
  m.emissiveIntensity = state === 'acknowledged' ? 2.2 : 1.2 + 2.6 * (0.5 + 0.5 * Math.sin(t * (fast ? 14 : 6)));
}
