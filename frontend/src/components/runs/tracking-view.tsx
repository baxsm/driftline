"use client";

import { Loader2, Pause, Play } from "lucide-react";
import {
  type FC,
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
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
  /**
   * Where the scrubber opens. A failed run points this at the frame it failed on, because
   * that frame is the reason the run ended and starting at frame 0 asks the reader to go and
   * find it. Both this and the stored tracks count from the start of the run, not the
   * sequence, so a run with `start_frame` set still lands on the right image.
   */
  initialFrame?: number;
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

const TrackingView: FC<TrackingViewProps> = ({ runId, frameCount, initialFrame = 0 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const framesRef = useRef<Map<number, TrackFrame>>(new Map());
  const imageRef = useRef<HTMLImageElement | null>(null);

  // clamped, because a failure frame from a run whose poses were trimmed could sit past the
  // last frame the scrubber can reach, which would leave it pinned at an index with no image
  const [frameIndex, setFrameIndex] = useState(() =>
    Math.max(0, Math.min(initialFrame, Math.max(0, frameCount - 1))),
  );
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState<TrackFrame | null>(null);
  /** The frame asked for is not loaded yet. Distinct from "this frame has no features". */
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedWindow, setLoadedWindow] = useState<number | null>(null);

  /** Whether playback was running when a drag started, so release can put it back. */
  const resumeRef = useRef(false);

  const togglePlay = useCallback(() => {
    if (frameCount <= 1) return;
    setPlaying((value) => !value);
  }, [frameCount]);

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

  /*
   * Frames land in a ref, so a finished fetch does not re-render on its own. `loadedWindow`
   * is what says "the map changed, read it again".
   *
   * A frame that is not in the map yet is pending, not empty. Clearing `current` while the
   * next window loads made the count read "0 features tracked into this frame", which is a
   * real reading this run never produced: scrubbing past the window told the reader the
   * tracker had died. The last frame is held instead, and `pending` says the fetch is still
   * out, so the seek reads as loading rather than as a result.
   */
  // biome-ignore lint/correctness/useExhaustiveDependencies: loadedWindow signals the ref changed
  useEffect(() => {
    const frame = framesRef.current.get(frameIndex);
    if (frame) setCurrent(frame);
    setPending(!frame);
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
    image.src = `/api/runs/${runId}/frames/${frameIndex}`;
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

  /*
   * Keyboard control, scoped to the viewer rather than the window.
   *
   * A run page carries a second scrubber for the error plots, and a document level listener
   * would move both from one key. The handler sits on the container, so the keys apply to
   * whichever viewer the reader is actually in. Typing in a field is left alone.
   */
  function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement | null;
    const typing = target?.tagName === "INPUT" && (target as HTMLInputElement).type !== "range";
    if (typing || target?.tagName === "TEXTAREA") return;

    const last = Math.max(0, frameCount - 1);
    const step = event.shiftKey ? 10 : 1;
    // the range input already moves itself on the arrows, so they are only handled when
    // focus is elsewhere. Doubling up would step two frames per press.
    const onSlider = target instanceof HTMLInputElement && target.type === "range";

    if (event.key === " ") {
      event.preventDefault();
      togglePlay();
    } else if (onSlider && event.key !== "Home" && event.key !== "End") {
      return;
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setPlaying(false);
      setFrameIndex((index) => Math.max(0, index - step));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setPlaying(false);
      setFrameIndex((index) => Math.min(last, index + step));
    } else if (event.key === "Home") {
      event.preventDefault();
      setPlaying(false);
      setFrameIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setPlaying(false);
      setFrameIndex(last);
    }
  }

  /*
   * The keys ride on the container rather than on a focusable wrapper of their own. A div
   * given a tabindex and a role is a control the reader has to find and cannot see, so
   * nothing here takes focus that was not already focusable: the play button and the scrubber
   * are the two stops, and either of them being focused is what puts these keys in reach.
   */
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

      {/* biome-ignore lint/a11y/noStaticElementInteractions: the keys are delegated from the
          controls that already take focus, the play button and the scrubber, rather than from
          a wrapper given a tabindex of its own */}
      <div className="flex flex-col gap-2" onKeyDown={handleKeyDown}>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={togglePlay}
            disabled={frameCount <= 1}
            aria-label={playing ? "Pause" : "Play"}
            title={playing ? "Pause (space)" : "Play (space)"}
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
            {playing ? "Pause" : "Play"}
          </Button>

          {/*
            Dragging pauses and release resumes, rather than leaving the clock running against
            the pointer. Landing on a chosen frame is the whole point of the control, and it
            cannot be done while playback keeps moving the target.
          */}
          <input
            type="range"
            min={0}
            max={Math.max(0, frameCount - 1)}
            value={frameIndex}
            onPointerDown={() => {
              resumeRef.current = playing;
              setPlaying(false);
            }}
            onPointerUp={() => {
              if (resumeRef.current) setPlaying(true);
              resumeRef.current = false;
            }}
            onChange={(event) => setFrameIndex(Number(event.target.value))}
            aria-label="Frame"
            aria-valuetext={`Frame ${frameIndex} of ${Math.max(0, frameCount - 1)}`}
            className="scrubber min-w-0 flex-1"
          />

          <span className="w-24 shrink-0 text-right font-mono text-muted-foreground text-xs tabular-nums">
            {frameIndex} / {Math.max(0, frameCount - 1)}
          </span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground text-xs">
          {/*
            "loading" and "none found" are different readings and are never collapsed. A
            pending window used to render as zero features, which says the tracker lost every
            point on a frame where it had not been asked yet.
          */}
          <span aria-live="polite">
            {pending ? (
              <span className="flex items-center gap-1.5">
                <Loader2 className="size-3 animate-spin" aria-hidden />
                Loading frame {frameIndex}
              </span>
            ) : (
              `${formatCount(trackedCount)} features tracked into this frame`
            )}
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-2 rounded-full bg-track-new" />
            new
            <span aria-hidden className="ml-2 size-2 rounded-full bg-track-old" />
            long lived
          </span>
        </div>

        <p className="text-[0.6875rem] text-muted-foreground/70">
          Space plays and pauses. Left and right step a frame, Home and End jump to the ends.
        </p>
      </div>
    </div>
  );
};

export default TrackingView;
