import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, setAuthToken } from "../api/client";
import type { User } from "../types";

const TOKEN_STORAGE_KEY = "fire-agent-auth-token";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Phase 2 (accounts). Entirely optional from the rest of the app's point of
// view: Phase 1's anonymous flow (create a case file, no login at all)
// keeps working exactly as before whether or not this provider has a user -
// api/client.ts's setAuthToken(null) is the default, so every request stays
// unauthenticated until someone actually logs in.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!storedToken) {
      setLoading(false);
      return;
    }
    setAuthToken(storedToken);
    api
      .me()
      .then(setUser)
      .catch(() => {
        // Stored token no longer valid (expired, tampered, server secret
        // rotated) - fall back to signed-out rather than looping errors.
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setAuthToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const applySession = (token: string, loggedInUser: User) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    setAuthToken(token);
    setUser(loggedInUser);
  };

  const login = async (email: string, password: string) => {
    const result = await api.login(email, password);
    applySession(result.access_token, result.user);
  };

  const signup = async (email: string, password: string) => {
    const result = await api.signup(email, password);
    applySession(result.access_token, result.user);
  };

  const logout = () => {
    // Revoke server-side first, while the token is still attached. Fire
    // and forget: if the request fails the token stays alive until it
    // expires, but this browser must still end up signed out - leaving
    // someone appearing logged in because the network blipped is worse.
    void api.logout().catch(() => undefined);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, login, signup, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
