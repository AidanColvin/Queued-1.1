import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'NextWatch — find your next watch',
  description:
    'Swipe through movie & TV recommendations from a hybrid ML engine trained on 25M ratings. It learns your taste as you go.',
  manifest: '/manifest.webmanifest',
  applicationName: 'NextWatch',
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
  // Adds the apple-mobile-web-app-* meta so "Add to Home Screen" launches a
  // chromeless, standalone app with our title. `default` gives a light status
  // bar (dark text) to match the bright app (the shell pads out of safe areas).
  appleWebApp: {
    capable: true,
    title: 'NextWatch',
    statusBarStyle: 'default',
  },
};

export const viewport: Viewport = {
  themeColor: '#ffffff',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  // Render edge-to-edge on notched iPhones; the app shell then pads itself back
  // out of the safe areas (see .app-shell in globals.css).
  viewportFit: 'cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Fonts are loaded via a CSS @import in globals.css (build-safe). */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
