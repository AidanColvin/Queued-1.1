// Capacitor-aware helpers. The same bundle runs on the web and inside the iOS
// shell; everything here no-ops gracefully in the browser so the web build
// carries no native behavior.

import { Capacitor } from '@capacitor/core';

/** True when running inside the Capacitor native shell (iOS/Android). */
export function isNative(): boolean {
  return Capacitor.isNativePlatform();
}

// ---------------------------------------------------------------------------
// Auth token store. Browsers authenticate with the httpOnly cookie; the native
// shell (capacitor://localhost origin) can't rely on cross-site cookies, so it
// keeps the session JWT in Capacitor Preferences and sends it as a Bearer
// header. An in-memory mirror lets the synchronous fetch path read it.
// ---------------------------------------------------------------------------
const TOKEN_KEY = 'nextwatch_auth_token';
let cachedToken: string | null = null;

/** Load the persisted token into memory. Call once before the first API call. */
export async function initAuthToken(): Promise<void> {
  if (!isNative()) return;
  try {
    const { Preferences } = await import('@capacitor/preferences');
    cachedToken = (await Preferences.get({ key: TOKEN_KEY })).value;
  } catch {
    cachedToken = null;
  }
}

/** The session token to attach as an Authorization header (native only). */
export function getAuthToken(): string | null {
  return cachedToken;
}

/** Persist (or clear, with null) the session token after login/logout. */
export async function setAuthToken(token: string | null): Promise<void> {
  if (!isNative()) return; // web sessions live in the httpOnly cookie only
  cachedToken = token;
  try {
    const { Preferences } = await import('@capacitor/preferences');
    if (token) await Preferences.set({ key: TOKEN_KEY, value: token });
    else await Preferences.remove({ key: TOKEN_KEY });
  } catch {
    /* keep the in-memory copy */
  }
}

// ---------------------------------------------------------------------------
// Haptics — native impact feedback on swipes, navigator.vibrate fallback.
// ---------------------------------------------------------------------------
export async function hapticImpact(strong = false): Promise<void> {
  if (isNative()) {
    try {
      const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
      await Haptics.impact({ style: strong ? ImpactStyle.Heavy : ImpactStyle.Light });
      if (strong) {
        // Double-buzz for the super like, mirroring the web pattern.
        setTimeout(() => void Haptics.impact({ style: ImpactStyle.Heavy }), 60);
      }
      return;
    } catch {
      /* fall through to vibrate */
    }
  }
  if (typeof navigator !== 'undefined' && navigator.vibrate) {
    navigator.vibrate(strong ? [18, 40, 18] : 12);
  }
}

/** Run the native Sign-in-with-Apple flow; returns the identity token + name.
 *  Only callable when {@link isNative} is true. */
export async function nativeAppleSignIn(): Promise<{ identityToken: string; displayName: string | null }> {
  const { SignInWithApple } = await import('@capacitor-community/apple-sign-in');
  const result = await SignInWithApple.authorize({
    clientId: 'com.nextwatch.app',
    redirectURI: 'https://nextwatch-rouge.vercel.app',
    scopes: 'email name',
  });
  const r = result.response;
  if (!r.identityToken) throw new Error('Apple sign-in was cancelled.');
  const name = [r.givenName, r.familyName].filter(Boolean).join(' ');
  return { identityToken: r.identityToken, displayName: name || null };
}
