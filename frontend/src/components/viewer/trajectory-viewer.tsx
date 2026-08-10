"use client";

import { type FC, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Button } from "@/components/ui/button";
import type { Pose } from "@/lib/types";

interface TrajectoryViewerProps {
  poses: Pose[];
  /** Shown when there is nothing to draw, so the canvas is never a silent black box. */
  emptyMessage: string;
}

const GROUND_TRUTH_FALLBACK = "#b4b8c0";

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
 */
function buildPathGeometry(poses: Pose[]): THREE.BufferGeometry {
  const positions = new Float32Array(poses.length * 3);
  for (let index = 0; index < poses.length; index += 1) {
    const pose = poses[index];
    positions[index * 3] = pose.tx;
    positions[index * 3 + 1] = pose.ty;
    positions[index * 3 + 2] = pose.tz;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
}

interface Extent {
  centre: THREE.Vector3;
  /** Half the diagonal of the path's bounding box, which is what the camera frames. */
  radius: number;
  /** Vertical size, used to drop the grid to the floor of the path rather than through it. */
  height: number;
}

function pathExtent(poses: Pose[]): Extent {
  const box = new THREE.Box3();
  const point = new THREE.Vector3();
  for (const pose of poses) {
    box.expandByPoint(point.set(pose.tx, pose.ty, pose.tz));
  }
  const centre = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return {
    centre,
    radius: Math.max(size.length() / 2, 0.5),
    height: size.y,
  };
}

const TrajectoryViewer: FC<TrajectoryViewerProps> = ({ poses, emptyMessage }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || poses.length === 0) return;

    const scene = new THREE.Scene();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const { centre, radius, height } = pathExtent(poses);

    // clip planes follow the path size so a small room and a long outdoor run both stay in
    // range without z fighting at one end or clipping at the other
    const camera = new THREE.PerspectiveCamera(50, 1, radius / 100, radius * 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxDistance = radius * 20;

    // the grid is a scale reference, so it stays close to the path's own size. Making it
    // several times larger pushes the camera back to frame the grid and the trajectory ends
    // up a dot in the middle.
    const grid = new THREE.GridHelper(radius * 1.5, 12, 0x3a3f47, 0x24282e);
    grid.position.set(centre.x, centre.y - height / 2, centre.z);
    scene.add(grid);

    const axes = new THREE.AxesHelper(radius * 0.2);
    axes.position.set(centre.x, centre.y - height / 2, centre.z);
    scene.add(axes);

    const geometry = buildPathGeometry(poses);
    const material = new THREE.LineBasicMaterial({
      color: readColor("--truth-path", GROUND_TRUTH_FALLBACK),
    });
    scene.add(new THREE.Line(geometry, material));

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
      geometry.dispose();
      material.dispose();
      grid.dispose();
      axes.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      resetRef.current = null;
      setReady(false);
    };
  }, [poses]);

  if (poses.length === 0) {
    return (
      <div className="flex min-h-[320px] flex-1 items-center justify-center rounded-lg border border-border bg-muted/10 px-6 text-center text-muted-foreground text-sm">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-lg border border-border bg-muted/10">
      <div ref={mountRef} className="absolute inset-0" data-testid="viewer-canvas" />
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
