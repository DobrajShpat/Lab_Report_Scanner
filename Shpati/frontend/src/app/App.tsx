import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../shared/auth';
import { Layout } from './Layout';
import { DashboardPage } from './DashboardPage';
import { UploadPage, AuditQueuePage } from './Pages';
import { InspectorPage } from './InspectorPage';

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="audit" element={<AuditQueuePage />} />
            <Route path="reports/:reportId" element={<InspectorPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
