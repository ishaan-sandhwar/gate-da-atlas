/** Numeric helpers that reproduce Python's behaviour exactly where the plan depends on it. */

/** Python's round(x): round half to even. */
export function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** Python's round(x, digits) for the small, well-behaved values used here. */
export function roundTo(value: number, digits: number): number {
  const scale = 10 ** digits;
  return roundHalfEven(value * scale) / scale;
}

/** First element with the largest key, like Python's max(iterable, key=...). */
export function maxBy<T>(values: T[], key: (value: T) => number): T {
  let best = values[0];
  let bestKey = key(best);
  for (const value of values.slice(1)) {
    const k = key(value);
    if (k > bestKey) {
      best = value;
      bestKey = k;
    }
  }
  return best;
}

/** Sum of numbers. */
export function sum(values: Iterable<number>): number {
  let total = 0;
  for (const value of values) total += value;
  return total;
}
