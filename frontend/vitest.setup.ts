import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

/**
 * jsdom implements neither ResizeObserver nor WebGL. The trajectory viewer needs the first
 * to size its canvas and the second to render at all, so both are stubbed here. Component
 * tests can then assert structure and states. Anything about what is actually drawn has to
 * be checked in a real browser, which is what the Playwright suite is for.
 */

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

if (!HTMLCanvasElement.prototype.getContext) {
  HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as never;
}

globalThis.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof globalThis.matchMedia;
