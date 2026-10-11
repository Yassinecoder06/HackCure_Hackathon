import type { Layout, Point } from '../types';

// Walking routes for the staff figures. The layout file gives the anchors; the route follows the
// building: out of the station bay, along the corridor, through the room's door, to the bedside.
// Points are [x, up, z] in three.js axes; routes stay on the floor (up = 0).

type XZ = [number, number];
const xz = (p: Point): XZ => [p[0], p[2]];

export interface Route {
  points: XZ[];
  length: number;
}

function measure(points: XZ[]): Route {
  let length = 0;
  for (let i = 1; i < points.length; i++) length += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  return { points, length };
}

export function bedAnchors(layout: Layout, bed: string) {
  for (const room of layout.rooms) {
    const b = room.beds.find((x) => x.id === bed);
    if (b) return { room, bed: b };
  }
  return undefined;
}

// From a spot in the station bay to the bedside of `bed`.
export function routeToBed(layout: Layout, from: Point, bed: string): Route | undefined {
  const a = bedAnchors(layout, bed);
  if (!a) return undefined;
  const { hall, walkY } = layout.corridor;
  const door = xz(a.room.door.pos);
  const west = door[0] < 0;
  const sideX = west ? hall.westX : hall.eastX;
  const walkZ = -walkY; // blender y -> three z
  const pts: XZ[] = [
    xz(from),
    [from[0], hall.southZ],       // step out on the staff side of the counter
    [sideX, hall.southZ],          // around the end of the counter
    [sideX, walkZ],                // up to the corridor line
    [door[0], walkZ],              // along the corridor to the room's door
    door,                          // the door
    xz(a.bed.via),                 // inside the room, level with the bed
    xz(a.bed.bedside.pos),         // beside the bed
  ];
  return measure(dedupe(pts));
}

export function reverse(route: Route): Route {
  return { points: [...route.points].reverse(), length: route.length };
}

function dedupe(points: XZ[]): XZ[] {
  return points.filter((p, i) => i === 0 || Math.hypot(p[0] - points[i - 1][0], p[1] - points[i - 1][1]) > 0.05);
}

// Position and heading after walking `dist` metres along the route.
export function along(route: Route, dist: number): { x: number; z: number; yaw: number; done: boolean } {
  let left = Math.max(0, dist);
  const pts = route.points;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0];
    const dz = pts[i][1] - pts[i - 1][1];
    const len = Math.hypot(dx, dz);
    if (left <= len || i === pts.length - 1) {
      const t = len === 0 ? 1 : Math.min(1, left / len);
      return { x: pts[i - 1][0] + dx * t, z: pts[i - 1][1] + dz * t, yaw: Math.atan2(dx, dz), done: left >= len && i === pts.length - 1 };
    }
    left -= len;
  }
  const last = pts[pts.length - 1];
  return { x: last[0], z: last[1], yaw: 0, done: true };
}
