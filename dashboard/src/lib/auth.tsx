"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { Amplify } from "aws-amplify";
import {
  signIn,
  signUp,
  signOut,
  getCurrentUser,
  confirmSignUp,
  fetchAuthSession,
  type SignInOutput,
} from "aws-amplify/auth";
import awsConfig from "./aws-config";

Amplify.configure(awsConfig);

interface User {
  userId: string;
  email: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<SignInOutput>;
  register: (email: string, password: string) => Promise<void>;
  confirm: (email: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkUser();
  }, []);

  async function checkUser() {
    try {
      const currentUser = await getCurrentUser();
      setUser({
        userId: currentUser.userId,
        email: currentUser.signInDetails?.loginId || "",
      });
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function login(email: string, password: string) {
    const result = await signIn({ username: email, password });
    await checkUser();
    return result;
  }

  async function register(email: string, password: string) {
    await signUp({
      username: email,
      password,
      options: { userAttributes: { email } },
    });
  }

  async function confirm(email: string, code: string) {
    await confirmSignUp({ username: email, confirmationCode: code });
  }

  async function logout() {
    await signOut();
    setUser(null);
  }

  async function getToken(): Promise<string | null> {
    try {
      const session = await fetchAuthSession();
      return session.tokens?.idToken?.toString() || null;
    } catch {
      return null;
    }
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, confirm, logout, getToken }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
