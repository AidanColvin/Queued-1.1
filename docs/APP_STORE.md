# Shipping Queued to the iOS App Store

The frontend is one codebase with two build targets: the Vercel web deploy and
a Capacitor-wrapped native iOS app. This document covers everything the repo
can't automate — the Apple-side setup, the review checklist, and the licensing
constraint that governs how the app may be distributed.

## What's already in the repo

- `frontend/capacitor.config.ts` — app id `com.nextwatch.app`, `webDir: out`,
  splash configuration.
- `frontend/ios/` — the generated Xcode project (`npx cap add ios`).
- `npm run build:native` — static-exports the SPA and syncs it into the iOS
  shell (`next build && cap sync ios`).
- **Native auth** — sessions use a bearer token stored in Capacitor
  Preferences (cookies are unreliable from the `capacitor://localhost`
  origin); the backend accepts `Authorization: Bearer` everywhere and its CORS
  allowlist already includes the Capacitor origins.
- **Sign in with Apple** — `POST /auth/apple` verifies identity tokens against
  Apple's JWKS; the in-app button renders only inside the native shell. Apple
  *requires* this because Google sign-in is offered (guideline 4.8).
- **Account deletion** — in-app, in the account menu (guideline 5.1.1(v)).
- **Haptics** — real impact feedback on swipes via `@capacitor/haptics`, so
  the app doesn't feel like a wrapped website (guideline 4.2 — minimum
  functionality).

## One-time Apple setup (manual)

1. **Apple Developer Program** — enroll at developer.apple.com ($99/year).
2. **Bundle ID** — register `com.nextwatch.app` (Certificates, Identifiers &
   Profiles → Identifiers) and enable the **Sign in with Apple** capability.
3. **Backend config** — set `APPLE_CLIENT_IDS=com.nextwatch.app` on the
   backend (Render/Vercel env), or `/auth/apple` will report 503.

## Building (requires a Mac with Xcode 15+)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=https://<your-backend-host> npm run build:native
npx cap open ios          # opens Xcode; CocoaPods runs on first open
```

In Xcode: select your team under *Signing & Capabilities*, confirm the Sign in
with Apple capability, then build to a device or archive.

`NEXT_PUBLIC_API_URL` **must** be the absolute backend URL — the web deploy's
relative `/api` default has nothing to resolve against inside the shell.

## App icons & splash

Replace the placeholder assets in
`frontend/ios/App/App/Assets.xcassets` (AppIcon: 1024×1024 master;
Splash: 2732×2732 centered). `npx @capacitor/assets generate --ios` can
produce the full set from a single `assets/icon.png` + `assets/splash.png`.

## TestFlight → review

1. Xcode → Product → Archive → Distribute → App Store Connect.
2. In App Store Connect: create the app record (same bundle id), fill in the
   **App Privacy** questionnaire. Data collected: email + display name
   (account), movie ratings/swipes (app functionality, linked to the user).
   No tracking, no third-party ads → no App Tracking Transparency prompt.
3. **Privacy policy URL** is mandatory — publish one (what's collected, the
   in-app deletion path, contact address) and link it in App Store Connect.
4. TestFlight an internal build first; verify sign-in (email, Google, Apple),
   account deletion, the onboarding screen, and offline behavior.

## Review checklist (the rules this app actually trips)

| Guideline | Requirement | Status |
|---|---|---|
| 4.8 | Sign in with Apple when Google login is offered | built (`/auth/apple`) |
| 5.1.1(v) | In-app account deletion | built (account menu) |
| 4.2 | More than a wrapped website | haptics, native auth, swipe-first UI |
| 5.1.1 | Privacy policy + App Privacy labels | manual (App Store Connect) |

## ⚠️ Licensing: this build must stay non-commercial

The recommendation model is trained on **MovieLens 25M**, licensed by
GroupLens for **non-commercial research use only**, and IMDb's TSV dumps carry
the same restriction. TMDB's free API likewise excludes commercial products.

Consequences for the App Store build:

- the app must be **free** — no price, no ads, no in-app purchases;
- App Store Connect's "Made for Kids"/monetization questions are unaffected,
  but any future monetization requires retraining on commercially licensed
  data (or your own accumulated `swipe_events` signal) and a paid TMDB/JustWatch
  agreement for availability data;
- keep the data-source attributions (TMDB + JustWatch) visible in the UI.
