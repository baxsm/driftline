"use client";

import { type FC, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

/**
 * What the estimator wrote while the run executed.
 *
 * On a failed run this is where the reason came from and what preceded it: how many frames
 * were read, which camera model, whether fusion ran, whether scoring found ground truth. The
 * failure banner states the conclusion, and this is the working that led to it.
 *
 * Collapsed by default. It is a diagnostic rather than part of reading a successful run, and
 * left open it pushes everything else off the screen on a long run.
 */
const RunLog: FC<{ runId: string }> = ({ runId }) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setText(await api.getText(`/api/runs/${runId}/log`));
    } catch (caught) {
      setText(null);
      setError(caught instanceof ApiError ? caught.message : "Could not load the log.");
    }
  }, [runId]);

  useEffect(() => {
    if (open && text === null && error === null) void load();
  }, [open, text, error, load]);

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "Hide log" : "Show log"}
      </Button>

      {open ? (
        error ? (
          <div role="alert" className="flex flex-col items-start gap-2">
            <p className="text-destructive text-sm">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Try again
            </Button>
          </div>
        ) : text === null ? (
          <p className="text-muted-foreground text-sm">Loading the log.</p>
        ) : text.trim() === "" ? (
          <p className="text-muted-foreground text-sm">
            This run wrote no log. Its artifacts were removed, or it never reached the worker.
          </p>
        ) : (
          // No box of its own: the Panel above already draws the frame, and a rounded bordered
          // block inside it was a box in a box. A rule and the page's own surface separate the
          // log from the control that opened it, so it reads as output rather than as a card.
          // wrapped rather than scrolled sideways: the config line is a long JSON blob, and a
          // horizontal scrollbar hides the end of it behind a gesture nobody makes
          <pre className="-mx-4 -mb-4 max-h-80 overflow-y-auto whitespace-pre-wrap break-words border-border border-t bg-surface-page px-4 py-3 font-mono text-muted-foreground text-xs leading-relaxed">
            {text}
          </pre>
        )
      ) : null}
    </div>
  );
};

export default RunLog;
