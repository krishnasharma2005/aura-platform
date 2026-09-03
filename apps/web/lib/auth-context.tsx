"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  api,
  clearOrgId,
  clearToken,
  getToken,
  setOrgId,
  setToken as persistToken,
} from "@/lib/api-client";
import type { Organization, User } from "@/lib/api-types";

interface AuthContextValue {
  user: User | null;
  organization: Organization | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string) => Promise<void>;
  setOrganization: (org: Organization) => void;
  logout: () => void;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(undefined);

const ORG_KEY = "aura_org";
const USER_KEY = "aura_user";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = React.useState<User | null>(null);
  const [organization, setOrganizationState] = React.useState<Organization | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    const token = getToken();
    if (token) {
      const rawUser = window.localStorage.getItem(USER_KEY);
      const rawOrg = window.localStorage.getItem(ORG_KEY);
      if (rawUser) setUser(JSON.parse(rawUser));
      if (rawOrg) {
        const org: Organization = JSON.parse(rawOrg);
        setOrganizationState(org);
        // Restore the active tenant for the API client too — every org-scoped
        // request needs it in a header, not just in React state.
        if (org?.id) setOrgId(org.id);
      }
    }
    setIsLoading(false);
  }, []);

  const persistUser = (u: User) => {
    setUser(u);
    window.localStorage.setItem(USER_KEY, JSON.stringify(u));
  };

  const setOrganization = (org: Organization) => {
    setOrganizationState(org);
    window.localStorage.setItem(ORG_KEY, JSON.stringify(org));
    if (org?.id) setOrgId(org.id);
  };

  const login = async (email: string, password: string) => {
    const res = await api.auth.login({ email, password });
    persistToken(res.token);
    persistUser(res.user);
  };

  const signup = async (email: string, password: string, fullName: string) => {
    const res = await api.auth.signup({ email, password, full_name: fullName });
    persistToken(res.token);
    persistUser(res.user);
  };

  const logout = () => {
    clearToken();
    clearOrgId();
    window.localStorage.removeItem(USER_KEY);
    window.localStorage.removeItem(ORG_KEY);
    setUser(null);
    setOrganizationState(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        isAuthenticated: Boolean(user),
        isLoading,
        login,
        signup,
        setOrganization,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
