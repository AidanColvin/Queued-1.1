import type { Config } from 'tailwindcss';

// Dark, opinionated palette: deep charcoal, warm off-white text, saturated amber
// accent. Swipe-direction colors map to the four actions.
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        charcoal: '#0d0f12',
        surface: '#16191e',
        'surface-2': '#1d2128',
        ink: '#f5f3ee',
        muted: '#9aa0a6',
        amber: '#f5a623',
        like: '#3ecf8e',
        pass: '#ff5e5b',
        save: '#4aa8ff',
        skip: '#8a9099',
      },
      fontFamily: {
        serif: ['"DM Serif Display"', 'Georgia', 'serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      borderColor: {
        warm: 'rgba(245, 166, 35, 0.18)',
      },
      keyframes: {
        'drift': {
          '0%, 100%': { transform: 'translate(0, 0)' },
          '50%': { transform: 'translate(-2%, 2%)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        drift: 'drift 18s ease-in-out infinite',
        'fade-in': 'fade-in 0.4s ease-out both',
      },
    },
  },
  plugins: [],
};

export default config;
