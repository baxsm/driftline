"use client";

import { Pause, Play } from "lucide-react";
import { type FC, useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { API_BASE, ApiError, api } from "@/lib/api";
import { formatCount } from "@/lib/format";
import type { TrackFrame, TracksResponse } from "@/lib/types";

/** Tracks come back a window at a time, well under the server's 100 frame ceiling. */
const WINDOW = 60;
const PLAYBACK_MS = 100;
const NEW_TRACK_FALLBACK = "#3fb8c4";
const OLD_TRACK_FALLBACK = "#d1a63c";
/** A feature this old is drawn fully at the far end of the ramp. */
const AGE_CEILING = 30;

interface TrackingViewProps {
  runId: string;
  frameCount: number;
}

/**
 * Reads a colour token as sRGB bytes.
 *
 * The tokens are wide gamut and `getComputedStyle` hands back `lab()` unchanged. Canvas
 * `fillStyle` parses it, so painting one pixel and reading it back is what forces the
 * conversion. Same reason the 3D viewer does it.
 */
function readRgb(token: string, fallback: string): [number, number, number] {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  const context = document.createElement("canvas").getContext("2d");
  if (!raw || !context) return hexToRgb(fallback);
  context.fillStyle = raw;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return [r, g, b];
}

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.replace("#", ""), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function mix(from: [number, number, number], to: [number, number, number], amount: number): string {
  const clamped = Math.max(0, Math.min(1, amount));
  const channel = (index: number) => Math.round(from[index] + (to[index] - from[index]) * clamped);
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}

const TrackingView: FC<TrackingViewProps> = ({ runId, frameCount }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const framesRef = useRef<Map<number, TrackFrame>>(new Map());
  const imageRef = useRef<HTMLImageElement | null>(null);

  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState<TrackFrame | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedWindow, setLoadedWindow] = useState<number | null>(null);

  const windowStart = Math.floor(frameIndex / WINDOW) * WINDOW;

  useEffect(() => {
    let cancelled = false;
    async function loadWindow() {
      const last = Math.min(windowStart + WINDOW - 1, frameCount - 1);
      try {
        const response = await api.get<TracksResponse>(
          `/api/runs/${runId}/tracks?from=${windowStart}&to=${last}`,
        );
        if (cancelled) return;
        for (const frame of response.frames) framesRef.current.set(frame.frame_index, frame);
        setLoadedWindow(windowStart);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof ApiError ? caught.message : "Could not load feature tracks.");
      }
    }
    void loadWindow();
    return () => {
      cancelled = true;
    };
  }, [runId, windowStart, frameCount]);

  // frames land in a ref, so a finished fetch does not re-render on its own. `loadedWindow`
  // is what says "the map changed, read it again".
  // biome-ignore lint/correctness/useExhaustiveDependencies: loadedWindow signals the ref changed
  useEffect(() => {
    setCurrent(framesRef.current.get(frameIndex) ?? null);
  }, [frameIndex, loadedWindow]);

  /** Draws the frame, then its features. Redraws once the image itself has decoded. */
  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const width = image?.naturalWidth || canvas.width;
    const height = image?.naturalHeight || canvas.height;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    context.clearRect(0, 0, width, height);
    if (image?.complete && image.naturalWidth > 0) {
      context.drawImage(image, 0, 0, width, height);
    } else {
      context.fillStyle = "#14161a";
      context.fillRect(0, 0, width, height);
    }

    const young = readRgb("--track-new", NEW_TRACK_FALLBACK);
    const old = readRgb("--track-old", OLD_TRACK_FALLBACK);
    for (const feature of current?.features ?? []) {
      context.beginPath();
      context.arc(feature.x, feature.y, 3, 0, Math.PI * 2);
      context.strokeStyle = mix(young, old, feature.age / AGE_CEILING);
      context.lineWidth = 1.5;
      context.stroke();
    }
  }, [current]);

  useEffect(() => {
    const image = new Image();
    image.crossOrigin = "use-credentials";
    image.src = `${API_BASE}/api/runs/${runId}/frames/${frameIndex}`;
    imageRef.current = image;
    image.onload = paint;
    image.onerror = paint;
    paint();
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [runId, frameIndex, paint]);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setFrameIndex((index) => {
        if (index + 1 >= frameCount) {
          setPlaying(false);
          return index;
        }
        return index + 1;
      });
    }, PLAYBACK_MS);
    return () => clearInterval(timer);
  }, [playing, frameCount]);

  const trackedCount = current?.features.length ?? 0;

  return (
    <div className="flex flex-col gap-3">
      {/*
        the frame is capped in height rather than left to fill the width. A 640x480 frame on a
        wide screen otherwise grows tall enough to push the scrubber below the fold, and the
        controls for a viewer should never be off screen from the thing they control.
      */}
      <div className="flex max-h-[60vh] w-fit max-w-full justify-center self-center overflow-hidden rounded-lg border border-border bg-muted/10">
        <canvas
          ref={canvasRef}
          data-testid="tracking-canvas"
          className="block max-h-[60vh] w-auto max-w-full object-contain"
          role="img"
          aria-label={`Tracked features drawn on frame ${frameIndex}`}
        />
      </div>

      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPlaying((value) => !value)}
            disabled={frameCount <= 1}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
            {playing ? "Pause" : "Play"}
          </Button>

          <input
            type="range"
            min={0}
            max={Math.max(0, frameCount - 1)}
            value={frameIndex}
            onChange={(event) => {
              setPlaying(false);
              setFrameIndex(Number(event.target.value));
            }}
            aria-label="Frame"
            className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-border accent-foreground"
          />

          <span className="w-24 shrink-0 text-right font-mono text-muted-foreground text-xs">
            {frameIndex} / {Math.max(0, frameCount - 1)}
          </span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground text-xs">
          <span>{formatCount(trackedCount)} features tracked into this frame</span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-2 rounded-full bg-track-new" />
            new
            <span aria-hidden className="ml-2 size-2 rounded-full bg-track-old" />
            long lived
          </span>
        </div>
      </div>
    </div>
  );
};

export default TrackingView;
