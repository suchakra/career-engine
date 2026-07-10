import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";

/**
 * Firebase Web SDK init from the public NEXT_PUBLIC_FIREBASE_* config.
 *
 * Every value here is PUBLIC client config (documented in .env.example), NOT a
 * secret. Initialized lazily/once so it is safe under React strict mode and SSR.
 */
function firebaseConfig() {
  return {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  };
}

let cachedApp: FirebaseApp | null = null;

function firebaseApp(): FirebaseApp {
  if (cachedApp) return cachedApp;
  cachedApp = getApps().length ? getApp() : initializeApp(firebaseConfig());
  return cachedApp;
}

/** The Firebase Auth instance (lazily initialized). */
export function getFirebaseAuth(): Auth {
  return getAuth(firebaseApp());
}

/** Google sign-in provider (the single sign-in method for Phase 10). */
export function googleProvider(): GoogleAuthProvider {
  return new GoogleAuthProvider();
}
