/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#07080c',
          900: '#0d0f16',
          850: '#12141d',
          800: '#171a25',
          700: '#222636',
          600: '#2e3347',
        },
        accent: {
          DEFAULT: '#7c5cff',
          soft: '#a593ff',
          deep: '#5b3df5',
        },
        signal: {
          DEFAULT: '#22d3ee',
          soft: '#67e8f9',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(124,92,255,.35), 0 8px 32px -8px rgba(124,92,255,.45)',
        'glow-signal': '0 0 0 1px rgba(34,211,238,.4), 0 8px 28px -8px rgba(34,211,238,.5)',
        panel: '0 1px 0 0 rgba(255,255,255,.04) inset, 0 20px 40px -24px rgba(0,0,0,.8)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #7c5cff 0%, #22d3ee 100%)',
        'grid-fade':
          'radial-gradient(ellipse at top, rgba(124,92,255,.18), transparent 60%), radial-gradient(ellipse at bottom right, rgba(34,211,238,.08), transparent 55%)',
      },
      keyframes: {
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        'fade-up': { from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'none' } },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        'fade-up': 'fade-up .25s ease-out both',
      },
    },
  },
  plugins: [],
};
