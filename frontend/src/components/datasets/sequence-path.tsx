"use client";

import { Check, Copy } from "lucide-react";
import { type FC, useState } from "react";
import { Button } from "@/components/ui/button";

/**
 * The sequence folder, named rather than spelled out.
 *
 * The full path was printed inline, which on a real machine is most of a line of chrome that
 * says very little: the folder name is what identifies the sequence, and the rest only
 * matters when you are about to type it somewhere. So the name is shown, the whole path is
 * on the title, and copying it is one press.
 */
const SequencePath: FC<{ path: string }> = ({ path }) => {
  const [copied, setCopied] = useState(false);
  const folder = path.split(/[/\\]/).filter(Boolean).pop() ?? path;

  async function copy() {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard can be refused; the full path is on the title either way
      setCopied(false);
    }
  }

  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className="truncate font-mono text-muted-foreground text-xs" title={path}>
        {folder}
      </span>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={copy}
        aria-label={copied ? "Path copied" : "Copy the full path"}
        title={copied ? "Copied" : "Copy the full path"}
      >
        {copied ? <Check className="text-status-success" aria-hidden /> : <Copy aria-hidden />}
      </Button>
    </span>
  );
};

export default SequencePath;
