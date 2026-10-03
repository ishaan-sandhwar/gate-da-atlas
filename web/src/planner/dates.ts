/** Calendar dates as ISO strings (yyyy-mm-dd), computed in UTC so time zones never shift a day. */

const DAY_MS = 86_400_000;

/** Parse an ISO date into a UTC timestamp at midnight. */
export function toTime(iso: string): number {
  const [year, month, day] = iso.split('-').map(Number);
  return Date.UTC(year, month - 1, day);
}

/** Format a UTC timestamp as an ISO date. */
export function toIso(time: number): string {
  return new Date(time).toISOString().slice(0, 10);
}

/** ISO date plus a number of days. */
export function addDays(iso: string, days: number): string {
  return toIso(toTime(iso) + days * DAY_MS);
}

/** Whole days from `start` to `end` (end - start). */
export function daysBetween(start: string, end: string): number {
  return Math.round((toTime(end) - toTime(start)) / DAY_MS);
}

/** Today's date in the viewer's own time zone, as ISO. */
export function todayIso(): string {
  const now = new Date();
  return toIso(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}
