import { NavLink, Outlet } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';

export function Layout() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
