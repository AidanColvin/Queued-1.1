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
      boxShadow: {
        // Soft, layered elevation for cards and floating controls.
        card: '0 18px 50px -18px rgba(0, 0, 0, 0.75), 0 4px 14px -6px rgba(0, 0, 0, 0.55)',
        glow: '0 0 0 1px rgba(245, 166, 35, 0.25), 0 8px 30px -8px rgba(245, 166, 35, 0.35)',
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
        'rise': {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.95)', opacity: '0.7' },
          '70%, 100%': { transform: 'scale(1.25)', opacity: '0' },
        },
      },
      animation: {
        drift: 'drift 18s ease-in-out infinite',
        'fade-in': 'fade-in 0.4s ease-out both',
        rise: 'rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both',
        'pulse-ring': 'pulse-ring 1.8s cubic-bezier(0.66, 0, 0, 1) infinite',
      },
    },
  },
  plugins: [],
};

export default config;
