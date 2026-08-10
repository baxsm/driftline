"use client";

import { type FC, type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import type { EstimatorConfig } from "@/lib/types";

/**
 * The bounds are the server's, repeated here so a value out of range is caught before a run is
 * queued. The server still validates; this only saves a round trip and points at the field.
 */
interface Field {
  key: keyof EstimatorConfig;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
}

interface Group {
  title: string;
  description: string;
  fields: Field[];
}

export const CONFIG_GROUPS: Group[] = [
  {
    title: "Features",
    description: "How many points are tracked, and how they are spread across the frame.",
    fields: [
      {
        key: "max_features",
        label: "Max features",
        hint: "50 to 2000",
        min: 50,
        max: 2000,
        step: 10,
      },
      {
        key: "min_feature_distance_px",
        label: "Min separation",
        hint: "pixels between features, 1 to 100",
        min: 1,
        max: 100,
        step: 1,
      },
      {
        key: "redetect_below",
        label: "Redetect below",
        hint: "top up when fewer than this survive",
        min: 10,
        max: 2000,
        step: 10,
      },
      {
        key: "fast_threshold",
        label: "Corner threshold",
        hint: "1 to 100, higher keeps only stronger corners",
        min: 1,
        max: 100,
        step: 1,
      },
    ],
  },
  {
    title: "Geometry",
    description: "How strictly a tracked point has to agree before it shapes the pose.",
    fields: [
      {
        key: "ransac_threshold_px",
        label: "RANSAC threshold",
        hint: "pixels, 0 to 10",
        min: 0.1,
        max: 10,
        step: 0.1,
      },
      {
        key: "min_track_length",
        label: "Min track length",
        hint: "frames a feature must survive, 2 to 100",
        min: 2,
        max: 100,
        step: 1,
      },
    ],
  },
];

export const DEFAULT_CONFIG: EstimatorConfig = {
  mode: "mono",
  max_features: 300,
  fast_threshold: 20,
  min_feature_distance_px: 12,
  ransac_threshold_px: 1,
  redetect_below: 120,
  min_track_length: 3,
  max_frames: null,
};

interface RunConfigFormProps {
  frameCount: number;
  onQueue: (config: EstimatorConfig, label: string) => Promise<void>;
}

const RunConfigForm: FC<RunConfigFormProps> = ({ frameCount, onQueue }) => {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<EstimatorConfig>(DEFAULT_CONFIG);
  const [label, setLabel] = useState("");
  const [limitFrames, setLimitFrames] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function reset() {
    setConfig(DEFAULT_CONFIG);
    setLabel("");
    setLimitFrames("");
    setError(null);
    setFieldError(null);
    setPending(false);
  }

  function update(key: keyof EstimatorConfig, raw: string) {
    const parsed = Number(raw);
    setConfig((current) => ({ ...current, [key]: Number.isFinite(parsed) ? parsed : 0 }));
  }

  function firstInvalidField(): Field | null {
    for (const group of CONFIG_GROUPS) {
      for (const field of group.fields) {
        const value = Number(config[field.key]);
        if (!Number.isFinite(value) || value < field.min || value > field.max) return field;
      }
    }
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const invalid = firstInvalidField();
    if (invalid) {
      setError(`${invalid.label} must be between ${invalid.min} and ${invalid.max}.`);
      setFieldError(invalid.key);
      return;
    }

    const trimmed = limitFrames.trim();
    const maxFrames = trimmed === "" ? null : Number(trimmed);
    if (maxFrames !== null && (!Number.isFinite(maxFrames) || maxFrames < 2)) {
      setError("Frame limit must be at least 2, or empty to run the whole sequence.");
      setFieldError("max_frames");
      return;
    }

    setError(null);
    setFieldError(null);
    setPending(true);
    try {
      await onQueue({ ...config, max_frames: maxFrames }, label.trim());
      reset();
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not queue that run.");
      setFieldError(caught instanceof ApiError ? (caught.field ?? null) : null);
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">New run</Button>
      </DialogTrigger>

      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Queue a run</DialogTitle>
            <DialogDescription>
              Monocular visual odometry over cam0. The estimate drifts and has no absolute scale;
              that is what the next phases fix and measure.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-6 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="run-label">Label</Label>
              <Input
                id="run-label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="What is this run testing?"
                autoComplete="off"
              />
            </div>

            {CONFIG_GROUPS.map((group) => (
              <section key={group.title} className="flex flex-col gap-3">
                <div className="flex flex-col gap-0.5">
                  <h3 className="font-medium text-sm">{group.title}</h3>
                  <p className="text-muted-foreground text-xs">{group.description}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  {group.fields.map((field) => (
                    <div key={field.key} className="flex flex-col gap-2">
                      <Label htmlFor={`config-${field.key}`}>{field.label}</Label>
                      <Input
                        id={`config-${field.key}`}
                        type="number"
                        inputMode="decimal"
                        value={String(config[field.key] ?? "")}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        aria-invalid={fieldError === field.key}
                        aria-describedby={`hint-${field.key}`}
                        onChange={(event) => update(field.key, event.target.value)}
                      />
                      <span id={`hint-${field.key}`} className="text-muted-foreground text-xs">
                        {field.hint}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            ))}

            <div className="flex flex-col gap-2">
              <Label htmlFor="config-max_frames">Frame limit</Label>
              <Input
                id="config-max_frames"
                type="number"
                inputMode="numeric"
                value={limitFrames}
                min={2}
                max={frameCount}
                aria-invalid={fieldError === "max_frames"}
                aria-describedby="hint-max_frames"
                onChange={(event) => setLimitFrames(event.target.value)}
                placeholder={`All ${frameCount.toLocaleString("en-US")} frames`}
              />
              <span id="hint-max_frames" className="text-muted-foreground text-xs">
                Leave empty to run the whole sequence. A short limit is the quick way to see whether
                a config tracks at all.
              </span>
            </div>

            {error ? (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? "Queueing" : "Queue run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default RunConfigForm;
