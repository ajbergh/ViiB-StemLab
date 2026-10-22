import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { CudaStatus } from '../types';

export function CudaSetup() {
  const [state, setState] = useState<CudaStatus | null>(null);
  const [error, setError] = useState('');
  const [requesting, setRequesting] = useState(false);
  const refresh = useCallback(async () => {
    try { setState(await api.getCuda()); setError(''); }
    catch (e) { setError(String(e)); }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(refresh, 1500);
    return () => clearInterval(timer);
  }, [refresh]);
  const busy = requesting || ['checking', 'downloading', 'verifying'].includes(state?.status ?? '');
  const action = async (operation: () => Promise<unknown>) => {
    setRequesting(true);
    try { await operation(); await refresh(); }
    catch (e) { setError(String(e)); }
    finally { setRequesting(false); }
  };
  if (state?.hardware?.platform === 'Darwin') return null;
  return <section aria-label="NVIDIA acceleration setup" className="bg-surface-1 border border-surface-3 rounded-xl p-5 space-y-3">
    <h3 className="font-medium">NVIDIA acceleration</h3>
    <p className="text-sm text-text-subtle">On supported Windows PCs, download GPU acceleration once. Auto uses it when ready. CPU processing stays available during setup; the audio model is shared.</p>
    <label className="flex gap-2 text-sm items-center">
      <input type="checkbox" checked={state?.automatic ?? true} disabled={!state || requesting}
        onChange={e => {
          const enabled = e.target.checked;
          setState(previous => previous ? { ...previous, automatic: enabled } : previous);
          void action(() => api.saveSettings({ auto_cuda: enabled }));
        }} />
      Automatically download acceleration when using Auto or CUDA
    </label>
    {state?.hardware?.gpus.map(gpu => <p key={gpu.name} className="text-xs text-text-subtle">{gpu.name} · Driver {gpu.driver} · {gpu.memoryMb} MB</p>)}
    <p aria-live="polite" className={state?.status === 'failed' ? 'text-accent-orange text-sm' : 'text-sm'}>{state?.message ?? 'Checking acceleration status…'}</p>
    {busy && <progress aria-label="CUDA setup progress" max={1} value={state?.progress ?? undefined} className="w-full" />}
    {error && <p role="alert" className="text-accent-crimson">{error}</p>}
    <div className="flex gap-3">
      {busy ? <button disabled={requesting} onClick={() => void action(api.cancelCuda)} className="bg-surface-2 px-4 py-2 rounded-lg text-sm">Cancel setup</button>
        : !state?.ready && state?.status !== 'unsupported' && <button disabled={!state || requesting || !state.configured}
          onClick={() => void action(api.installCuda)} className="bg-brand text-black px-4 py-2 rounded-lg text-sm disabled:opacity-50">
          {state?.status === 'failed' || state?.status === 'cancelled' ? 'Retry CUDA setup' : 'Install CUDA acceleration'}
        </button>}
    </div>
  </section>;
}
