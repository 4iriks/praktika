import { createContext } from 'react';
import type { AuthStatus, LoginRequest, RegisterRequest, User } from '../../types';

export interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  isLoading: boolean;
  login: (request: LoginRequest) => Promise<User>;
  register: (request: RegisterRequest) => Promise<User>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
