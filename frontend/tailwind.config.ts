import type { Config } from 'tailwindcss';

// Clean, Apple-inspired light palette: soft off-white canvas (#f5f5f7), pure
// white surfaces, near-black ink, and Apple system colors for the four swipe
// actions. The whole feel is bright, calm, and high-contrast.
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces & canvas
        canvas: '#ffffff', // pure white background
        surface: '#ffffff', // cards, panels, drawers
        'surface-2': '#f5f5f7', // very light raised fills (chips, hover)
        // Text
        ink: '#1d1d1f', // primary near-black
        muted: '#6e6e73', // secondary gray
        faint: '#86868b', // tertiary gray
        // Accent + actions (Apple system colors)
        accent: '#0071e3', // Apple link blue
        like: '#34c759', // green
        pass: '#ff3b30', // red
        save: '#0a84ff', // blue
        skip: '#8e8e93', // gray
      },
      fontFamily: {
        // SF Pro on Apple devices, Inter as the cross-platform stand-in.
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"SF Pro Display"',
          '"SF Pro Text"',
          'Inter',
          'system-ui',
          'sans-serif',
        ],
        // Display headings reuse the same SF/Inter stack — kept as a separate
        // token so call-sites read intentionally, no serif anywhere.
        display: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"SF Pro Display"',
          'Inter',
          'system-ui',
          'sans-serif',
        ],
      },
      borderColor: {
        hairline: 'rgba(0, 0, 0, 0.08)', // Apple-style 1px separators
      },
      boxShadow: {
        card: '0 10px 34px -14px rgba(0, 0, 0, 0.22)',
        soft: '0 1px 3px rgba(0, 0, 0, 0.08)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.4s ease-out both',
      },
    },
  },
  plugins: [],
};

export default config;
