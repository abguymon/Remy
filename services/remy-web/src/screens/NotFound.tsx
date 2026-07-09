import { Link } from 'react-router-dom'
import { EmptyState } from '../components/ui'

export default function NotFound() {
  return (
    <div className="px-5 py-16">
      <EmptyState
        glyph="🧭"
        message="Nothing here."
        action={
          <Link to="/" className="mt-1 text-[13.5px] font-semibold text-terracotta">
            Back to Plan
          </Link>
        }
      />
    </div>
  )
}
