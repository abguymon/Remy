// Client-side ingredient scaling + US/metric conversion (COOKBOOK_PLAN item 2).
//
// Works from the raw line, not the stored parsed fields: about a third of
// saved lines have no parsed quantity, and the raw text is what the user sees.
// A line we can't confidently parse is shown unchanged — never a guessed number.

export type UnitSystem = 'us' | 'metric'

type Dim = 'volume' | 'weight'
interface UnitDef {
  canon: string // display label (singular)
  plural?: string
  dim?: Dim // convertible units only
  base?: number // ml or g per unit
  system?: UnitSystem
}

const UNITS: Record<string, UnitDef> = {}
function unit(names: string[], def: UnitDef) {
  for (const n of names) UNITS[n] = def
}
unit(['teaspoon', 'teaspoons', 'tsp', 'tsps', 't'], { canon: 'tsp', dim: 'volume', base: 4.93, system: 'us' })
unit(['tablespoon', 'tablespoons', 'tbsp', 'tbsps', 'tbs', 'tbl', 'T'], {
  canon: 'tbsp',
  dim: 'volume',
  base: 14.79,
  system: 'us',
})
unit(['cup', 'cups', 'c'], { canon: 'cup', plural: 'cups', dim: 'volume', base: 240, system: 'us' })
unit(['fl oz', 'fluid ounce', 'fluid ounces'], { canon: 'fl oz', dim: 'volume', base: 29.57, system: 'us' })
unit(['pint', 'pints', 'pt'], { canon: 'pint', plural: 'pints', dim: 'volume', base: 473, system: 'us' })
unit(['quart', 'quarts', 'qt'], { canon: 'quart', plural: 'quarts', dim: 'volume', base: 946, system: 'us' })
unit(['gallon', 'gallons', 'gal'], { canon: 'gallon', plural: 'gallons', dim: 'volume', base: 3785, system: 'us' })
unit(['ounce', 'ounces', 'oz'], { canon: 'oz', dim: 'weight', base: 28.35, system: 'us' })
unit(['pound', 'pounds', 'lb', 'lbs'], { canon: 'lb', dim: 'weight', base: 453.6, system: 'us' })
unit(['ml', 'milliliter', 'milliliters', 'millilitre', 'millilitres'], {
  canon: 'ml',
  dim: 'volume',
  base: 1,
  system: 'metric',
})
unit(['l', 'liter', 'liters', 'litre', 'litres'], { canon: 'l', dim: 'volume', base: 1000, system: 'metric' })
unit(['g', 'gram', 'grams', 'gr'], { canon: 'g', dim: 'weight', base: 1, system: 'metric' })
unit(['kg', 'kilogram', 'kilograms'], { canon: 'kg', dim: 'weight', base: 1000, system: 'metric' })
// Countable units: scale, never convert.
for (const [s, p] of [
  ['clove', 'cloves'],
  ['can', 'cans'],
  ['pinch', 'pinches'],
  ['dash', 'dashes'],
  ['stick', 'sticks'],
  ['slice', 'slices'],
  ['bunch', 'bunches'],
  ['sprig', 'sprigs'],
  ['handful', 'handfuls'],
  ['head', 'heads'],
  ['package', 'packages'],
  ['jar', 'jars'],
  ['piece', 'pieces'],
  ['stalk', 'stalks'],
]) {
  unit([s, p], { canon: s, plural: p })
}

const UNICODE_FRACTIONS: Record<string, number> = {
  '½': 1 / 2,
  '⅓': 1 / 3,
  '⅔': 2 / 3,
  '¼': 1 / 4,
  '¾': 3 / 4,
  '⅕': 1 / 5,
  '⅛': 1 / 8,
  '⅜': 3 / 8,
  '⅝': 5 / 8,
  '⅞': 7 / 8,
}
const UF = Object.keys(UNICODE_FRACTIONS).join('')

// One number: "1", "1.5", "1/2", "½", "1½", "1 ½", "1 1/2".
const NUM = `(?:\\d+(?:\\.\\d+)?\\s*[${UF}]|\\d+\\s+\\d+/\\d+|\\d+/\\d+|\\d+(?:\\.\\d+)?|[${UF}])`
const QTY_RE = new RegExp(`^\\s*(${NUM})(?:\\s*(?:-|–|to|or)\\s*(${NUM}))?\\s*`, 'i')

