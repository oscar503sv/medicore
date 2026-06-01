import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        accent: 'var(--accent)',
        'accent-hover': 'var(--accent-hover)',
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        line: 'var(--line)',
        'line-soft': 'var(--line-soft)',
        tx: 'var(--text)',
        'tx-2': 'var(--text-2)',
        'tx-3': 'var(--text-3)',
        'tx-4': 'var(--text-4)',
        ok: 'var(--ok)',
        warn: 'var(--warn)',
        danger: 'var(--danger)',
        info: 'var(--info)',
      },
      fontFamily: {
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['"Geist"', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '10px',
        lg: '14px',
        xl: '16px',
        pill: '9999px',
      },
      boxShadow: {
        sm: '0 1px 3px 0 rgb(0 0 0 / .07)',
        DEFAULT: '0 2px 8px 0 rgb(0 0 0 / .10)',
        lg: '0 8px 24px 0 rgb(0 0 0 / .14)',
      },
      animation: {
        'fade-in': 'fadeIn .18s ease',
        'pop-in': 'popIn .22s ease',
        'slide-in': 'slideIn .28s cubic-bezier(.32,.72,0,1)',
        'pulse-dot': 'pulseDot 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        popIn: {
          from: { opacity: '0', transform: 'scale(.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        slideIn: {
          from: { transform: 'translateX(100%)' },
          to: { transform: 'translateX(0)' },
        },
        pulseDot: {
          '0%,100%': { opacity: '1' },
          '50%': { opacity: '.4' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
