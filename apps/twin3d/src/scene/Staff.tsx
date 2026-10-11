import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { clone } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { responseTargets, type WardState } from '../logic/wardStore';
import { along, bedAnchors, reverse, routeToBed, type Route } from '../logic/paths';
import type { Anchor, Layout, Point, Role } from '../types';

const SPEED = 1.35; // m/s, the pace of the walk clip
type Mode = 'seated' | 'standing_up' | 'walking_out' | 'at_bed' | 'walking_back' | 'sitting_down' | 'standing';

interface Home {
  pos: Point;
  yaw: number;
  seat?: { lift: number };
}

function homeOf(layout: Layout, id: string): Home {
  const h = layout.home[id];
  if (h?.kind === 'seat' && layout.station.seats[h.index]) {
    const s = layout.station.seats[h.index];
    return { pos: s.pos, yaw: s.yaw, seat: { lift: s.lift } };
  }
  const stands = layout.station.standing;
  const a: Anchor = stands[(h?.index ?? 0) % stands.length];
  return { pos: a.pos, yaw: a.yaw };
}

function recolour(root: THREE.Object3D, outfit: { top: Point; bottom: Point; hat: Point }) {
  const own = new Map<string, THREE.MeshStandardMaterial>();
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    const m = mesh.material as THREE.MeshStandardMaterial;
    const key = m.name === 'nurse_top' ? 'top' : m.name === 'nurse_bottom' ? 'bottom' : m.name === 'nurse_hat' ? 'hat' : null;
    if (!key) return;
    let c = own.get(m.name);
    if (!c) {
      c = m.clone(); // each person gets their own material; the outfit table is linear RGB from Blender
      c.color.setRGB(...outfit[key], THREE.LinearSRGBColorSpace);
      own.set(m.name, c);
    }
    mesh.material = c;
  });
}

interface ActorProps {
  id: string;
  role: Role;
  layout: Layout;
  state: WardState;
  source: THREE.Group;
  clips: THREE.AnimationClip[];
}

function Actor({ id, role, layout, state, source, clips }: ActorProps) {
  const group = useRef<THREE.Group>(null);
  const model = useMemo(() => {
    const m = clone(source) as THREE.Group;
    recolour(m, layout.outfits[role]);
    m.traverse((o) => {
      o.frustumCulled = false; // skinned meshes: the bind-pose bounds are wrong once animated
    });
    return m;
  }, [source, layout, role]);
  const mixer = useMemo(() => new THREE.AnimationMixer(model), [model]);
  const home = useMemo(() => homeOf(layout, id), [layout, id]);
  const targets = useRef<Record<string, string>>({});
  targets.current = responseTargets(state);

  const ctl = useRef({
    mode: (home.seat ? 'seated' : 'standing') as Mode,
    bed: null as string | null,
    route: null as Route | null,
    dist: 0,
    timer: 0,
    lift: home.seat?.lift ?? 0,
    yaw: home.yaw,
    current: '' as string,
  });

  const play = (name: string, once = false) => {
    const c = ctl.current;
    if (c.current === name) return;
    const clip = clips.find((k) => k.name === name);
    if (!clip) return;
    const next = mixer.clipAction(clip);
    next.reset();
    next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    next.clampWhenFinished = once;
    const prev = c.current ? mixer.clipAction(clips.find((k) => k.name === c.current)!) : null;
    next.play();
    if (prev) prev.crossFadeTo(next, 0.25, false);
    c.current = name;
  };
  const clipLength = (name: string) => clips.find((k) => k.name === name)?.duration ?? 2;

  useEffect(() => {
    play(home.seat ? 'type' : 'idle');
    return () => {
      mixer.stopAllAction();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mixer]);

  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, 0.1);
    const c = ctl.current;
    const wanted = targets.current[id] ?? null;
    const g = group.current;
    if (!g) return;
    c.timer += dt;

    switch (c.mode) {
      case 'seated':
      case 'standing':
        if (wanted && routeToBed(layout, home.pos, wanted)) {
          c.bed = wanted;
          c.route = routeToBed(layout, home.pos, wanted)!;
          c.dist = 0;
          c.timer = 0;
          if (c.mode === 'seated') {
            c.mode = 'standing_up';
            play('sit_to_stand', true);
          } else {
            c.mode = 'walking_out';
            play('walk');
          }
        }
        break;
      case 'standing_up': {
        const len = clipLength('sit_to_stand');
        c.lift = (home.seat?.lift ?? 0) * Math.max(0, 1 - c.timer / len); // rise out of the chair
        if (c.timer >= len) {
          c.mode = 'walking_out';
          c.lift = 0;
          play('walk');
        }
        break;
      }
      case 'walking_out':
      case 'walking_back': {
        c.dist += SPEED * dt;
        const p = along(c.route!, c.dist);
        g.position.set(p.x, 0, p.z);
        c.yaw = p.yaw;
        if (p.done) {
          if (c.mode === 'walking_out') {
            const a = bedAnchors(layout, c.bed!)!;
            c.yaw = a.bed.bedside.yaw;
            c.mode = 'at_bed';
            play('talk');
          } else if (home.seat) {
            c.yaw = home.yaw;
            c.mode = 'sitting_down';
            c.timer = 0;
            play('stand_to_sit', true);
          } else {
            c.yaw = home.yaw;
            c.mode = 'standing';
            play('idle');
          }
        }
        break;
      }
      case 'at_bed':
        if (targets.current[id] !== c.bed) {
          c.route = reverse(c.route!);
          c.dist = 0;
          c.mode = 'walking_back';
          play('walk');
        }
        break;
      case 'sitting_down': {
        const len = clipLength('stand_to_sit');
        c.lift = (home.seat?.lift ?? 0) * Math.min(1, c.timer / len);
        if (c.timer >= len) {
          c.mode = 'seated';
          c.lift = home.seat?.lift ?? 0;
          play('type');
        }
        break;
      }
    }

    if (c.mode === 'seated' || c.mode === 'standing' || c.mode === 'standing_up' || c.mode === 'sitting_down') {
      g.position.set(home.pos[0], 0, home.pos[2]);
    }
    g.position.y = c.lift;
    // turn smoothly toward the heading
    const diff = Math.atan2(Math.sin(c.yaw - g.rotation.y), Math.cos(c.yaw - g.rotation.y));
    g.rotation.y += diff * Math.min(1, dt * 8);
    mixer.update(dt);
  });

  return (
    <group ref={group} position={[home.pos[0], home.seat?.lift ?? 0, home.pos[2]]} rotation={[0, home.yaw, 0]}>
      <primitive object={model} />
    </group>
  );
}

export function Staff({ layout, state }: { layout: Layout; state: WardState }) {
  const gltf = useGLTF('/models/staff.glb');
  const people = layout.staff.filter((s) => state.staff[s.id]?.onWard !== false && state.staff[s.id]?.onShift !== false);
  if (!state.ready) return null;
  return (
    <>
      {people.map((s) => (
        <Actor key={s.id} id={s.id} role={s.role} layout={layout} state={state} source={gltf.scene} clips={gltf.animations} />
      ))}
    </>
  );
}
