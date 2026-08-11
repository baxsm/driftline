"use client";

import type { FC } from "react";
import { configLabel, formatConfigValue } from "@/lib/format";
import type { ConfigDiffRow } from "@/lib/types";

interface ConfigDiffProps {
  rows: ConfigDiffRow[];
  labelA: string;
  labelB: string;
}

/**
 * The config keys that differ between two runs.
 *
 * An empty diff says so in a sentence rather than rendering an empty table with headers. Two
 * runs with the same config are a real and useful answer, usually meaning the difference in
 * their scores came from somewhere other than the settings, and a bare table implies the
 * comparison failed to load.
 */
const ConfigDiff: FC<ConfigDiffProps> = ({ rows, labelA, labelB }) => {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-border border-dashed bg-muted/10 px-4 py-3 text-muted-foreground text-sm">
        These two runs used identical settings. Any difference in their scores came from something
        other than the config.
      </div>
    );
  }

  return (
    // scrolls inside its own box rather than compressing, same reason as the scores table
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[28rem] text-sm">
        <thead>
          <tr className="border-border border-b text-left text-muted-foreground text-xs">
            <th scope="col" className="px-4 py-2 font-medium">
              Setting
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="h-0.5 w-3 rounded-full bg-[var(--estimate-path)]"
                />
                {labelA}
              </span>
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="h-0.5 w-3 rounded-full bg-[var(--compare-path)]"
                />
                {labelB}
              </span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="px-4 py-2 text-left font-normal text-muted-foreground">
                {configLabel(row.key)}
              </th>
              <td className="px-4 py-2 font-mono tabular-nums">{formatConfigValue(row.a)}</td>
              <td className="px-4 py-2 font-mono tabular-nums">{formatConfigValue(row.b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ConfigDiff;
