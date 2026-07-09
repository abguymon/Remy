// Small display helpers. Prices always tabular + 2dp (DESIGN_BRIEF §3).

export function money(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${n.toFixed(2)}`
}

export function pluralize(n: number, singular: string, plural?: string): string {
  return `${n} ${n === 1 ? singular : (plural ?? `${singular}s`)}`
}

// Kroger stock levels → the four review pills. Anything unknown reads as
// "stock unknown" rather than pretending it's in stock (honesty, FR-16).
export function stockLabel(level: string | null | undefined): string {
  switch ((level ?? '').toUpperCase()) {
    case 'HIGH':
      return 'In stock'
    case 'MEDIUM':
      return 'In stock'
    case 'LOW':
      return 'Low stock'
    default:
      return 'Stock unknown'
  }
}
