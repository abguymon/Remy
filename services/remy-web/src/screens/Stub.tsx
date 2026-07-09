// Placeholder for the screens T8 owns (Cookbook, Cart record, Settings).
import { EmptyState } from '../components/ui'

export default function Stub({ title, glyph }: { title: string; glyph: string }) {
  return (
    <div className="px-5 py-4">
      <div className="font-serif text-[28px] font-semibold tracking-tight">{title}</div>
      <div className="mt-6">
        <EmptyState glyph={glyph} message="Coming in T8." />
      </div>
    </div>
  )
}