function parseNum(s: string): number {
  s = s.trim()
  const uni = s.match(new RegExp(`^(\\d+(?:\\.\\d+)?)?\\s*([${UF}])$`))
  if (uni) return (uni[1] ? parseFloat(uni[1]) : 0) + UNICODE_FRACTIONS[uni[2]]
  const mixed = s.match(/^(\d+)\s+(\d+)\/(\d+)$/)
  if (mixed) return parseInt(mixed[1]) + parseInt(mixed[2]) / parseInt(mixed[3])
  const frac = s.match(/^(\d+)\/(\d+)$/)
  if (frac) return parseInt(frac[1]) / parseInt(frac[2])
  return parseFloat(s)
}

export interface ParsedLine {
  raw: string
  qty: number | null // null = unscalable, show raw
  qty2: number | null // range upper bound ("3 or 4")
  rangeWord: string // the separator as written ("-", "to", "or")
  unit: UnitDef | null
  unitText: string // unit as written (kept when not converting)
  rest: string // everything after quantity + unit (alt measure removed)
  alt: { qty: number; qty2: number | null; unit: UnitDef } | null // "(500 ml)" right after the unit
  plus: { qty: number; unit: UnitDef; text: string } | null // "plus 2 teaspoons"
}

export function parseLine(raw: string): ParsedLine {
  const out: ParsedLine = {
    raw,
    qty: null,
    qty2: null,
    rangeWord: '',
    unit: null,
    unitText: '',
    rest: raw,
    alt: null,
    plus: null,
  }
  const m = raw.match(QTY_RE)
  if (!m) return out
  const qty = parseNum(m[1])
  if (!Number.isFinite(qty) || qty <= 0) return out
  out.qty = qty
  if (m[2]) {
    out.qty2 = parseNum(m[2])
    out.rangeWord = (m[0].match(/\b(to|or)\b|[-–]/i)?.[0] ?? '-').toLowerCase()
  }
  let rest = raw.slice(m[0].length)
  // Parenthetical size right after the number: "1 (14-ounce) can" — keep as text.
  const um = rest.match(/^(fl\.?\s*oz|fluid ounces?|[a-zA-Z]+)\.?(?=[\s,)]|$)/)
  if (um) {
    const word = um[1].replace(/\.$/, '')
    const def = UNITS[word] ?? UNITS[word.toLowerCase()] ?? UNITS[word.replace(/\s+/g, ' ').toLowerCase()]
    // Single-letter units are ambiguous ("1 c" yes, "2 g" yes, but "1 T" is tbsp
    // and "1 t" is tsp) — accept only exact-case matches for those.
    if (def && !(word.length === 1 && !(word in UNITS))) {
      out.unit = def
      out.unitText = um[0]
      rest = rest.slice(um[0].length)
    }
  }
  rest = rest.replace(/^\s+/, '')
  // An equivalent measure in parentheses, "(500 ml)" / "(75 to 90 ml)": pulled
  // out so a scaled line never shows a stale second number.
  if (out.unit?.dim) {
    const pm = rest.match(/^\(([^)]*)\)\s*/)
    if (pm) {
      const inner = parseLine(pm[1])
      // Any measured equivalent counts — "3 tablespoons (36 g)" pairs volume with weight.
      if (inner.qty != null && inner.unit?.dim && !inner.rest.trim()) {
        out.alt = { qty: inner.qty, qty2: inner.qty2, unit: inner.unit }
        rest = rest.slice(pm[0].length)
      }
    }
    const plus = rest.match(new RegExp(`^plus\\s+(${NUM})\\s*([a-zA-Z]+)\\.?\\s*`, 'i'))
    if (plus) {
      const def = UNITS[plus[2]] ?? UNITS[plus[2].toLowerCase()]
      if (def?.dim === out.unit.dim) {
        out.plus = { qty: parseNum(plus[1]), unit: def, text: plus[0] }
        rest = rest.slice(plus[0].length)
      }
    }
  }
  out.rest = rest
  return out
}

// --- Formatting ------------------------------------------------------------

const NICE_FRACTIONS: [number, string][] = [
  [0, ''],
  [1 / 8, '⅛'],
  [1 / 4, '¼'],
  [1 / 3, '⅓'],
  [3 / 8, '⅜'],
  [1 / 2, '½'],
  [5 / 8, '⅝'],
  [2 / 3, '⅔'],
  [3 / 4, '¾'],
  [7 / 8, '⅞'],
  [1, ''],
]

