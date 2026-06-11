import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor wraps the same static Next.js export the web deploy uses
 * (`next build` → `out/`). One codebase, two build targets:
 *
 *   Web   →  vercel (frontend/out + /api function)
 *   iOS   →  NEXT_PUBLIC_API_URL=https://<backend> npm run build:native
 *            npx cap sync ios && npx cap open ios
 *
 * The native shell serves the bundle from capacitor://localhost, so the
 * backend's CORS allowlist includes that origin and auth falls back from the
 * cookie to a bearer token kept in Capacitor Preferences (see lib/native.ts).
 */
const config: CapacitorConfig = {
  appId: 'com.queued.app',
  appName: 'Queued',
  webDir: 'out',
  ios: {
    contentInset: 'always',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 800,
      backgroundColor: '#f5f5f7',
      showSpinner: false,
    },
  },
};

export default config;
