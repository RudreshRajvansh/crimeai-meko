/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // CrimeAI dark theme palette — Palantir Gotham inspired
        // Theme tokens live in index.css as RGB channels (light base, .dark override), so opacity modifiers work.
        bg: {
          primary:   'rgb(var(--bg-primary) / <alpha-value>)',
          secondary: 'rgb(var(--bg-secondary) / <alpha-value>)',
          tertiary:  'rgb(var(--bg-tertiary) / <alpha-value>)',
          elevated:  'rgb(var(--bg-elevated) / <alpha-value>)',
          hover:     'rgb(var(--bg-hover) / <alpha-value>)',
        },
        border: {
          subtle:  'rgb(var(--border-subtle) / <alpha-value>)',
          default: 'rgb(var(--border-default) / <alpha-value>)',
          strong:  'rgb(var(--border-strong) / <alpha-value>)',
        },
        text: {
          primary:   'rgb(var(--text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
          muted:     'rgb(var(--text-muted) / <alpha-value>)',
          inverse:   'rgb(var(--text-inverse) / <alpha-value>)',
        },
        accent: {
          blue:    'rgb(var(--accent-blue) / <alpha-value>)',
          light:   'rgb(var(--accent-light) / <alpha-value>)',
          cyan:    'rgb(var(--accent-cyan) / <alpha-value>)',
          purple:  'rgb(var(--accent-purple) / <alpha-value>)',
          amber:   'rgb(var(--accent-amber) / <alpha-value>)',
        },
        severity: {
          low:      { DEFAULT: 'rgb(var(--severity-low) / <alpha-value>)', bg: 'rgb(var(--severity-low-bg) / <alpha-value>)' },
          medium:   { DEFAULT: 'rgb(var(--severity-medium) / <alpha-value>)', bg: 'rgb(var(--severity-medium-bg) / <alpha-value>)' },
          high:     { DEFAULT: 'rgb(var(--severity-high) / <alpha-value>)', bg: 'rgb(var(--severity-high-bg) / <alpha-value>)' },
          critical: { DEFAULT: 'rgb(var(--severity-critical) / <alpha-value>)', bg: 'rgb(var(--severity-critical-bg) / <alpha-value>)' },
        },
        status: {
          online:  'rgb(var(--status-online) / <alpha-value>)',
          offline: 'rgb(var(--status-offline) / <alpha-value>)',
          idle:    'rgb(var(--status-idle) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':     'fadeIn 0.2s ease-in-out',
        'slide-up':    'slideUp 0.3s ease-out',
        'blink':       'blink 1s step-end infinite',
        'float-slow':  'floatSlow 25s ease-in-out infinite',
        'float-slow-r':'floatSlowReverse 30s ease-in-out infinite',
        'radar-spin':  'radarSpin 12s linear infinite',
        'fade-up':     'fadeUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-up-d1':  'fadeUp 0.7s 0.1s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-up-d2':  'fadeUp 0.7s 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-up-d3':  'fadeUp 0.7s 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'scan-line':   'scanLine 2.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn:  { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: { '0%': { transform: 'translateY(8px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
        blink:   { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0' } },
        floatSlow: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%':      { transform: 'translate(20px, -30px) scale(1.05)' },
          '66%':      { transform: 'translate(-15px, 15px) scale(0.95)' },
        },
        floatSlowReverse: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%':      { transform: 'translate(-25px, 20px) scale(1.08)' },
          '66%':      { transform: 'translate(15px, -15px) scale(0.92)' },
        },
        radarSpin: { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } },
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(16px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        scanLine: { '0%, 100%': { top: '0%' }, '50%': { top: 'calc(100% - 2px)' } },
      },
      boxShadow: {
        'inner-sm': 'inset 0 1px 2px rgba(0,0,0,0.4)',
        'card':     '0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(48,54,61,0.5)',
        'elevated': '0 8px 24px rgba(0,0,0,0.6)',
        'glow-blue': '0 0 12px rgba(31,111,235,0.4)',
        'glow-red':  '0 0 12px rgba(248,81,73,0.4)',
        'auth-card': '0 8px 32px rgba(0,0,0,0.7), 0 0 80px rgba(31,111,235,0.08)',
        'auth-glow': '0 0 60px rgba(31,111,235,0.12)',
        'input-focus': '0 0 0 1px rgba(31,111,235,0.5), 0 0 8px rgba(31,111,235,0.15)',
        'btn-glow': '0 0 20px rgba(31,111,235,0.35)',
        'btn-glow-hover': '0 0 28px rgba(31,111,235,0.5)',
      },
    },
  },
  plugins: [],
}
