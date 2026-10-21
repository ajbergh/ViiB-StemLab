import { useEffect, useState } from 'react';
import App from './App';
import { api, configureApi } from './api';
import { desktopConnection, nativeDesktop, runtimeStatus, installRuntime, cancelRuntime } from './desktop';
import type { RuntimeSetup } from './desktop';
import type { Preferences } from './types';

export default function Startup() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [setup, setSetup] = useState<RuntimeSetup | null>(null);
  const [requesting, setRequesting] = useState(false);
  useEffect(() => {
    let disposed = false;
    setError('');
    (async () => {
      if (nativeDesktop()) {
        while (!disposed) {
          const status = await runtimeStatus();
          if (disposed) return;
          setSetup(status);
          if (status.phase === 'ready') break;
          await new Promise(resolve => setTimeout(resolve, 400));
        }
        if (disposed) return;
      }
      configureApi(await desktopConnection());
      await api.health();
      const settings = await api.getSettings();
      if (!disposed) setPreferences(settings);
    })().catch(e => { if (!disposed) setError(String(e instanceof Error ? e.message : e)); });
    return () => { disposed = true; };
  }, [attempt]);
  if (preferences) return <App initialPreferences={preferences} />;
  const setupAction = async (operation: () => Promise<void>) => {
    setRequesting(true);
    setError('');
    try { await operation(); }
    catch (e) { setError(String(e)); }
    finally { setRequesting(false); }
  };
  const needsSetup = setup && ['needed', 'failed', 'cancelled'].includes(setup.phase);
  const settingUp = setup && ['checking', 'downloading', 'verifying'].includes(setup.phase);
  return <main className="h-screen overflow-y-auto flex flex-col items-center justify-center p-10 text-center gap-5" aria-live="polite">
    <h1 className="text-2xl font-bold">ViiB StemLab</h1>
    <p className="max-w-xl break-words text-text-secondary">{error ? 'Unable to start the audio engine' : setup?.message ?? 'Starting your audio engine…'}</p>
    {setup && setup.phase !== 'ready' && <section aria-label="Processing components setup" className="max-w-xl w-full bg-surface-1 rounded-xl border border-surface-3 p-5 space-y-4">
      <h2 className="font-semibold">{setup.flavor === 'full' ? 'Preparing your offline installation' : 'Set up audio processing'}</h2>
      <p className="text-sm text-text-subtle">{setup.flavor === 'full'
        ? 'Your audio engine, decoder tools and model are included. No processing download is required.'
        : 'Download the CPU audio engine, decoder tools and model once. No separate Python installation is needed. Optional NVIDIA acceleration can be set up afterward.'}</p>
      {setup.downloadBytes != null && <p className="text-xs text-text-subtle">Download: {(setup.downloadBytes / 1048576).toFixed(0)} MB · Setup space: {((setup.requiredBytes ?? 0) / 1073741824).toFixed(1)} GB</p>}
      {settingUp && <progress aria-label="Processing setup progress" max={1} value={setup.progress ?? undefined} className="w-full" />}
      {setup.phase === 'failed' && <p role="alert" className="text-sm text-accent-crimson">Setup could not finish. Check your connection and available disk space, then retry.</p>}
      {needsSetup && <button disabled={requesting} onClick={() => void setupAction(installRuntime)} className="bg-brand text-black px-5 py-2 rounded-lg disabled:opacity-50">
        {setup.phase === 'needed' ? 'Download processing components' : 'Retry setup'}
      </button>}
      {settingUp && <button disabled={requesting} onClick={() => void setupAction(cancelRuntime)} className="bg-surface-2 px-5 py-2 rounded-lg disabled:opacity-50">Cancel setup</button>}
    </section>}
    {error && <>
      <p role="alert" className="max-w-xl text-accent-crimson break-words">{error}</p>
      <p className="text-sm text-text-subtle">Close and reopen the app if the engine has exited. Diagnostic details are saved in desktop.log in the app data folder.</p>
      <button className="bg-brand text-black px-5 py-2 rounded-lg" onClick={() => setAttempt(a => a + 1)}>Try connection again</button>
    </>}
  </main>;
}
