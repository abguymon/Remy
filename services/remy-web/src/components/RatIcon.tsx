// The Remy mark — a simple sitting rat. Inherits color via currentColor so it
// can sit next to the wordmark in any register; eye/inner-ear knock out to the
// page background via the `hole` prop (defaults to the cream canvas).
export default function RatIcon({ size = 28, hole = '#F6F0E8', className = '' }: {
  size?: number
  hole?: string
  className?: string
}) {
  return (
    <svg viewBox="0 0 68 64" width={size} height={(size * 64) / 68} className={className} aria-hidden="true">
      <g fill="currentColor">
        <circle cx="28" cy="18" r="8" />
        <path d="M4 44 C 8 34, 18 26, 28 25 C 42 23, 54 30, 56 40 C 57 48, 51 54, 41 55 L 18 55 C 10 55, 2 50, 4 44 Z" />
      </g>
      <circle cx="28" cy="18" r="3.5" fill={hole} />
      <circle cx="16" cy="42" r="2.6" fill={hole} />
      <path
        d="M55 47 C 64 50, 65 58, 55 59 C 48 60, 46 56, 48 53"
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  )
}
