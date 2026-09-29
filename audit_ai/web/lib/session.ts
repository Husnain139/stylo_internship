"use client";

import { useSyncExternalStore } from "react";

export type Role = "junior_auditor" | "senior_auditor" | "administrator";

export type Session = {
  token: string;
  email: string;
  name: string;
  role: Role;
};

const KEY = "audit_session";
const EVENT = "audit-session";
let cachedRaw: string | null = null;
let cachedSession: Session | null = null;

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(KEY);
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  if (!raw) {
    cachedSession = null;
    return null;
  }
  try {
    cachedSession = JSON.parse(raw) as Session;
  } catch {
    cachedSession = null;
  }
  return cachedSession;
}

function publish() {
  window.dispatchEvent(new Event(EVENT));
}

export function writeSession(session: Session) {
  sessionStorage.setItem(KEY, JSON.stringify(session));
  publish();
}

export function clearSession() {
  sessionStorage.removeItem(KEY);
  publish();
}

function subscribe(onStoreChange: () => void) {
  window.addEventListener(EVENT, onStoreChange);
  return () => window.removeEventListener(EVENT, onStoreChange);
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, readSession, () => null);
}

export function roleLabel(role: string): string {
  if (role === "junior_auditor") return "Junior Auditor";
  if (role === "senior_auditor") return "Senior Auditor";
  if (role === "administrator") return "Administrator";
  return role;
}
