import { Link } from 'react-router-dom'
import RatIcon from '../components/RatIcon'
import { useAuth } from '../stores/auth'

const steps = [
  {
    number: '01',
    title: 'Name the meals',
    body: 'Type whatever sounds good, from “tacos” to a recipe link you already love.',
  },
  {
    number: '02',
    title: 'Pick your recipes',
    body: 'Compare ideas from the web and your cookbook. You choose what makes the cut.',
  },
  {
    number: '03',
    title: 'Tidy the list',
    body: 'Remy combines duplicate ingredients and sets pantry staples aside for review.',
  },
  {
    number: '04',
    title: 'Approve the cart',
    body: 'Check the real products, prices, and substitutions before anything is added.',
  },
]

const handled = [
  'Finding useful recipe options',
  'Saving recipes to your cookbook',
  'Combining ingredients across meals',
  'Matching groceries at your store',
]

const yours = [
  'Choosing what you actually want to cook',
  'Editing quantities and pantry items',
  'Approving products and substitutions',
  'Scheduling pickup and checking out',
]

export default function Landing() {
  const signedIn = Boolean(useAuth((state) => state.token))
  const appLabel = signedIn ? 'Open Remy' : 'Sign in'
  const appHref = signedIn ? '/app' : '/login'

  return (
    <div className="min-h-full overflow-x-hidden bg-cream text-ink">
      <header className="relative z-20 border-b border-line/80 bg-cream/90 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-[1180px] items-center justify-between px-5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5" aria-label="Remy home">
            <RatIcon size={31} hole="#F6F0E8" className="text-terracotta" />
            <span className="font-serif text-[28px] font-semibold tracking-tight">Remy</span>
          </Link>
          <nav className="flex items-center gap-2 sm:gap-6" aria-label="Main navigation">
            <a
              href="#how-it-works"
              className="hidden text-sm font-semibold text-muted transition-colors hover:text-ink sm:block"
            >
              How it works
            </a>
            <a
              href="#getting-started"
              className="hidden text-sm font-semibold text-muted transition-colors hover:text-ink md:block"
            >
              Getting started
            </a>
            <Link
              to={appHref}
              className="inline-flex min-h-11 items-center justify-center rounded-full bg-ink px-5 text-sm font-bold text-surface transition-transform hover:-translate-y-0.5"
            >
              {appLabel} <span aria-hidden className="ml-1.5">→</span>
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="relative isolate">
          <div className="absolute inset-x-0 top-0 -z-10 h-[88%] bg-[radial-gradient(circle_at_82%_20%,rgba(192,91,59,.13),transparent_38%),radial-gradient(circle_at_15%_80%,rgba(122,106,43,.09),transparent_31%)]" />
          <div className="mx-auto grid max-w-[1180px] gap-12 px-5 pb-20 pt-16 sm:px-8 sm:pt-24 lg:grid-cols-[1.02fr_.98fr] lg:items-center lg:gap-16 lg:pb-28">
            <div>
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#DCCFC0] bg-surface/75 px-3.5 py-2 text-[12px] font-bold uppercase tracking-[0.12em] text-terracotta-deep shadow-cardsoft">
                <span className="h-1.5 w-1.5 rounded-full bg-terracotta" aria-hidden />
                Your weeknight sous-chef
              </div>
              <h1 className="max-w-[680px] font-serif text-[49px] font-semibold leading-[.97] tracking-[-.035em] sm:text-[68px] lg:text-[76px]">
                Dinner ideas in.
                <span className="block italic text-terracotta">Groceries out.</span>
              </h1>
              <p className="mt-7 max-w-[610px] text-[17px] leading-7 text-muted sm:text-[19px] sm:leading-8">
                Remy turns the meals you want to cook into a reviewed, ready-to-shop grocery
                cart—without taking the choices away from you.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Link
                  to={appHref}
                  className="inline-flex min-h-[52px] items-center justify-center rounded-full bg-terracotta px-7 text-[15px] font-bold text-white shadow-terracotta transition hover:bg-terracotta-dark"
                >
                  {appLabel} <span aria-hidden className="ml-2">→</span>
                </Link>
                <a
                  href="#how-it-works"
                  className="inline-flex min-h-[52px] items-center justify-center rounded-full border border-line2 bg-surface/60 px-7 text-[15px] font-bold text-ink transition hover:bg-surface"
                >
                  See how it works
                </a>
              </div>
              <p className="mt-4 text-[13px] text-faint">
                Private and invitation-only. Built for friends, family, and real-life kitchens.
              </p>
            </div>

            <ProductStory />
          </div>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="mx-auto grid max-w-[1180px] divide-y divide-line px-5 sm:grid-cols-3 sm:divide-x sm:divide-y-0 sm:px-8">
            {[
              ['Plan with plain language', 'No forms or rigid weekly calendar.'],
              ['Stay in control', 'Review every recipe, ingredient, and product.'],
              ['Checkout stays familiar', 'Finish pickup and payment with your grocery store.'],
            ].map(([title, body]) => (
              <div key={title} className="py-6 sm:px-7 sm:first:pl-0 sm:last:pr-0">
                <div className="text-[14px] font-bold text-ink">{title}</div>
                <div className="mt-1 text-[13px] leading-5 text-muted">{body}</div>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 px-5 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[1180px]">
            <div className="max-w-[650px]">
              <div className="text-[12px] font-bold uppercase tracking-[.15em] text-terracotta">
                From craving to cart
              </div>
              <h2 className="mt-3 font-serif text-[39px] font-semibold leading-[1.04] tracking-tight sm:text-[52px]">
                Four small decisions.
                <br />
                One much easier grocery run.
              </h2>
            </div>

            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {steps.map((step) => (
                <article
                  key={step.number}
                  className="group min-h-[235px] rounded-panel border border-line bg-surface p-6 shadow-cardsoft transition-transform hover:-translate-y-1"
                >
                  <div className="font-mono text-[11px] font-bold tracking-[.12em] text-terracotta">
                    {step.number}
                  </div>
                  <div className="mt-12 font-serif text-[24px] font-semibold leading-tight">
                    {step.title}
                  </div>
                  <p className="mt-3 text-[14px] leading-6 text-muted">{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-ink px-5 py-20 text-surface sm:px-8 sm:py-24">
          <div className="mx-auto grid max-w-[1050px] gap-12 lg:grid-cols-[.9fr_1.1fr] lg:items-start">
            <div>
              <div className="text-[12px] font-bold uppercase tracking-[.15em] text-[#E48A6D]">
                A helper, not autopilot
              </div>
              <h2 className="mt-4 max-w-[450px] font-serif text-[40px] font-semibold leading-[1.04] tracking-tight sm:text-[50px]">
                Remy does the busywork. You make the calls.
              </h2>
              <p className="mt-5 max-w-[480px] text-[15px] leading-7 text-[#C9BEB1]">
                Grocery shopping has too many tiny steps. Remy connects them while keeping the
                important choices visible and reversible.
              </p>
            </div>
            <div className="grid overflow-hidden rounded-panel border border-white/10 bg-white/[.04] sm:grid-cols-2">
              <List title="Remy handles" items={handled} accent="text-[#E48A6D]" />
              <List title="You decide" items={yours} accent="text-[#A9B481]" border />
            </div>
          </div>
        </section>

        <section id="getting-started" className="scroll-mt-20 px-5 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto grid max-w-[1050px] gap-12 lg:grid-cols-[.85fr_1.15fr] lg:gap-20">
            <div>
              <div className="text-[12px] font-bold uppercase tracking-[.15em] text-terracotta">
                Your first week
              </div>
              <h2 className="mt-3 font-serif text-[40px] font-semibold leading-[1.04] tracking-tight sm:text-[50px]">
                Start with an invitation. Be planning in minutes.
              </h2>
              <p className="mt-5 text-[15px] leading-7 text-muted">
                Remy is a private household tool, so there is no public sign-up. An invitation
                creates your account; after that, your cookbook and plans are waiting whenever you
                sign in.
              </p>
            </div>
            <ol className="overflow-hidden rounded-panel border border-line bg-surface shadow-cardsoft">
              {[
                ['Open your invitation', 'Choose a username and a secure password.'],
                ['Connect your grocery account', 'Pick your preferred store and pickup method in Settings.'],
                ['Tell Remy what sounds good', 'A loose list is enough—Remy will help with the recipes.'],
                ['Review, add, and check out', 'Approve the cart, then schedule and pay on your store’s site.'],
              ].map(([title, body], index) => (
                <li
                  key={title}
                  className="grid grid-cols-[42px_1fr] gap-3 border-b border-divider px-5 py-5 last:border-0 sm:px-7"
                >
                  <span className="tab-fig flex h-8 w-8 items-center justify-center rounded-full bg-terracotta-soft text-[12px] font-bold text-terracotta-deep">
                    {index + 1}
                  </span>
                  <div>
                    <div className="text-[15px] font-bold">{title}</div>
                    <div className="mt-1 text-[13.5px] leading-5 text-muted">{body}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="px-5 pb-20 sm:px-8 sm:pb-28">
          <div className="mx-auto max-w-[1050px] overflow-hidden rounded-[24px] bg-terracotta px-6 py-12 text-center text-white shadow-terracotta sm:px-12 sm:py-16">
            <RatIcon size={46} hole="#C05B3B" className="mx-auto text-white/90" />
            <h2 className="mt-4 font-serif text-[38px] font-semibold leading-tight tracking-tight sm:text-[48px]">
              Ready to make this week easier?
            </h2>
            <p className="mx-auto mt-3 max-w-[540px] text-[15px] leading-6 text-white/80">
              Bring the dinner ideas. Remy will help with everything between the recipe and the
              pickup window.
            </p>
            <Link
              to={appHref}
              className="mt-7 inline-flex min-h-[50px] items-center justify-center rounded-full bg-surface px-7 text-[15px] font-bold text-ink transition-transform hover:-translate-y-0.5"
            >
              {appLabel} <span aria-hidden className="ml-2">→</span>
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-line px-5 py-8 sm:px-8">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-3 text-[12px] text-faint sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 font-semibold text-muted">
            <RatIcon size={20} hole="#F6F0E8" className="text-terracotta" />
            Remy · Meals in. Groceries out.
          </div>
          <div>Made for quieter weeknights and better dinners.</div>
        </div>
      </footer>
    </div>
  )
}

function ProductStory() {
  return (
    <div className="relative mx-auto w-full max-w-[560px] lg:mx-0">
      <div className="absolute -left-5 top-10 h-28 w-28 rounded-full bg-[#C5B985]/25 blur-2xl" />
      <div className="absolute -right-6 bottom-5 h-36 w-36 rounded-full bg-terracotta/20 blur-2xl" />
      <div className="relative rotate-[1.5deg] rounded-[22px] border border-[#D8CBBB] bg-surface p-3 shadow-[0_24px_65px_rgba(67,48,31,.15)] sm:p-4">
        <div className="rounded-[17px] border border-line bg-cream p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-serif text-[22px] font-semibold">This week</div>
              <div className="mt-0.5 text-[11px] text-faint">3 dinners · 18 groceries</div>
            </div>
            <div className="rounded-full bg-success-bg px-3 py-1.5 text-[10px] font-bold text-success">
              Ready to review
            </div>
          </div>

          <div className="mt-5 grid grid-cols-[1fr_auto] gap-2">
            {[
              ['Lemony chicken & orzo', 'Tuesday'],
              ['Black bean tacos', 'Thursday'],
              ['Miso salmon bowls', 'Saturday'],
            ].map(([meal, day]) => (
              <div
                key={meal}
                className="col-span-2 grid grid-cols-subgrid items-center rounded-xl border border-line bg-surface px-3.5 py-3"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-terracotta-soft text-sm">
                    {meal.includes('chicken') ? '🍋' : meal.includes('tacos') ? '🌮' : '🍚'}
                  </span>
                  <span className="text-[12px] font-bold sm:text-[13px]">{meal}</span>
                </div>
                <span className="text-[10px] font-semibold text-faint">{day}</span>
              </div>
            ))}
          </div>

          <div className="my-4 flex items-center gap-2 px-1" aria-hidden>
            <span className="h-px flex-1 bg-line" />
            <span className="text-[9px] font-bold uppercase tracking-[.12em] text-hint">
              becomes
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-xl border border-line bg-surface p-3.5">
              <div className="mb-2.5 text-[10px] font-bold uppercase tracking-[.1em] text-faint">
                Grocery list
              </div>
              {['Chicken thighs', '2 limes', 'Greek yogurt'].map((item) => (
                <div key={item} className="flex items-center gap-2 border-t border-divider py-2 text-[11px]">
                  <span className="flex h-3.5 w-3.5 items-center justify-center rounded bg-success text-[9px] text-white">
                    ✓
                  </span>
                  {item}
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-line bg-surface p-3.5">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-[.1em] text-faint">
                  Matched cart
                </span>
                <span className="tab-fig text-[11px] font-bold">$64.20</span>
              </div>
              {[
                ['🍗', 'Boneless thighs'],
                ['🥛', 'Plain yogurt'],
                ['🥬', 'Fresh cilantro'],
              ].map(([glyph, item]) => (
                <div key={item} className="flex items-center gap-2 border-t border-divider py-2 text-[11px]">
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-cream">{glyph}</span>
                  <span className="truncate">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="absolute -bottom-5 -left-2 -rotate-3 rounded-xl border border-[#D8CBBB] bg-[#FFF9EF] px-4 py-3 shadow-[0_10px_25px_rgba(67,48,31,.12)] sm:-left-7">
        <div className="text-[9px] font-bold uppercase tracking-[.12em] text-terracotta">Pantry check</div>
        <div className="mt-0.5 text-[11px] font-semibold">Salt & olive oil skipped ✓</div>
      </div>
    </div>
  )
}

function List({
  title,
  items,
  accent,
  border = false,
}: {
  title: string
  items: string[]
  accent: string
  border?: boolean
}) {
  return (
    <div className={`p-6 sm:p-7 ${border ? 'border-t border-white/10 sm:border-l sm:border-t-0' : ''}`}>
      <div className={`text-[12px] font-bold uppercase tracking-[.13em] ${accent}`}>{title}</div>
      <ul className="mt-5 space-y-4">
        {items.map((item) => (
          <li key={item} className="flex gap-3 text-[13.5px] leading-5 text-[#E7DED4]">
            <span className={accent} aria-hidden>✓</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
