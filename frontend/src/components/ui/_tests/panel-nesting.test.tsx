import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE_ROOT = join(process.cwd(), "src");

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) return entry === "_tests" ? [] : sourceFiles(full);
    return entry.endsWith(".tsx") ? [full] : [];
  });
}

/**
 * A bordered panel inside another bordered panel is the nesting the UI rules forbid, and it
 * is easy to reintroduce by wrapping one more section without looking at what already frames
 * it. Scanning the source catches that at the point it is written; a runtime guard would only
 * catch the paths a test happens to render.
 */
describe("panel nesting", () => {
  const files = sourceFiles(SOURCE_ROOT);

  it("finds source files to scan", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it("never renders a Panel inside another Panel", () => {
    const offenders = files.filter((file) => {
      // the primitive's own definition contains the single <section data-slot="panel">
      if (file.endsWith(join("ui", "panel.tsx"))) return false;
      const source = readFileSync(file, "utf8");
      const opens = source.match(/<Panel[\s>]/g);
      return opens !== null && opens.length > 1 && /<Panel[\s>][\s\S]*<Panel[\s>]/.test(source)
        ? isNested(source)
        : false;
    });

    expect(offenders).toEqual([]);
  });
});

/**
 * Two panels in one file are normal; a screen is a column of them. Only a `<Panel>` opened
 * before a previous one has closed is a nest, so the check tracks depth rather than counting
 * occurrences.
 */
function isNested(source: string): boolean {
  const tokens = source.match(/<Panel[\s>]|<\/Panel>/g) ?? [];
  let depth = 0;
  for (const token of tokens) {
    if (token === "</Panel>") {
      depth = Math.max(0, depth - 1);
      continue;
    }
    depth += 1;
    if (depth > 1) return true;
  }
  return false;
}
