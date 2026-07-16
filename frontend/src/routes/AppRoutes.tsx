import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from '../features/auth/ProtectedRoute';
import { PermissionRoute } from '../features/auth/PermissionRoute';

const HomePage = lazy(() =>
  import('../pages/HomePage').then((module) => ({ default: module.HomePage })),
);
const SearchPage = lazy(() =>
  import('../pages/SearchPage').then((module) => ({ default: module.SearchPage })),
);
const DocumentPage = lazy(() =>
  import('../pages/DocumentPage').then((module) => ({ default: module.DocumentPage })),
);
const LoginPage = lazy(() =>
  import('../pages/LoginPage').then((module) => ({ default: module.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('../pages/RegisterPage').then((module) => ({ default: module.RegisterPage })),
);
const ProfilePage = lazy(() =>
  import('../pages/ProfilePage').then((module) => ({ default: module.ProfilePage })),
);
const HistoryPage = lazy(() =>
  import('../pages/HistoryPage').then((module) => ({ default: module.HistoryPage })),
);
const SavedPage = lazy(() =>
  import('../pages/SavedPage').then((module) => ({ default: module.SavedPage })),
);
const ForbiddenPage = lazy(() =>
  import('../pages/ForbiddenPage').then((module) => ({ default: module.ForbiddenPage })),
);
const NotFoundPage = lazy(() =>
  import('../pages/NotFoundPage').then((module) => ({ default: module.NotFoundPage })),
);
const ManagementLayout = lazy(() =>
  import('../layouts/ManagementLayout').then((module) => ({ default: module.ManagementLayout })),
);
const EditorDashboardPage = lazy(() =>
  import('../pages/editor/EditorDashboardPage').then((module) => ({
    default: module.EditorDashboardPage,
  })),
);
const ManagedDocumentsPage = lazy(() =>
  import('../pages/editor/ManagedDocumentsPage').then((module) => ({
    default: module.ManagedDocumentsPage,
  })),
);
const ManagedDocumentPage = lazy(() =>
  import('../pages/editor/ManagedDocumentPage').then((module) => ({
    default: module.ManagedDocumentPage,
  })),
);
const EditorJobsPage = lazy(() =>
  import('../pages/management/JobsPage').then((module) => ({ default: module.EditorJobsPage })),
);
const AdminDashboardPage = lazy(() =>
  import('../pages/admin/AdminDashboardPage').then((module) => ({
    default: module.AdminDashboardPage,
  })),
);
const AdminUsersPage = lazy(() =>
  import('../pages/admin/AdminUsersPage').then((module) => ({ default: module.AdminUsersPage })),
);
const SourcesPage = lazy(() =>
  import('../pages/admin/SourcesPage').then((module) => ({ default: module.SourcesPage })),
);
const AdminJobsPage = lazy(() =>
  import('../pages/management/JobsPage').then((module) => ({ default: module.AdminJobsPage })),
);
const AuditPage = lazy(() =>
  import('../pages/admin/AuditPage').then((module) => ({ default: module.AuditPage })),
);
const SystemPage = lazy(() =>
  import('../pages/admin/SystemPage').then((module) => ({ default: module.SystemPage })),
);
const IndexesPage = lazy(() =>
  import('../pages/admin/IndexesPage').then((module) => ({ default: module.IndexesPage })),
);
const RagDiagnosticsPage = lazy(() =>
  import('../pages/admin/RagDiagnosticsPage').then((module) => ({
    default: module.RagDiagnosticsPage,
  })),
);

export function AppRoutes() {
  return (
    <Suspense
      fallback={
        <div className="grid min-h-screen place-items-center bg-canvas text-sm text-muted">
          Загружаем интерфейс…
        </div>
      }
    >
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/history"
          element={
            <ProtectedRoute>
              <HistoryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/saved"
          element={
            <ProtectedRoute>
              <SavedPage />
            </ProtectedRoute>
          }
        />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route
          element={
            <PermissionRoute permissions={['EDITOR_ACCESS']}>
              <ManagementLayout />
            </PermissionRoute>
          }
        >
          <Route path="/editor" element={<EditorDashboardPage />} />
          <Route path="/editor/documents" element={<ManagedDocumentsPage />} />
          <Route path="/editor/documents/:documentId" element={<ManagedDocumentPage />} />
          <Route path="/editor/jobs" element={<EditorJobsPage />} />
        </Route>
        <Route
          element={
            <PermissionRoute permissions={['ADMIN_ACCESS']}>
              <ManagementLayout />
            </PermissionRoute>
          }
        >
          <Route path="/admin" element={<AdminDashboardPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/sources" element={<SourcesPage />} />
          <Route path="/admin/jobs" element={<AdminJobsPage />} />
          <Route path="/admin/audit" element={<AuditPage />} />
          <Route path="/admin/system" element={<SystemPage />} />
          <Route path="/admin/indexes" element={<IndexesPage />} />
          <Route path="/admin/rag" element={<RagDiagnosticsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
