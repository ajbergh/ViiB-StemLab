import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

export function ModelSetup({ compact = false }: { compact?: boolean }) {
  const [models, setModels] = useState<Awaited<ReturnType<typeof api.getModels>> | null>(null);
  const [error, setError] = useState('');
  const [requesting, setRequesting] = useState(false);
  const refresh = useCallback(async () => {
    try { setModels(await api.getModels()); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, []);
  useEffect(() => {
    void refresh();
    const interval = setInterval(refresh, 1500);
    return () => clearInterval(interval);
  }, [refresh]);
  const model = models?.models.find(m => m.name === 'htdemucs_6s');
  const download = models?.downloads?.htdemucs_6s;
  const downloading = requesting || download?.status === 'downloading';
  if (compact && model?.cached && !error) return null;
  return <section className={`bg-surface-1 border border-surface-3 rounded-xl p-5 ${compact ? 'mx-6 mt-4' : ''}`} aria-label="Audio model setup">
    <h3 className="font-medium mb-2">{model?.cached ? 'Audio model ready' : 'Set up your audio model'}</h3>
    <p className="text-sm text-text-subtle mb-3">{model?.cached
      ? 'The six-stem model is stored locally and can process audio offline.'
      : 'Download the six-stem model once before processing. After setup, your audio stays on this computer and processing works offline.'}</p>
    {!compact && <p className="text-xs text-text-subtle break-all mb-3">Cache: {models?.cache_dir ?? 'Loading…'}</p>}
    {download && <div className="text-sm mb-3" aria-live="polite">
      <p className={download.status === 'failed' ? 'text-accent-crimson' : 'text-text-secondary'}>{download.message}</p>
      {download.status === 'downloading' && <progress aria-label="Model download progress" max={1} value={download.progress ?? undefined} className="w-full mt-2" />}
    </div>}
    {error && <p role="alert" className="text-accent-crimson mb-2">{error}</p>}
    {!model?.cached && <button disabled={!model || downloading} className="bg-brand text-black px-4 py-2 rounded-lg text-sm disabled:opacity-50" onClick={async () => {
      setRequesting(true);
      try { await api.downloadModel('htdemucs_6s'); await refresh(); }
      catch (e) { setError(e instanceof Error ? e.message : String(e)); }
      finally { setRequesting(false); }
    }}>{downloading ? `Downloading${download?.progress != null ? ` ${Math.round(download.progress * 100)}%` : '…'}` : download?.status === 'failed' ? 'Retry model download' : 'Download audio model'}</button>}
  </section>;
}
