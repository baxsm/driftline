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

  /**
   * A Panel already draws the only border that level needs. Anything given its own border
   * and rounding inside one is the box in a box the rules forbid, and it does not have to be
   * a Panel to look like one: a plain div with `rounded-xl border` reads exactly the same.
   *
   * Lists inside a panel separate their rows with dividers instead, which is why
   * `divide-*` and a bare `border-t` are not matches here.
   */
  it("never draws a bordered rounded box inside a Panel", () => {
    const offenders: string[] = [];

    for (const file of files) {
      if (file.endsWith(join("ui", "panel.tsx"))) continue;
      const source = readFileSync(file, "utf8");

      for (const region of panelBodies(source)) {
        // a container that both rounds and borders itself is drawing its own frame
        if (/rounded-(?:lg|xl|2xl)[^"'`]*\bborder\b(?!-0)/.test(region)) {
          offenders.push(file);
          break;
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  /**
   * The same rule across files.
   *
   * A panel's body is often one component, so the box is drawn where the Panel is not: the
   * estimator log rendered its own bordered block, and the `<Panel>` framing it lived on the
   * run screen. Scanning inside `<Panel>` alone cannot see that, so every component used as a
   * panel body is checked for a frame of its own at its top level.
   */
  it("never has a panel body component draw its own frame", () => {
    const bodies = new Set<string>();
    for (const file of files) {
      for (const region of panelBodies(readFileSync(file, "utf8"))) {
        for (const [, name] of region.matchAll(/<([A-Z][A-Za-z0-9]*)[\s/>]/g)) {
          if (name !== "Panel") bodies.add(name);
        }
      }
    }

    const offenders = files.filter((file) => {
      const name = file.split(/[/\\]/).pop()?.replace(".tsx", "") ?? "";
      const component = name.replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase());
      if (!bodies.has(component)) return false;
      const source = readFileSync(file, "utf8");
      // the outermost element of a panel body must not round and border itself
      return /return \(\s*(?:\/\*[\s\S]*?\*\/\s*)?<\w[^>]*className="[^"]*rounded-(?:lg|xl|2xl)[^"]*\bborder\b(?!-0)/.test(
        source,
      );
    });

    expect(offenders).toEqual([]);
  });
});

/** The source between each `<Panel ...>` and its matching `</Panel>`. */
function panelBodies(source: string): string[] {
  const bodies: string[] = [];
  const opens = [...source.matchAll(/<Panel[\s>]/g)];

  for (const open of opens) {
    const start = open.index ?? 0;
    const close = source.indexOf("</Panel>", start);
    if (close === -1) continue;
    bodies.push(source.slice(start, close));
  }
  return bodies;
}

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
