import { NavLink } from 'react-router-dom';
import { ClipboardList, LayoutDashboard, Upload } from 'lucide-react';
import { cn } from '../shared/api';
import { LoginPanel } from './LoginPanel';

const items = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/upload', icon: Upload, label: 'Batch Upload' },
  { to: '/audit', icon: ClipboardList, label: 'All Reports' },
];

export function Sidebar() {
  return (
    <aside className="flex min-h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-6">
      <div className="mb-8 px-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-teal-600">Shpati</p>
        <h1 className="text-lg font-bold text-slate-900">Lab Digitizer</h1>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition',
                isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-50',
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <LoginPanel />
    </aside>
  );
}
