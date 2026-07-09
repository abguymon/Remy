/** @type {import('tailwindcss').Config} */
// Design tokens mined verbatim from design/src/remy-app-source.html — the warm
// hybrid palette (DESIGN_BRIEF §3). Light only, phone-first.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Hanken Grotesk'", 'system-ui', 'sans-serif'],
        serif: ["'Newsreader'", 'Georgia', 'serif'],
        mono: ['ui-monospace', 'Menlo', 'monospace'],
      },
      colors: {
        canvas: '#ECE4D8', // outermost page bg
        cream: '#F6F0E8', // screen/app bg
        creamsoft: '#F1E7D8', // login gradient stop
        surface: '#FFFDFA', // cards & panels
        ink: '#2A2520', // primary text
        muted: '#6B6156', // secondary text
        faint: '#8A8072', // tertiary text
        fainter: '#A79B8B',
        hint: '#B6AB99', // labels / placeholders
        line: '#E7DFD3', // card hairline border
        line2: '#E1D8C9', // control border
        divider: '#F0E9DD', // row divider
        tile: '#EDE4D5', // product tile border
        dark: '#17130F', // notch / token panel
        terracotta: {
          DEFAULT: '#C05B3B',
          dark: '#A84A2E',
          deep: '#A0492C',
          soft: '#F7E6DE',
        },
        success: { DEFAULT: '#3F7A50', bg: '#E4F0E6', dot: '#4F8A5B' },
        warn: { DEFAULT: '#916312', bg: '#F7ECD6', dot: '#C08A2B', border: '#E7D3A8', deep: '#7A5B12' },
        danger: { DEFAULT: '#A8392B', bg: '#F6DFDB', border: '#E9C4BD', dot: '#C0392B' },
        badge: {
          savedbg: '#F7E6DE',
          savedfg: '#A0492C',
          favbg: '#EFEAD9',
          favfg: '#7A6A2B',
          webbg: '#ECE6DD',
          webfg: '#6B6156',
        },
      },
      borderRadius: {
        card: '14px',
        panel: '16px',
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