/** 1.5 → "1½", 0.333 → "⅓", 2.97 → "3". Never rounds a positive amount to 0. */
export function formatQty(n: number): string {
  if (n >= 10) return String(Math.round(n))
  let whole = Math.floor(n)
  const r = n - whole
  let best = NICE_FRACTIONS[0]
  for (const f of NICE_FRACTIONS) if (Math.abs(f[0] - r) < Math.abs(best[0] - r)) best = f
  if (best[0] === 1) {
    whole += 1
    best = NICE_FRACTIONS[0]
  }
  if (whole === 0 && !best[1]) return '⅛'
  return `${whole || ''}${best[1]}`
}

function roundTo(n: number): number {
  if (n < 10) return Math.round(n) || 1
  if (n < 100) return Math.round(n / 5) * 5
  return Math.round(n / 10) * 10
}

function roundMetric(n: number, dim: Dim): { value: number; unit: string } {
  if (dim === 'weight') {
    if (n >= 1000) return { value: Math.round(n / 100) / 10, unit: 'kg' }
    return { value: roundTo(n), unit: 'g' }
  }
  if (n >= 1000) return { value: Math.round(n / 100) / 10, unit: 'l' }
  return { value: roundTo(n), unit: 'ml' }
}

function bestUS(base: number, dim: Dim): { value: number; def: UnitDef } {
  if (dim === 'weight') {
    return base >= 453.6 ? { value: base / 453.6, def: UNITS.lb } : { value: base / 28.35, def: UNITS.oz }
  }
  if (base < 14) return { value: base / 4.93, def: UNITS.tsp }
  const cups = base / 240
  // Under a cup, only use cups for amounts people measure that way (¼ ⅓ ½ ⅔ ¾);
  // otherwise tablespoons read better ("10 tbsp", not "⅝ cup").
  const clean = (n: number) => Math.abs(n - Math.round(n)) < 0.06
  const measurableCup = cups >= 0.23 && (clean(cups * 4) || clean(cups * 3))
  if (!measurableCup && (base < 59 || cups < 1)) {
    const tbsp = base / 14.79
    return tbsp < 2 && !clean(tbsp * 2) ? { value: base / 4.93, def: UNITS.tsp } : { value: tbsp, def: UNITS.tbsp }
  }
  return { value: cups, def: UNITS.cup }
}

// --- Ingredient densities ------------------------------------------------------
// Grams per US cup (240 ml) for ingredients commonly written by weight in one
// system and by volume in the other. Values follow King Arthur's ingredient
// weight chart. `dry` items convert to grams in metric mode; liquids stay in ml.
// `preferWeight` items (cream cheese) stay in ounces in US mode.

interface Density {
  gPerCup: number
  kind: 'dry' | 'liquid'
  preferWeight?: boolean
}

const DENSITIES: [string, Density][] = (
  [
    ['all-purpose flour', 125, 'dry'],
    ['bread flour', 127, 'dry'],
    ['whole wheat flour', 113, 'dry'],
    ['cake flour', 113, 'dry'],
    ['almond flour', 96, 'dry'],
    ['flour', 125, 'dry'],
    ['powdered sugar', 113, 'dry'],
    ["confectioners' sugar", 113, 'dry'],
    ['confectioners sugar', 113, 'dry'],
    ['icing sugar', 113, 'dry'],
    ['brown sugar', 213, 'dry'],
    ['granulated sugar', 198, 'dry'],
    ['caster sugar', 198, 'dry'],
    ['sugar', 198, 'dry'],
    ['cocoa powder', 84, 'dry'],
    ['cornstarch', 112, 'dry'],
    ['rolled oats', 89, 'dry'],
    ['old-fashioned oats', 89, 'dry'],
    ['oats', 89, 'dry'],
    ['quinoa', 177, 'dry'],
    ['rice', 198, 'dry'],
    ['chocolate chips', 170, 'dry'],
    ['instant dry yeast', 149, 'dry'],
    ['instant yeast', 149, 'dry'],
    ['active dry yeast', 149, 'dry'],
    ['yeast', 149, 'dry'],
    ['baking powder', 192, 'dry'],
    ['baking soda', 288, 'dry'],
    ['kosher salt', 144, 'dry'],
    ['sea salt', 240, 'dry'],
    ['salt', 288, 'dry'],
    ['ground cinnamon', 125, 'dry'],
    ['ground cardamom', 96, 'dry'],
    ['ground ginger', 86, 'dry'],
    ['ground nutmeg', 106, 'dry'],
    ['butter', 227, 'dry'],
    ['cream cheese', 232, 'dry', true],
    ['peanut butter', 270, 'liquid'],
    ['honey', 336, 'liquid'],
    ['maple syrup', 312, 'liquid'],
    ['heavy cream', 232, 'liquid'],
    ['whipping cream', 232, 'liquid'],
    ['sour cream', 227, 'liquid'],
    ['buttermilk', 242, 'liquid'],
    ['yogurt', 227, 'liquid'],
    ['milk', 242, 'liquid'],
    ['water', 236, 'liquid'],
    ['olive oil', 200, 'liquid'],
    ['vegetable oil', 198, 'liquid'],
    ['oil', 198, 'liquid'],
    ['vanilla extract', 192, 'liquid'],
    ['vanilla bean paste', 240, 'liquid'],
  ] as [string, number, 'dry' | 'liquid', boolean?][]
)
  .map(([k, g, kind, pw]) => [k, { gPerCup: g, kind, preferWeight: pw }] as [string, Density])
  .sort((a, b) => b[0].length - a[0].length) // most specific first ("brown sugar" before "sugar")

