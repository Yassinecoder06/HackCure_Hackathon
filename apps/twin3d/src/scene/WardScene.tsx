import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Environment, OrbitControls, PerformanceMonitor } from '@react-three/drei';
import { Bloom, EffectComposer, N8AO, ToneMapping } from '@react-three/postprocessing';
import { ToneMappingMode } from 'postprocessing';
import * as THREE from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import type { WardState } from '../logic/wardStore';
import { bedAnchors } from '../logic/paths';
import type { Layout } from '../types';
import { WardModel } from './WardModel';
import { Staff } from './Staff';

export type CameraView = 'overview' | 'station' | 'follow';
export type QualityLevel = 0 | 1 | 2 | 3; // 0 plain, 1 bloom, 2 + ambient occlusion, 3 photo

const GOALS: Record<'overview' | 'station', { pos: THREE.Vector3; look: THREE.Vector3 }> = {
  overview: { pos: new THREE.Vector3(0, 27, 24), look: new THREE.Vector3(0, 0, 0) },
  station: { pos: new THREE.Vector3(0, 6.5, 10.5), look: new THREE.Vector3(0, 0.8, 3.2) },
};

// Flies the camera to a preset, then hands control back to the user.
function CameraRig({ view, layout, selected, nonce }: { view: CameraView; layout: Layout; selected: string | null; nonce: number }) {
  const controls = useRef<OrbitControlsImpl>(null);
  const camera = useThree((t) => t.camera);
  const goal = useRef<{ pos: THREE.Vector3; look: THREE.Vector3 } | null>(GOALS.overview);

  useEffect(() => {
    if (view === 'follow' && selected) {
      const a = bedAnchors(layout, selected);
      if (a) {
        const p = a.bed.bedside.pos;
        // above the room, on the corridor side of the bed, looking down at it (the door wall stays behind the camera)
        const toward = a.room.side === 'north' ? 1 : -1;
        goal.current = { pos: new THREE.Vector3(p[0] + 1.6, 6.4, p[2] + toward * 2.6), look: new THREE.Vector3(p[0] - 1.1, 0.5, p[2] - toward * 0.6) };
        return;
      }
    }
    goal.current = view === 'station' ? GOALS.station : GOALS.overview;
  }, [view, selected, layout, nonce]);

  useFrame((_, dt) => {
    const g = goal.current;
    const c = controls.current;
    if (!g || !c) return;
    const k = 1 - Math.exp(-dt * 3.5);
    camera.position.lerp(g.pos, k);
    c.target.lerp(g.look, k);
    c.update();
    if (camera.position.distanceTo(g.pos) < 0.05) goal.current = null;
  });

  return <OrbitControls ref={controls} makeDefault enableDamping maxPolarAngle={Math.PI / 2.05} minDistance={2} maxDistance={60} onStart={() => (goal.current = null)} />;
}

function ToneControl({ level }: { level: QualityLevel }) {
  const gl = useThree((t) => t.gl);
  useEffect(() => {
    gl.toneMapping = level === 0 ? THREE.AgXToneMapping : THREE.NoToneMapping; // with post-processing, ToneMapping does it
  }, [gl, level]);
  return null;
}

// Where each bed's label belongs on screen. The labels themselves are plain DOM buttons (see ui/Hud.tsx):
// drei's <Html> mounts a second React root, which clashes with React 19 and logged errors.
export interface LabelPos {
  id: string;
  x: number;
  y: number;
  visible: boolean;
}

function LabelProjector({ layout, onProject }: { layout: Layout; onProject: (p: LabelPos[]) => void }) {
  const { camera, size } = useThree();
  const acc = useRef(0);
  const anchors = useMemo(
    () => layout.rooms.flatMap((r) => r.beds.map((b) => ({ id: b.id, pos: new THREE.Vector3(b.bedside.pos[0] - 1.6, 2.3, b.bedside.pos[2]) }))),
    [layout],
  );
  useFrame((_, dt) => {
    acc.current += dt;
    if (acc.current < 0.1) return; // ten times a second is plenty for labels
    acc.current = 0;
    const v = new THREE.Vector3();
    onProject(
      anchors.map((a) => {
        v.copy(a.pos).project(camera);
        return { id: a.id, x: (v.x * 0.5 + 0.5) * size.width, y: (-v.y * 0.5 + 0.5) * size.height, visible: v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1 };
      }),
    );
  });
  return null;
}

interface Props {
  layout: Layout;
  state: WardState;
  selected: string | null;
  onSelect: (b: string | null) => void;
  view: CameraView;
  viewNonce: number;
  quality: QualityLevel;
  onQuality: (q: QualityLevel) => void;
  photo: boolean;
  onProject: (p: LabelPos[]) => void;
}

export function WardScene({ layout, state, selected, onSelect, view, viewNonce, quality, onQuality, photo, onProject }: Props) {
  const level: QualityLevel = photo ? 3 : quality;
  return (
    <Canvas
      id="twin-canvas"
      camera={{ position: [0, 27, 24], fov: 38, near: 0.1, far: 300 }}
      dpr={level === 0 ? 1 : level === 3 ? [2, 2] : [1, 1.5]}
      gl={{ antialias: level < 2, preserveDrawingBuffer: true, powerPreference: 'high-performance' }}
    >
      <color attach="background" args={['#12161d']} />
      <PerformanceMonitor
        ms={250}
        onDecline={() => !photo && onQuality(Math.max(0, quality - 1) as QualityLevel)}
        onIncline={() => !photo && onQuality(Math.min(2, quality + 1) as QualityLevel)}
      />
      <ToneControl level={level} />
      <Suspense fallback={null}>
        <Environment files="/hdri/hospital_1k.hdr" environmentIntensity={0.95} />
        <hemisphereLight args={['#dfe9ff', '#403830', 0.35]} />
        <WardModel layout={layout} state={state} selected={selected} onSelect={onSelect} />
        <Staff layout={layout} state={state} />
        {!photo && <LabelProjector layout={layout} onProject={onProject} />}
      </Suspense>
      <CameraRig view={view} layout={layout} selected={selected} nonce={viewNonce} />
      {level === 0 ? null : (
        <EffectComposer multisampling={level === 3 ? 8 : 0} enableNormalPass={false}>
          {level >= 2 ? <N8AO aoRadius={level === 3 ? 1.2 : 0.8} intensity={level === 3 ? 3 : 2} distanceFalloff={1} quality={level === 3 ? 'high' : 'medium'} halfRes={level < 3} /> : <></>}
          <Bloom mipmapBlur luminanceThreshold={0.85} luminanceSmoothing={0.2} intensity={level === 3 ? 0.9 : 0.6} />
          <ToneMapping mode={ToneMappingMode.AGX} />
        </EffectComposer>
      )}
    </Canvas>
  );
}
