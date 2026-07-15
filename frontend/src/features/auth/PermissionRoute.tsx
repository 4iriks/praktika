import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import type { Permission } from '../../types';
import { loginUrl } from '../../utils/returnTo';
import { hasAllPermissions } from './permissions';
import { useAuth } from './useAuth';

interface PermissionRouteProps {
  children: ReactNode;
  permissions: readonly Permission[];
}

export function PermissionRoute({ children, permissions }: PermissionRouteProps) {
  const { user, status } = useAuth();
  const location = useLocation();

  if (status === 'initializing') {
    return (
      <div className="grid min-h-screen place-items-center bg-canvas text-sm text-muted">
        Проверяем права доступа…
      </div>
    );
  }

  if (!user) {
    const returnTo = location.pathname + location.search;
    return <Navigate to={loginUrl(returnTo)} replace state={{ from: returnTo }} />;
  }

  if (!hasAllPermissions(user, permissions)) {
    return <Navigate to="/403" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
