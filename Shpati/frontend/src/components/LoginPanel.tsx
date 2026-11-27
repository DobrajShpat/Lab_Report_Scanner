import { FormEvent, useState } from 'react';
import { useAuth } from '../shared/auth';

export function LoginPanel() {
  const { login, register, user, logout, loading } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('demo');
  const [password, setPassword] = useState('demo123');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) {
    return <p className="px-3 text-xs text-slate-500">Checking session…</p>;
  }

  if (user) {
    return (
      <div className="mt-auto border-t border-slate-200 px-3 pt-4">
        <p className="text-xs text-slate-500">Signed in as</p>
        <p className="text-sm font-semibold text-slate-900">{user.username}</p>
        <button
          type="button"
          onClick={logout}
          className="mt-2 text-xs font-semibold text-teal-700 hover:underline"
        >
          Sign out
        </button>
      </div>
    );
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(username, password);
      } else {
        await register(username, password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-auto border-t border-slate-200 px-3 pt-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {mode === 'login' ? 'Sign in' : 'Create account'}
      </p>
      <form onSubmit={onSubmit} className="space-y-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          autoComplete="username"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        />
        {error && <p className="text-xs text-rose-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-teal-700 py-2 text-xs font-semibold text-white disabled:opacity-60"
        >
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register'}
        </button>
      </form>
      <button
        type="button"
        onClick={() => setMode((m) => (m === 'login' ? 'register' : 'login'))}
        className="mt-2 text-xs text-teal-700 hover:underline"
      >
        {mode === 'login' ? 'Need an account? Register' : 'Already have an account? Sign in'}
      </button>
      <p className="mt-2 text-[10px] leading-snug text-slate-400">Demo: demo / demo123</p>
    </div>
  );
}
