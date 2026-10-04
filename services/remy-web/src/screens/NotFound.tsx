import { Link } from 'react-router-dom'
import { EmptyState, ScreenHeader } from '../components/ui'

export default function NotFound() {
  return (
    <div className="pb-16">
      <ScreenHeader title="Page not found" subtitle="That link doesn’t lead anywhere in Remy." />
      <div className="px-5 pt-6">
        <EmptyState
          icon="utensils"
          message="Nothing here."
          action={
            <Link
              to="/app"
              className="mt-2 inline-flex h-11 items-center justify-center rounded-[14px] bg-terracotta px-5 text-[14px] font-semibold text-onaccent shadow-terracotta transition-colors hover:bg-terracotta-dark"
            >
              Back to Plan
            </Link>
          }
        />
      </div>
    </div>
  )
}
