// Small display helpers. Prices always tabular + 2dp (DESIGN_BRIEF §3).

export function money(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${n.toFixed(2)}`
}

export function pluralize(n: number, singular: string, plural?: string): string {
  return `${n} ${n === 1 ? singular : (plural ?? `${singular}s`)}`
}

// Short "Mon D" date, e.g. "Jul 8" — used for order history + last-cooked.
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// "Cooked Jul 8" if a last-cooked stamp exists, otherwise "New".
export function cookedLabel(iso: string | null | undefined): string {
  return iso ? `Cooked ${shortDate(iso)}` : 'New'
}

// Display label for a Kroger cart handoff URL — the bare host without "www.",
// e.g. "https://www.fredmeyer.com/cart" → "fredmeyer.com". The API owns the
// URL→banner mapping; this only formats it for copy like "lives on fredmeyer.com".
export function cartHost(url: string | null | undefined): string {
  if (!url) return 'kroger.com'
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'kroger.com'
  }
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
