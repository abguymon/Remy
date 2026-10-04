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
  if (base < 59 || (cups < 1 && !clean(cups * 4) && !clean(cups * 3))) {
    const tbsp = base / 14.79
    return tbsp < 2 && !clean(tbsp * 2) ? { value: base / 4.93, def: UNITS.tsp } : { value: tbsp, def: UNITS.tbsp }
  }
  return { value: cups, def: UNITS.cup }
}

function unitLabel(def: UnitDef, qty: number): string {
  return qty > 1 && def.plural ? def.plural : def.canon
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
    const dim = alt ? alt.unit.dim! : def.dim
    return {
      amount: renderBase(lo * factor, hi != null ? hi * factor : null, dim, system, sepOf(p.rangeWord)),
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
  return true
}

function renderBase(lo: number, hi: number | null, dim: Dim, system: UnitSystem, sep: string): string {
  if (system === 'metric') {
    const a = roundMetric(lo, dim)
    if (hi == null) return `${a.value} ${a.unit}`
    const big = a.unit === 'kg' || a.unit === 'l'
    const b = big ? Math.round(hi / 100) / 10 : roundTo(hi)
    return `${a.value}${sep}${b} ${a.unit}`
  }
  // A range keeps one unit, picked from its lower bound.
  let a = bestUS(lo, dim)
  if (hi == null) return `${formatQty(a.value)} ${unitLabel(a.def, a.value)}`
  const near = (n: number) => Math.abs(n - Math.round(n)) < 0.06
  const hiCups = hi / 240
  if (a.def === UNITS.cup && hiCups < 1 && !near(hiCups * 4) && !near(hiCups * 3)) {
    a = { value: lo / UNITS.tbsp.base!, def: UNITS.tbsp } // "8–10 tbsp", not "½–⅝ cup"
  }
  const hiVal = hi / a.def.base!
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

/** First number in a yield string: "6 servings" → 6, "Serves 4-6" → 4. */
export function parseServings(yieldText: string | null | undefined): number | null {
  if (!yieldText) return null
  const m = yieldText.match(/\d+/)
  const n = m ? parseInt(m[0]) : NaN
  return Number.isFinite(n) && n > 0 && n < 200 ? n : null
}

// --- Cook mode helpers -------------------------------------------------------

const DESCRIPTORS = new Set(
  (
    'chopped minced diced sliced grated shredded fresh dried ground large small medium whole finely ' +
    'roughly thinly freshly good quality extra virgin to taste for serving optional about of and or ' +
    'peeled seeded halved cooked raw packed lightly divided plus more as needed room temperature cold ' +
    'warm hot unsalted salted kosher sea boneless skinless'
  ).split(' '),
)

/** Key words that identify an ingredient inside step text ("eggplant", "garlic"). */
export function ingredientKeywords(raw: string, food: string | null): string[] {
  const src = (food || parseLine(raw).rest)
    .toLowerCase()
    .replace(/\([^)]*\)/g, ' ')
    .split(/[,;]/)[0]
  const words = src
    .split(/[^a-zà-ÿ-]+/)
    .filter((w) => w.length > 2 && !DESCRIPTORS.has(w))
  if (!words.length) return []
  const keys = new Set<string>()
  const last = words[words.length - 1]
  keys.add(last)
  if (words.length > 1) keys.add(words.slice(-2).join(' '))
  return [...keys]
}

function stem(w: string): string {
  return w.replace(/(ies)$/, 'y').replace(/(oes|es|s)$/, '')
}

/** Does a step mention this ingredient? Singular/plural-insensitive. */
export function stepMentions(step: string, keywords: string[]): boolean {
  const text = step.toLowerCase()
  return keywords.some((k) => {
    const s = stem(k)
    return s.length > 2 && new RegExp(`\\b${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'i').test(text)
  })
}

export interface StepTimer {
  label: string // "10 min"
  seconds: number
}

/** Durations mentioned in a step ("simmer 10 to 15 minutes") → timer presets. */
export function stepTimers(step: string): StepTimer[] {
  const re = /(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b/gi
  const out: StepTimer[] = []
  const seen = new Set<number>()
  for (const m of step.matchAll(re)) {
    const n = parseFloat(m[2] ?? m[1]) // use the upper bound of a range
    const u = m[3].toLowerCase()
    const mult = u.startsWith('h') ? 3600 : u.startsWith('s') ? 1 : 60
    const seconds = Math.round(n * mult)
    if (seconds < 30 || seconds > 6 * 3600 || seen.has(seconds)) continue
    seen.add(seconds)
    const label = u.startsWith('h') ? `${m[2] ?? m[1]} hr` : u.startsWith('s') ? `${m[2] ?? m[1]} sec` : `${m[2] ?? m[1]} min`
    out.push({ label, seconds })
  }
  return out
}
