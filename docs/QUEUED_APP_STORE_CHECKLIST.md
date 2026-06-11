# Queued — Apple App Store + Mobile Readiness

## App name
Queued

## Project location
- Frontend folder: ./frontend
- Backend folder: ./backend
- iOS wrapper folder: ./frontend/ios

## Run locally
### Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

### Frontend
cd frontend
cp .env.local.example .env.local
npm install
npm run dev

### Native iOS shell
cd frontend
npm run build:native

## Main addresses
- Live demo: https://queued-2.vercel.app
- Backend URL: https://YOUR-RENDER-BACKEND.onrender.com
- Privacy policy URL: https://YOUR-DOMAIN/privacy
- Support URL: https://YOUR-DOMAIN/support
- App Store Connect bundle ID: com.queued.app

## Files to check before submission
- frontend/capacitor.config.*
- frontend/ios/*
- frontend/.env.local
- backend/.env
- render.yaml
- docs/APP_STORE.md
- docs/privacy-policy.md

## Apple readiness checklist
- [ ] Real iOS build opens and works on device.
- [ ] Privacy Policy URL is public and final.
- [ ] App Privacy details completed in App Store Connect.
- [ ] Data collected by the app and third-party SDKs is documented.
- [ ] Account deletion works inside the app.
- [ ] Email verification and password reset work in production.
- [ ] Sign in with Apple added if other third-party sign-in methods exist.
- [ ] Screenshots prepared for required iPhone sizes.
- [ ] TestFlight build uploaded and tested.
- [ ] Streaming/provider data attribution is visible where required.
- [ ] All data-source licenses reviewed for allowed use.
- [ ] MovieLens non-commercial constraint reviewed before public commercial release.

## Important App Store notes
1. Apple requires you to provide app privacy details in App Store Connect, including data collected by your app and third-party partners/SDKs.
2. A publicly accessible Privacy Policy URL is required for App Store submission.
3. If your app offers certain third-party sign-in options, Apple’s guidelines can require Sign in with Apple.
4. Keep privacy answers accurate and updated whenever app data practices change.
5. If you collect usage data, account info, diagnostics, or personalization data, disclose it appropriately.

## Likely data disclosures for Queued
Review these carefully before submitting:
- Name
- Email address
- User ID / account ID
- Product interaction
- Search history
- Diagnostics / crash data
- App functionality data
- Personalization data
- Possibly watch history / ratings import data

## My recommendation
Current status: good demo / portfolio app, not yet guaranteed App Store-ready until privacy, licensing, native packaging, and submission checklist items are fully closed.

