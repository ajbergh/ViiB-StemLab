import { useEffect, useState } from 'react';
import App from './App';
import { api, configureApi } from './api';
import { desktopConnection } from './desktop';
import type { Preferences } from './types';

export default function Startup() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    setError('');
    (async () => {
      configureApi(await desktopConnection());
      await api.health();
      const settings = await api.getSettings();
      if (!disposed) setPreferences(settings);
    })().catch(e => { if (!disposed) setError(String(e instanceof Error ? e.message : e)); });
    return () => { disposed = true; };
  }, [attempt]);
  if (preferences) return <App initialPreferences={preferences} />;
  return <main className="h-screen flex flex-col items-center justify-center p-10 text-center gap-5" aria-live="polite">
    <h1 className="text-2xl font-bold">ViiB StemLab</h1>
    <p className="text-text-secondary">{error ? 'Unable to start the audio engine' : 'Starting your audio engine…'}</p>
    {error && <>
      <p role="alert" className="max-w-xl text-accent-crimson break-words">{error}</p>
      <p className="text-sm text-text-subtle">Close and reopen the app if the engine has exited. Diagnostic details are saved in desktop.log in the app data folder.</p>
      <button className="bg-brand text-black px-5 py-2 rounded-lg" onClick={() => setAttempt(a => a + 1)}>Try connection again</button>
    </>}
  </main>;
}
