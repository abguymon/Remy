import { Link } from 'react-router-dom'
import Icon from '../components/Icon'
import type { IconName } from '../components/Icon'
import RatIcon from '../components/RatIcon'
import { useAuth } from '../stores/auth'

// Public marketing page. Editorial-cookbook register (DESIGN_BRIEF §8): cream
// canvas, Newsreader display type, real recipe photography from /landing/*.
// Every color is a theme token so the page follows light/dark.

const steps: { number: string; icon: IconName; title: string; body: string }[] = [
  {
    number: '01',
    icon: 'edit',
    title: 'Name the meals',
    body: 'Type whatever sounds good, from “tacos” to a recipe link you already love.',
  },
  {
    number: '02',
    icon: 'book',
    title: 'Pick your recipes',
    body: 'Compare ideas from the web and your cookbook. You choose what makes the cut.',
  },
  {
    number: '03',
    icon: 'list',
    title: 'Tidy the list',
    body: 'Remy combines duplicate ingredients and sets pantry staples aside for review.',
  },
  {
    number: '04',
    icon: 'cart',
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

const promises: { icon: IconName; title: string; body: string }[] = [
  { icon: 'edit', title: 'Plan with plain language', body: 'No forms or rigid weekly calendar.' },
  { icon: 'check', title: 'Stay in control', body: 'Review every recipe, ingredient, and product.' },
  { icon: 'store', title: 'Checkout stays familiar', body: 'Finish pickup and payment with your grocery store.' },
]

const eyebrow = 'text-[11.5px] font-bold uppercase tracking-[.14em] text-terracotta-deep'

function Arrow({ size = 18 }: { size?: number }) {
  // Icon.tsx has no forward arrow; the back chevron flipped reads as "go".
  return <Icon name="chevronRight" size={size} strokeWidth={2.2} />
}

export default function Landing() {
  const signedIn = Boolean(useAuth((state) => state.token))
  const appLabel = signedIn ? 'Open Remy' : 'Sign in'
  const appHref = signedIn ? '/app' : '/login'

  return (
    <div className="min-h-full overflow-x-hidden bg-cream text-ink">
      <header className="sticky top-0 z-20 border-b border-line bg-cream/90 backdrop-blur">
        <div className="mx-auto flex h-[68px] max-w-[1180px] items-center justify-between px-4 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5" aria-label="Remy home">
            <RatIcon size={30} className="text-terracotta" />
            <span className="font-serif text-[27px] font-medium tracking-[-0.02em]">Remy</span>
          </Link>
          <nav className="flex items-center gap-2 sm:gap-7" aria-label="Main navigation">
            <a
              href="#how-it-works"
              className="hidden text-[13.5px] font-semibold text-muted transition-colors hover:text-ink sm:block"
            >
              How it works
            </a>
            <a
              href="#getting-started"
              className="hidden text-[13.5px] font-semibold text-muted transition-colors hover:text-ink md:block"
            >
              Getting started
            </a>
            <Link
              to={appHref}
              className="inline-flex h-11 items-center justify-center gap-1 rounded-full bg-ink pl-5 pr-4 text-[14px] font-semibold text-cream transition-opacity hover:opacity-90"
            >
              {appLabel} <Arrow size={16} />
            </Link>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section>
          <div className="mx-auto grid max-w-[1180px] gap-14 px-4 pb-20 pt-12 sm:px-8 sm:pt-20 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:gap-16 lg:pb-28">
            <div>
              <div className={eyebrow}>Your weeknight sous-chef</div>
              <h1 className="mt-4 max-w-[640px] font-serif text-[52px] font-medium leading-[.98] tracking-[-0.03em] sm:text-[72px] lg:text-[82px]">
                Dinner ideas in.
                <span className="block italic text-terracotta-deep">Groceries out.</span>
              </h1>
              <p className="mt-6 max-w-[540px] text-[17px] leading-7 text-muted sm:text-[18.5px] sm:leading-8">
                Remy turns the meals you want to cook into a reviewed, ready-to-shop grocery
                cart—without taking the choices away from you.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Link
                  to={appHref}
                  className="inline-flex h-[54px] items-center justify-center gap-1.5 rounded-[14px] bg-terracotta px-7 text-[15.5px] font-semibold text-onaccent shadow-terracotta transition-colors hover:bg-terracotta-dark"
                >
                  {appLabel} <Arrow />
                </Link>
                <a
                  href="#how-it-works"
                  className="inline-flex h-[54px] items-center justify-center rounded-[14px] border border-line2 bg-surface px-7 text-[15.5px] font-semibold text-ink transition-colors hover:bg-chip"
                >
                  See how it works
                </a>
              </div>
              <p className="mt-5 text-[13px] text-faint">
                Private and invitation-only. Built for friends, family, and real-life kitchens.
              </p>
            </div>

            <ProductStory />
          </div>
        </section>

        {/* Promises */}
        <section className="border-y border-line bg-surface">
          <div className="mx-auto grid max-w-[1180px] divide-y divide-line px-4 sm:grid-cols-3 sm:divide-x sm:divide-y-0 sm:px-8">
            {promises.map(({ icon, title, body }) => (
              <div key={title} className="flex gap-3.5 py-6 sm:px-7 sm:first:pl-0 sm:last:pr-0">
                <span className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-terracotta-soft text-terracotta-deep">
                  <Icon name={icon} size={18} />
                </span>
                <div>
                  <div className="text-[14.5px] font-bold text-ink">{title}</div>
                  <div className="mt-0.5 text-[13.5px] leading-5 text-muted">{body}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-20 px-4 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[1180px]">
            <div className="max-w-[680px]">
              <div className={eyebrow}>From craving to cart</div>
              <h2 className="mt-3 font-serif text-[40px] font-medium leading-[1.04] tracking-[-0.025em] sm:text-[54px]">
                Four small decisions.
                <br />
                <span className="italic text-muted">One much easier grocery run.</span>
              </h2>
            </div>

            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {steps.map((step) => (
                <article
                  key={step.number}
                  className="flex flex-col rounded-card sm:min-h-[236px] border border-line bg-surface p-6 shadow-card"
                >
                  <div className="flex items-center justify-between">
                    <span className="flex h-11 w-11 items-center justify-center rounded-full bg-chip text-ink">
                      <Icon name={step.icon} size={20} strokeWidth={1.9} />
                    </span>
                    <span className="tab-fig font-serif text-[22px] italic text-faint">{step.number}</span>
                  </div>
                  <div className="mt-auto pt-6 font-serif sm:pt-10 text-[24px] font-medium leading-tight tracking-[-0.01em]">
                    {step.title}
                  </div>
                  <p className="mt-2 text-[14px] leading-6 text-muted">{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Helper, not autopilot */}
        <section className="border-y border-line bg-surface px-4 py-20 sm:px-8 sm:py-24">
          <div className="mx-auto grid max-w-[1100px] gap-10 lg:grid-cols-[.9fr_1.1fr] lg:items-center lg:gap-16">
            <figure className="relative">
              <img
                src="/landing/bibimbap.jpg"
                alt="Sheet-pan bibimbap with a fried egg, roasted vegetables and rice"
                loading="lazy"
                className="aspect-[4/3] w-full rounded-panel bg-tile object-cover lg:aspect-[4/5]"
              />
              <figcaption className="absolute bottom-3 left-3 rounded-full bg-surface/85 px-3 py-1.5 text-[12px] font-semibold text-ink backdrop-blur">
                Sheet-Pan Bibimbap
              </figcaption>
            </figure>
            <div>
              <div className={eyebrow}>A helper, not autopilot</div>
              <h2 className="mt-3 max-w-[520px] font-serif text-[38px] font-medium leading-[1.05] tracking-[-0.025em] sm:text-[50px]">
                Remy does the busywork. You make the calls.
              </h2>
              <p className="mt-5 max-w-[500px] text-[15.5px] leading-7 text-muted">
                Grocery shopping has too many tiny steps. Remy connects them while keeping the
                important choices visible and reversible.
              </p>
              <div className="mt-9 grid gap-8 sm:grid-cols-2 sm:gap-6">
                <List title="Remy handles" icon="sparkle" items={handled} tone="accent" />
                <List title="You decide" icon="user" items={yours} tone="success" />
              </div>
            </div>
          </div>
        </section>

        {/* Getting started */}
        <section id="getting-started" className="scroll-mt-20 px-4 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto grid max-w-[1100px] gap-12 lg:grid-cols-[.85fr_1.15fr] lg:gap-20">
            <div>
              <div className={eyebrow}>Your first week</div>
              <h2 className="mt-3 font-serif text-[38px] font-medium leading-[1.05] tracking-[-0.025em] sm:text-[50px]">
                Start with an invitation. Be planning in minutes.
              </h2>
              <p className="mt-5 text-[15.5px] leading-7 text-muted">
                Remy is a private household tool, so there is no public sign-up. An invitation
                creates your account; after that, your cookbook and plans are waiting whenever you
                sign in.
              </p>
            </div>
            <ol className="overflow-hidden rounded-panel border border-line bg-surface shadow-card">
              {[
                ['Open your invitation', 'Choose a username and a secure password.'],
                ['Connect your grocery account', 'Pick your preferred store and pickup method in Settings.'],
                ['Tell Remy what sounds good', 'A loose list is enough—Remy will help with the recipes.'],
                ['Review, add, and check out', 'Approve the cart, then schedule and pay on your store’s site.'],
              ].map(([title, body], index) => (
                <li
                  key={title}
                  className="grid grid-cols-[44px_1fr] items-start gap-3 border-b border-divider px-5 py-5 last:border-0 sm:px-7"
                >
                  <span className="tab-fig flex h-9 w-9 items-center justify-center rounded-full bg-terracotta-soft font-serif text-[17px] font-medium text-terracotta-deep">
                    {index + 1}
                  </span>
                  <div>
                    <div className="font-serif text-[19px] font-medium leading-snug">{title}</div>
                    <div className="mt-1 text-[13.5px] leading-5 text-muted">{body}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Closing CTA */}
        <section className="px-4 pb-20 sm:px-8 sm:pb-28">
          <div className="mx-auto grid max-w-[1100px] overflow-hidden rounded-panel bg-terracotta text-onaccent md:grid-cols-[1.25fr_.75fr]">
            <div className="px-6 py-12 sm:px-12 sm:py-14">
              <RatIcon size={44} hole="rgb(var(--c-terracotta))" className="text-onaccent" />
              <h2 className="mt-5 font-serif text-[36px] font-medium leading-[1.05] tracking-[-0.025em] sm:text-[48px]">
                Ready to make this week easier?
              </h2>
              <p className="mt-3 max-w-[480px] text-[15.5px] leading-6 opacity-90">
                Bring the dinner ideas. Remy will help with everything between the recipe and the
                pickup window.
              </p>
              <Link
                to={appHref}
                className="mt-7 inline-flex h-[52px] items-center justify-center gap-1.5 rounded-[14px] bg-surface px-7 text-[15px] font-semibold text-ink transition-colors hover:bg-cream"
              >
                {appLabel} <Arrow />
              </Link>
            </div>
            <img
              src="/landing/carrot-risotto.jpg"
              alt=""
              loading="lazy"
              className="hidden h-full w-full bg-tile object-cover md:block"
            />
          </div>
        </section>
      </main>

      <footer className="border-t border-line px-4 py-8 sm:px-8">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-3 text-[12.5px] text-faint sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 font-semibold text-muted">
            <RatIcon size={20} className="text-terracotta" />
            <span>
              <span className="font-serif text-[15px] font-medium text-ink">Remy</span> · Meals in. Groceries out.
            </span>
          </div>
          <div>Made for quieter weeknights and better dinners.</div>
        </div>
      </footer>
    </div>
  )
}

const weekMeals = [
  { title: 'Lemony asparagus orzo', day: 'Tuesday', img: '/landing/lemony-orzo.jpg' },
  { title: 'Massaman chicken curry', day: 'Thursday', img: '/landing/massaman-curry.jpg' },
  { title: 'Easy gazpacho', day: 'Saturday', img: '/landing/gazpacho.jpg' },
]

function ProductStory() {
  return (
    <div className="relative mx-auto w-full max-w-[540px] lg:mx-0 lg:ml-auto">
      <img
        src="/landing/pasta-norma.jpg"
        alt="Pasta alla Norma with eggplant, tomato and ricotta salata"
        className="aspect-[4/3] w-full rounded-panel bg-tile object-cover sm:aspect-[5/4] lg:aspect-[4/5]"
      />
      <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-surface/85 px-3 py-1.5 text-[12px] font-semibold text-ink backdrop-blur">
        <Icon name="clock" size={13} /> Pasta alla Norma · 45 min
      </span>

      {/* "This week" plan card, overlapping the photo */}
      <div className="relative -mt-16 ml-3 mr-3 rounded-card border border-line bg-surface p-4 shadow-card sm:ml-auto sm:mr-6 sm:w-[340px] lg:absolute lg:-bottom-10 lg:-left-12 lg:mt-0 lg:w-[330px]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-serif text-[21px] font-medium leading-tight tracking-[-0.01em]">This week</div>
            <div className="mt-0.5 text-[12px] text-faint">3 dinners · 18 groceries</div>
          </div>
          <span className="inline-flex items-center gap-1 rounded-full bg-success-bg px-2.5 py-1 text-[11px] font-bold text-success">
            <Icon name="check" size={12} strokeWidth={2.6} /> Ready to review
          </span>
        </div>
        <ul className="mt-3.5 space-y-2.5">
          {weekMeals.map((meal) => (
            <li key={meal.title} className="flex items-center gap-3">
              <img src={meal.img} alt="" className="h-11 w-11 flex-none rounded-[10px] bg-tile object-cover" />
              <span className="min-w-0 flex-1 truncate font-serif text-[15.5px] font-medium">{meal.title}</span>
              <span className="text-[11.5px] font-semibold text-faint">{meal.day}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3.5 flex items-center justify-between border-t border-divider pt-3 text-[12.5px]">
          <span className="inline-flex items-center gap-1.5 font-semibold text-muted">
            <Icon name="cart" size={15} /> Matched cart
          </span>
          <span className="tab-fig font-bold text-ink">$64.20</span>
        </div>
      </div>

      <div className="absolute -right-2 top-[38%] hidden items-center gap-2 rounded-full border border-line bg-surface py-2 pl-2 pr-3.5 shadow-card sm:flex lg:-right-6">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-terracotta-soft text-terracotta-deep">
          <Icon name="pantry" size={15} />
        </span>
        <span className="text-[12px] font-semibold leading-tight">
          <span className="block text-[10.5px] font-bold uppercase tracking-[.1em] text-faint">Pantry check</span>
          Salt &amp; olive oil skipped
        </span>
      </div>
    </div>
  )
}

function List({
  title,
  icon,
  items,
  tone,
}: {
  title: string
  icon: IconName
  items: string[]
  tone: 'accent' | 'success'
}) {
  const toneCls = tone === 'accent' ? 'bg-terracotta-soft text-terracotta-deep' : 'bg-success-bg text-success'
  return (
    <div>
      <div className="flex items-center gap-2 text-[11.5px] font-bold uppercase tracking-[.13em] text-faint">
        <Icon name={icon} size={15} /> {title}
      </div>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5 text-[14px] leading-5 text-ink">
            <span className={`mt-px flex h-5 w-5 flex-none items-center justify-center rounded-full ${toneCls}`} aria-hidden>
              <Icon name="check" size={12} strokeWidth={2.6} />
            </span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
