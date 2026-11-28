export const TZ = 'America/Los_Angeles'
// Same window compute_headways.py uses for service.
export const WINDOW_START_MIN = 7 * 60 + 30
export const WINDOW_END_MIN = 22 * 60

const fmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export function pacific(ms: number): { day: string; minute: number } {
  const p: Record<string, string> = {}
  for (const part of fmt.formatToParts(new Date(ms))) p[part.type] = part.value
  return { day: `${p.year}-${p.month}-${p.day}`, minute: Number(p.hour) * 60 + Number(p.minute) }
}

export function inWindow(ms: number): boolean {
  const { minute } = pacific(ms)
  return minute >= WINDOW_START_MIN && minute < WINDOW_END_MIN
}

// UTC ms of a Pacific wall-clock time on a Pacific day ("2026-11-29", "14:10").
export function pacificToMs(day: string, hhmm: string): number {
  const [y, mo, d] = day.split('-').map(Number)
  const [h, mi] = hhmm.split(':').map(Number)
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  // Offset is -7h or -8h; correct the guess by what it reads as in Pacific time.
  for (const off of [7, 8]) {
    const ms = guess + off * 3600_000
    const p = pacific(ms)
    if (p.day === day && p.minute === h * 60 + mi) return ms
  }
  return guess + 8 * 3600_000
}

export function addDays(day: string, n: number): string {
  const [y, mo, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, d + n)).toISOString().slice(0, 10)
}
