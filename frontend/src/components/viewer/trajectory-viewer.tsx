"use client";

import { type FC, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Button } from "@/components/ui/button";
import type { Pose } from "@/lib/types";

/** Used when the stylesheet has not loaded, so the marker is never an invisible black dot. */
const ESTIMATE_MARKER_FALLBACK = "#8b7fe8";

export interface TrajectoryPath {
  poses: Pose[];
  /** A colour token like `--truth-path`, read from the stylesheet at draw time. */
  colorToken: string;
  fallbackColor: string;
  label: string;
  /**
   * Per pose error, one value per pose, colouring the line from the low to the high token.
   * When present the flat colour is not used, and the legend says what the ramp means.
   */
  errors?: number[];
}

interface TrajectoryViewerProps {
  /** One entry per path drawn. Several are overlaid in the same space. */
  paths: TrajectoryPath[];
  /** Shown when there is nothing to draw, so the canvas is never a silent black box. */
  emptyMessage: string;
  /**
   * Index into the first path carrying errors, marked with a dot so the plot, the slider and
   * the 3D view all point at the same pose.
   */
  markerIndex?: number | null;
  /** Legend caption for the error ramp, e.g. "0 to 12 cm". */
  errorLegend?: string;
}

/**
 * Reads a colour token so the viewer and the rest of the UI cannot drift apart.
 *
 * The tokens are wide gamut (`oklch()`, which Tailwind emits as `lab()`). Three.js parses
 * neither and returns **white** instead of throwing, so a mistake here renders a wrong
 * colour silently. `getComputedStyle` does not downconvert either, it hands back the same
 * `lab()` string. Painting one pixel on a canvas does force the conversion, and the sRGB
 * bytes that come back are something Three.js can always read.
 */
function readColor(token: string, fallback: string): THREE.Color {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  if (!raw) return new THREE.Color(fallback);

  const context = document.createElement("canvas").getContext("2d");
  if (!context) return new THREE.Color(fallback);

  context.fillStyle = raw;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return new THREE.Color(r / 255, g / 255, b / 255);
}

/**
 * Draws a path as one BufferGeometry. The room sequences run to a few thousand poses and a
 * per pose object for each would cost thousands of draw calls for a single line.
 *
 * When errors are supplied each vertex is coloured between the low and high tokens, so the
 * shape of the drift is visible on the path itself rather than only in the plot.
 */
