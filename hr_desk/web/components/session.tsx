"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api, type Person } from "@/lib/api";

type SessionValue = {
  loading: boolean;
  me: Person | null;
  people: Person[];
  samples: boolean;
  loadError: string;
  retry: () => Promise<void>;
  signIn: (email: string) => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<Person | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [samples, setSamples] = useState(true);
  const [loadError, setLoadError] = useState("");

  async function refresh() {
    const data = await api<{ samples: boolean; people: Person[]; me: Person | null }>("/api/bootstrap");
    setSamples(data.samples);
    setPeople(data.people);
    setMe(data.me);
    setLoadError("");
  }

  useEffect(() => {
    refresh()
      .catch((caught) => {
        setMe(null);
        setPeople([]);
        setLoadError(
          caught instanceof Error ? caught.message : "The sign-in list didn't load. Try again.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  async function signIn(email: string) {
    const data = await api<{ me: Person }>("/api/session", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setMe(data.me);
  }

  return (
    <SessionContext.Provider value={{ loading, me, people, samples, loadError, retry: refresh, signIn }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("Session is only available inside the page shell.");
  }
  return value;
}
