/** @type {import('tailwindcss').Config} */
// Design tokens mined verbatim from design/src/remy-app-source.html — the warm
// hybrid palette (DESIGN_BRIEF §3), now themed light + dark. Phone-first.
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Hanken Grotesk'", 'system-ui', 'sans-serif'],
        serif: ["'Newsreader'", 'Georgia', 'serif'],
        mono: ['ui-monospace', 'Menlo', 'monospace'],
      },
      // Every color is a CSS variable (RGB triplet) defined in index.css for
      // light and dark themes, so `bg-surface/85`-style alpha still works and
      // the whole app re-themes from one place.
      colors: {
        canvas: v('canvas'), // outermost page bg
        cream: v('cream'), // screen/app bg
        creamsoft: v('creamsoft'), // login gradient stop
        surface: v('surface'), // cards & panels
        chip: v('chip'), // tag chips, segmented-control track
        ink: v('ink'), // primary text
        muted: v('muted'), // secondary text
        faint: v('faint'), // tertiary text (AA on cream)
        fainter: v('fainter'),
        hint: v('hint'), // labels / placeholders
        line: v('line'), // card hairline border
        line2: v('line2'), // control border
        divider: v('divider'), // row divider
        tile: v('tile'), // product tile border / photo placeholder
        producttile: v('producttile'), // stays light in dark mode: Kroger photos have baked-in white
        dark: v('dark'), // scrims, notch
        onaccent: v('onaccent'), // text/icons on a terracotta fill
        terracotta: {
          DEFAULT: v('terracotta'),
          dark: v('terracotta-dark'), // hover
          deep: v('terracotta-deep'), // accent text/links
          soft: v('terracotta-soft'),
        },
        success: { DEFAULT: v('success'), bg: v('success-bg'), dot: v('success-dot') },
        warn: {
          DEFAULT: v('warn'),
          bg: v('warn-bg'),
          dot: v('warn-dot'),
          border: v('warn-border'),
          deep: v('warn-deep'),
        },
        danger: { DEFAULT: v('danger'), bg: v('danger-bg'), border: v('danger-border'), dot: v('danger-dot') },
        badge: {
          savedbg: v('terracotta-soft'),
          savedfg: v('terracotta-deep'),
          favbg: v('badge-favbg'),
          favfg: v('badge-favfg'),
          webbg: v('chip'),
          webfg: v('muted'),
        },
      },
      borderRadius: {
        card: '16px',
        panel: '20px',
      },
      boxShadow: {
        card: '0 1px 3px rgba(40,30,20,.05)',
        cardsoft: '0 1px 3px rgba(40,30,20,.04)',
        terracotta: '0 2px 8px rgba(192,91,59,.25)',
        toast: '0 6px 20px rgba(0,0,0,.25)',
        modal: '0 20px 50px rgba(0,0,0,.3)',
      },
      keyframes: {
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        pop: { '0%': { transform: 'scale(.9)', opacity: '0' }, '100%': { transform: 'scale(1)', opacity: '1' } },
      },
      animation: {
        shimmer: 'shimmer 1.3s infinite',
        pop: 'pop .18s ease-out',
      },
    },
  },
  plugins: [],
}