function buildPathGeometry(poses: Pose[], errors?: number[]): THREE.BufferGeometry {
  const positions = new Float32Array(poses.length * 3);
  for (let index = 0; index < poses.length; index += 1) {
    const pose = poses[index];
    positions[index * 3] = pose.tx;
    positions[index * 3 + 1] = pose.ty;
    positions[index * 3 + 2] = pose.tz;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

  if (errors && errors.length === poses.length) {
    const low = readColor("--error-low", "#3fc0c8");
    const high = readColor("--error-high", "#e2724a");
    // the ramp is relative to this run's own worst pose. An absolute scale would leave an
    // accurate run drawn entirely in the "good" colour with no visible structure at all.
    const worst = Math.max(...errors);
    const colors = new Float32Array(poses.length * 3);
    const mixed = new THREE.Color();
    for (let index = 0; index < poses.length; index += 1) {
      mixed.copy(low).lerp(high, worst > 0 ? errors[index] / worst : 0);
      colors[index * 3] = mixed.r;
      colors[index * 3 + 1] = mixed.g;
      colors[index * 3 + 2] = mixed.b;
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  }
  return geometry;
}

interface Extent {
  centre: THREE.Vector3;
  /** Half the diagonal of the path's bounding box, which is what the camera frames. */
  radius: number;
  /**
   * The longest single axis of the path. A trajectory is often far longer than it is wide,
   * and half a diagonal understates that length, so the grid is sized from this instead.
   */
  longestAxis: number;
  /** Vertical size, used to drop the grid to the floor of the path rather than through it. */
  height: number;
}

function pathExtent(paths: TrajectoryPath[]): Extent {
  const box = new THREE.Box3();
  const point = new THREE.Vector3();
  for (const path of paths) {
    for (const pose of path.poses) {
      box.expandByPoint(point.set(pose.tx, pose.ty, pose.tz));
    }
  }
  const centre = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return {
    centre,
    radius: Math.max(size.length() / 2, 0.5),
    longestAxis: Math.max(size.x, size.y, size.z),
    height: size.y,
  };
}

const TrajectoryViewer: FC<TrajectoryViewerProps> = ({
  paths,
  emptyMessage,
  markerIndex = null,
  errorLegend,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const resetRef = useRef<(() => void) | null>(null);
  // the marker is state rather than a ref so that moving it depends on the scene existing.
  // With a ref, the effect that positions it would run before the scene had created it and
  // would have nothing to move.
  const [marker, setMarker] = useState<THREE.Mesh | null>(null);
  const [ready, setReady] = useState(false);

  const drawable = paths.filter((path) => path.poses.length > 0);
  const totalPoses = drawable.reduce((sum, path) => sum + path.poses.length, 0);
  // rebuilding the scene on every render would restart the camera mid-drag, so the effect
  // keys off what is actually drawn: which paths, how long, and where each one ends
  const signature = drawable
    .map((path) => {
      const last = path.poses[path.poses.length - 1];
      return `${path.label}:${path.poses.length}:${last.timestamp_ns}`;
    })
    .join("|");

  // the scene is rebuilt when the drawn geometry changes. `drawable` is a fresh array on
  // every render, so `signature` is what the effect actually depends on.
  // biome-ignore lint/correctness/useExhaustiveDependencies: signature stands in for drawable
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || totalPoses === 0) return;

    const scene = new THREE.Scene();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const { centre, radius, longestAxis, height } = pathExtent(drawable);

    // clip planes follow the path size so a small room and a long outdoor run both stay in
    // range without z fighting at one end or clipping at the other
    const camera = new THREE.PerspectiveCamera(50, 1, radius / 100, radius * 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxDistance = radius * 20;

    // the grid is a scale reference, so it stays close to the path's own size. Making it
    // several times larger pushes the camera back to frame the grid and the trajectory ends
    // up a dot in the middle.
    //
    // `radius` is half the bounding box diagonal, which for a long thin path is about half
    // its length. Sizing the grid from the longest axis instead keeps it under the whole
    // path rather than under the middle third of it.
    const gridSpan = Math.max(longestAxis, radius) * 1.2;
    const grid = new THREE.GridHelper(gridSpan, 12, 0x3a3f47, 0x24282e);
    grid.position.set(centre.x, centre.y - height / 2, centre.z);
    scene.add(grid);

    const axes = new THREE.AxesHelper(radius * 0.2);
    axes.position.set(centre.x, centre.y - height / 2, centre.z);
    scene.add(axes);

    const drawn = drawable.map((path) => {
      const coloured = Boolean(path.errors && path.errors.length === path.poses.length);
      const geometry = buildPathGeometry(path.poses, path.errors);
      const material = new THREE.LineBasicMaterial(
        coloured
          ? { vertexColors: true }
          : { color: readColor(path.colorToken, path.fallbackColor) },
      );
      scene.add(new THREE.Line(geometry, material));
      return { geometry, material };
    });

    // one small sphere marking the pose the plots and the slider are pointing at, sized
    // against the path so it stays visible on a long run and does not swamp a short one.
    // It takes the estimate's own colour rather than the foreground, because a near white
    // dot sitting on the near white truth line is invisible exactly where it matters.
    const markerGeometry = new THREE.SphereGeometry(radius * 0.03, 16, 16);
    const markerMaterial = new THREE.MeshBasicMaterial({
      color: readColor("--estimate-path", ESTIMATE_MARKER_FALLBACK),
    });
    const markerMesh = new THREE.Mesh(markerGeometry, markerMaterial);
    markerMesh.visible = false;
    scene.add(markerMesh);
    setMarker(markerMesh);

    function resetView() {
      // distance is derived from the vertical field of view so the path fills the frame at
      // any scale, rather than from a fixed multiplier that only suits one sequence size
      const fitDistance = radius / Math.tan((camera.fov * Math.PI) / 360);
      const distance = fitDistance * 1.15;
      const diagonal = distance / Math.sqrt(2.25);
      camera.position.set(centre.x + diagonal, centre.y + distance * 0.5, centre.z + diagonal);
      controls.target.copy(centre);
      controls.update();
    }
    resetView();
    resetRef.current = resetView;
    setReady(true);

    function resize() {
      const { clientWidth, clientHeight } = mount as HTMLDivElement;
      if (clientWidth === 0 || clientHeight === 0) return;
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
    }
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let frame = 0;
    function animate() {
      frame = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      for (const { geometry, material } of drawn) {
        geometry.dispose();
        material.dispose();
      }
      markerGeometry.dispose();
      markerMaterial.dispose();
      setMarker(null);
      grid.dispose();
      axes.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      resetRef.current = null;
      setReady(false);
    };
  }, [signature, totalPoses]);

  /**
   * Move the marker without rebuilding the scene.
   *
   * Selecting a pose changes one object's position. Putting `markerIndex` in the effect that
   * builds the scene would tear down and recreate the whole renderer on every step of the
   * slider, resetting the camera mid-drag.
   */
  const markedPath = drawable.find((path) => path.errors)?.poses;
  useEffect(() => {
    if (!marker) return;
    const pose = markerIndex === null ? undefined : markedPath?.[markerIndex];
    marker.visible = Boolean(pose);
    if (pose) marker.position.set(pose.tx, pose.ty, pose.tz);
  }, [marker, markerIndex, markedPath]);

  if (totalPoses === 0) {
    // a viewer with nothing in it does not need viewer sized space. Keeping the full height
    // here pushes the rest of the page below the fold to say "there is nothing to draw".
    return (
      <div className="flex items-center justify-center rounded-lg border border-border border-dashed bg-muted/10 px-6 py-10 text-center text-muted-foreground text-sm">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-lg border border-border bg-muted/10">
      <div ref={mountRef} className="absolute inset-0" data-testid="viewer-canvas" />
      <div className="pointer-events-none absolute top-3 left-3 flex flex-col gap-1.5">
        {drawable.map((path) => (
          <span key={path.label} className="flex items-center gap-2 text-xs">
            <span
              aria-hidden="true"
              className="h-0.5 w-4 rounded-full"
              style={
                path.errors
                  ? {
                      backgroundImage:
                        "linear-gradient(to right, var(--error-low), var(--error-high))",
                    }
                  : { backgroundColor: `var(${path.colorToken}, ${path.fallbackColor})` }
              }
            />
            <span className="text-muted-foreground">
              {path.label}
              {path.errors && errorLegend ? `, ${errorLegend}` : ""}
            </span>
          </span>
        ))}
      </div>
      {ready ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => resetRef.current?.()}
          className="absolute top-3 right-3"
        >
          Reset view
        </Button>
      ) : null}
    </div>
  );
};

export default TrajectoryViewer;
