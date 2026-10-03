/** Geometry helpers shared by the SVG charts. */
import { useEffect, useRef, useState } from 'react';

/** Width of a container, kept up to date. */
export function useWidth<T extends HTMLElement>(fallback = 720): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => setWidth(Math.max(280, Math.floor(entries[0].contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** Horizontal bar path with a square start at x0 and a rounded end at x1. */
export function barPath(x0: number, x1: number, y: number, height: number, radius = 4): string {
  const width = Math.max(0, x1 - x0);
  const r = Math.min(radius, width, height / 2);
  if (width <= 0) return '';
  return `M${x0},${y}H${x1 - r}A${r},${r} 0 0 1 ${x1},${y + r}V${y + height - r}A${r},${r} 0 0 1 ${x1 - r},${y + height}H${x0}Z`;
}

/** Nice tick values from 0 to max. */
export function ticks(max: number, count = 5): number[] {
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(6)));
  return out;
}