/** Density for the ingredient named at the start of a line's remainder, if known. */
export function densityFor(rest: string): Density | null {
  // Only the ingredient name: stop at the first comma/parenthesis ("milk (warm)").
  const name = rest.toLowerCase().split(/[,(;]/)[0]
  for (const [key, d] of DENSITIES) {
    if (new RegExp(`(^|[^a-z])${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^a-z])`).test(name)) return d
  }
  return null
}

function unitLabel(def: UnitDef, qty: number): string {
  // Judge by the amount as displayed: 1.008 cups reads "1 cup".
  return qty > 1 && formatQty(qty) !== '1' && def.plural ? def.plural : def.canon
}

// Density conversions are estimates, so snap to what people actually measure:
// cups to ¼/⅓, tablespoons to ½, teaspoons and ounces to ¼.
function snapApprox(value: number, def: UnitDef): number {
  const to = (step: number) => Math.max(step, Math.round(value / step) * step)
  if (def === UNITS.cup) {
    const q = to(1 / 4)
    const t = to(1 / 3)
    return Math.abs(q - value) <= Math.abs(t - value) ? q : t
  }
  if (def === UNITS.tbsp) return to(1 / 2)
  if (def === UNITS.tsp || def === UNITS.oz) return to(1 / 4)
  return value
}

export interface ScaledLine {
  amount: string // bold part, e.g. "1½ cups" (empty when unscalable)
  rest: string // remainder of the line
  scaled: boolean // whether the amount was parsed (and so scaled/converted)
}

/**
 * Scale one raw line by `factor` and render it in `system`. At 1× in the
 * line's own system the author's text is kept verbatim. Otherwise convertible
 * units are converted (preferring the author's own parenthetical equivalent),
 * and countables only scale.
 */
export function scaleLine(raw: string, factor: number, system: UnitSystem): ScaledLine {
  const p = parseLine(raw)
  if (p.qty == null) return { amount: '', rest: raw, scaled: false }
  const def = p.unit
  const converting = !!(def?.dim && def.system && def.system !== system)

  if (factor === 1 && !converting) {
    const head = raw.match(QTY_RE)![0] + (p.unitText ? p.unitText : '')
    return { amount: head.trim(), rest: raw.slice(head.length).replace(/^\s+/, ''), scaled: true }
  }

  const sepOf = (w: string) => (w === '-' || w === '–' || !w ? '–' : ` ${w} `)

  // Total in base units (ml / g), including any "plus 2 teaspoons".
  const toBase = (q: number) => q * (def?.base ?? 1) + (p.plus ? p.plus.qty * (p.plus.unit.base ?? 0) : 0)

  if (converting && def?.dim) {
    // Use the author's own equivalent when it's in the target system.
    const alt = p.alt && p.alt.unit.system === system ? p.alt : null
    const lo = alt ? alt.qty * alt.unit.base! : toBase(p.qty)
    const hiQ = alt ? alt.qty2 : p.qty2
    const hi = hiQ != null ? (alt ? hiQ * alt.unit.base! : toBase(hiQ)) : null
    let dim = alt ? alt.unit.dim! : def.dim
    let k = 1 // base-unit multiplier when crossing weight <-> volume
    // Cross weight <-> volume by ingredient density: US cooks measure flour,
    // sugar, butter and milk by the cup; metric bakers weigh dry goods.
    const d = alt ? null : densityFor(p.rest)
    if (d && system === 'us' && dim === 'weight' && !d.preferWeight) {
      dim = 'volume'
      k = 240 / d.gPerCup // grams -> ml
    } else if (d && system === 'metric' && dim === 'volume' && d.kind === 'dry') {
      dim = 'weight'
      k = d.gPerCup / 240 // ml -> grams
    }
    return {
      amount: renderBase(lo * k * factor, hi != null ? hi * k * factor : null, dim, system, sepOf(p.rangeWord), k !== 1),
      rest: p.rest,
      scaled: true,
    }
  }

  if (def?.dim && (p.plus || system === 'us')) {
    // Same system, scaled: re-pick a sensible unit (3 tsp → 1 tbsp) and fold in "plus".
    const lo = toBase(p.qty) * factor
    const hi = p.qty2 != null ? toBase(p.qty2) * factor : null
    if (system === 'us' && def.system === 'us') {
      const keep = !p.plus && keepUSUnit(def, p.qty * factor)
      if (keep) {
        const nums = p.qty2 != null ? `${formatQty(p.qty * factor)}${sepOf(p.rangeWord)}${formatQty(p.qty2 * factor)}` : formatQty(p.qty * factor)
        return { amount: `${nums} ${unitLabel(def, (p.qty2 ?? p.qty) * factor)}`, rest: p.rest, scaled: true }
      }
    }
    return { amount: renderBase(lo, hi, def.dim, system, sepOf(p.rangeWord)), rest: p.rest, scaled: true }
  }

  // Counts (eggs, chiles, cloves, cans) round to what you can actually use.
  const count = (n: number) => (n >= 3 ? Math.round(n) : n >= 1 ? Math.round(n * 2) / 2 : n)
  const num = (n: number) => (def?.system === 'metric' ? String(roundTo(n)) : formatQty(def?.dim ? n : count(n)))
  const q1 = p.qty * factor
  const nums = p.qty2 != null ? `${num(q1)}${sepOf(p.rangeWord)}${num(p.qty2 * factor)}` : num(q1)
  const unitWord = def ? unitLabel(def, (p.qty2 ?? p.qty) * factor) : ''
  return { amount: unitWord ? `${nums} ${unitWord}` : nums, rest: p.rest, scaled: true }
}

// Keep the author's US unit unless scaling pushes it past a natural boundary.
function keepUSUnit(def: UnitDef, q: number): boolean {
  if (def.canon === 'tsp') return q < 3
  if (def.canon === 'tbsp') return q < 8
  if (def.canon === 'oz' && def.dim === 'weight') return q < 32
  if (def.canon === 'cup' && q < 1) {
    // Under a cup, keep cups only for amounts people measure that way (¼ ⅓ ½ ⅔ ¾).
    const near = (n: number) => Math.abs(n - Math.round(n)) < 0.06
    return near(q * 4) || near(q * 3)
  }
  return true
}

function renderBase(
  lo: number,
  hi: number | null,
  dim: Dim,
  system: UnitSystem,
  sep: string,
  approx = false,
): string {
  if (system === 'metric') {
    const a = roundMetric(lo, dim)
    if (hi == null) return `${a.value} ${a.unit}`
    const big = a.unit === 'kg' || a.unit === 'l'
    const b = big ? Math.round(hi / 100) / 10 : roundTo(hi)
    return `${a.value}${sep}${b} ${a.unit}`
  }
  // A range keeps one unit, picked from its lower bound.
  let a = bestUS(lo, dim)
  if (approx) a = { ...a, value: snapApprox(a.value, a.def) }
  if (hi == null) return `${formatQty(a.value)} ${unitLabel(a.def, a.value)}`
  const near = (n: number) => Math.abs(n - Math.round(n)) < 0.06
  const hiCups = hi / 240
  if (a.def === UNITS.cup && hiCups < 1 && !near(hiCups * 4) && !near(hiCups * 3)) {
    a = { value: lo / UNITS.tbsp.base!, def: UNITS.tbsp } // "8–10 tbsp", not "½–⅝ cup"
  }
  const hiVal = approx ? snapApprox(hi / a.def.base!, a.def) : hi / a.def.base!
  return `${formatQty(a.value)}${sep}${formatQty(hiVal)} ${unitLabel(a.def, hiVal)}`
}

/** The recipe's dominant measuring system, so the toggle starts on it. */
export function detectSystem(raws: string[]): UnitSystem {
  let us = 0
  let metric = 0
  for (const r of raws) {
    const s = parseLine(r).unit?.system
    if (s === 'us') us++
    else if (s === 'metric') metric++
  }
  return metric > us ? 'metric' : 'us'
}

/** What a yield counts: "12 rolls" → rolls/roll, otherwise servings/serving. */
export function yieldNoun(yieldText: string | null | undefined): { one: string; many: string } {
  const m = yieldText?.match(/\d+\s*(?:-|–|to)?\s*\d*\s+([a-z][a-z -]*)/i)
  const word = m?.[1].trim().toLowerCase()
  if (!word || /^(servings?|people|persons?|portions?)$/.test(word)) return { one: 'serving', many: 'servings' }
  const IRREGULAR: Record<string, string> = {
    loaf: 'loaves',
    dozen: 'dozen',
    batch: 'batches',
    serving: 'servings',
    // -ie nouns, which the -ies → -y rule would get wrong
    cookie: 'cookies',
    brownie: 'brownies',
    pie: 'pies',
    smoothie: 'smoothies',
  }
  const singular = (w: string) =>
    Object.keys(IRREGULAR).find((k) => IRREGULAR[k] === w) ??
    (w.endsWith('ies') ? `${w.slice(0, -3)}y` : /(ch|sh|x)es$/.test(w) ? w.slice(0, -2) : w.replace(/(?<=[^s])s$/, ''))
  const one = singular(word)
  const many =
    IRREGULAR[one] ??
    (/[^aeiou]y$/.test(one) ? `${one.slice(0, -1)}ies` : /(ch|sh|x)$/.test(one) ? `${one}es` : `${one}s`)
  return { one, many }
}

/** First number in a yield string: "6 servings" → 6, "Serves 4-6" → 4. */
export function parseServings(yieldText: string | null | undefined): number | null {
  if (!yieldText) return null
  const m = yieldText.match(/\d+/)
  const n = m ? parseInt(m[0]) : NaN
  return Number.isFinite(n) && n > 0 && n < 200 ? n : null
}

// --- Whole-ingredient helpers -------------------------------------------------

interface IngredientLike {
  raw: string
  alt_raw?: string | null
  section?: string | null
}

const lineSystem = (raw: string): UnitSystem | undefined => parseLine(raw).unit?.system

/**
 * Render an ingredient at a scale and unit system, preferring the recipe
 * author's own conversion (alt_raw) when it's written in the target system.
 */
export function renderIngredient(ing: IngredientLike, factor: number, system: UnitSystem): ScaledLine {
  if (ing.alt_raw && lineSystem(ing.raw) !== system && lineSystem(ing.alt_raw) === system) {
    return scaleLine(ing.alt_raw, factor, system)
  }
  return scaleLine(ing.raw, factor, system)
}

/** Heading text for display: "For the Dough:" → "For the Dough". */
export function sectionTitle(section: string): string {
  return section.trim().replace(/:\s*$/, '')
}

/** Consecutive runs of ingredients sharing a section (order preserved). */
export function groupBySection<T extends IngredientLike>(items: T[]): { section: string | null; items: T[] }[] {
  const out: { section: string | null; items: T[] }[] = []
  for (const it of items) {
    const section = it.section?.trim() || null
    const last = out[out.length - 1]
    if (last && last.section === section) last.items.push(it)
    else out.push({ section, items: [it] })
  }
  return out
}

/** Edit-sheet text: section headings on their own line ending in ":". */
export function ingredientsToText(items: IngredientLike[]): string {
  const lines: string[] = []
  for (const g of groupBySection(items)) {
    if (g.section) {
      if (lines.length) lines.push('')
      lines.push(g.section.trim().endsWith(':') ? g.section.trim() : `${g.section.trim()}:`)
    }
    lines.push(...g.items.map((i) => i.raw))
  }
  return lines.join('\n')
}

/** Parse edit-sheet text back: a line ending in ":" with no leading amount is a heading. */
export function textToIngredients(text: string): { raw: string; section: string | null }[] {
  let section: string | null = null
  const out: { raw: string; section: string | null }[] = []
  for (const line of text.split('\n').map((l) => l.trim())) {
    if (!line) continue
    if (line.endsWith(':') && parseLine(line).qty == null) {
      section = line
      continue
    }
    out.push({ raw: line, section })
  }
  return out
}
