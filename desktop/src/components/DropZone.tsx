import { useEffect, useRef, useState } from 'react';
import { Upload, FolderPlus, FileAudio } from 'lucide-react';
import { listenForFiles, nativeDesktop, pickAudio } from '../desktop';

interface DropZoneProps { onAddPaths: (paths: string[]) => void; isAdding: boolean }

export function DropZone({ onAddPaths, isAdding }: DropZoneProps) {
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const onAdd = useRef(onAddPaths);
  onAdd.current = onAddPaths;
  useEffect(() => {
    if (!nativeDesktop()) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    listenForFiles(paths => onAdd.current(paths)).then(stop => {
      if (disposed) stop(); else unlisten = stop;
    }).catch(e => setError(String(e)));
    return () => { disposed = true; unlisten?.(); };
  }, []);

  async function choose(folder: boolean) {
    setError('');
    try {
      const paths = await pickAudio(folder);
      if (paths.length) onAddPaths(paths);
    } catch (e) { setError(String(e)); }
  }

  return <section className="bg-surface-1 border border-surface-3 rounded-xl p-5">
    <div className="border-2 border-dashed border-surface-3 rounded-xl p-6 text-center flex flex-col items-center gap-3">
      <Upload className="w-8 h-8 text-brand" />
      <h3 className="font-medium">{nativeDesktop() ? 'Drop audio files or folders into this window' : 'Add local audio by absolute path'}</h3>
      <p className="text-sm text-text-subtle">WAV, FLAC, MP3, and OGG • six aligned stems</p>
      {nativeDesktop() && <div className="flex gap-3">
        <button disabled={isAdding} onClick={() => choose(false)} className="flex items-center gap-2 bg-surface-2 rounded-lg px-4 py-2"><FileAudio size={16} />Add Files</button>
        <button disabled={isAdding} onClick={() => choose(true)} className="flex items-center gap-2 bg-surface-2 rounded-lg px-4 py-2"><FolderPlus size={16} />Add Folder</button>
      </div>}
    </div>
    <details className="mt-3" open={!nativeDesktop()}>
      <summary className="text-xs text-text-subtle cursor-pointer">Enter file or folder paths</summary>
      <form className="flex gap-3 mt-2" onSubmit={e => {
        e.preventDefault();
        const paths = text.split('\n').map(p => p.trim()).filter(Boolean);
        if (paths.length) { onAddPaths(paths); setText(''); }
      }}>
        <textarea aria-label="Absolute audio paths, one per line" value={text} onChange={e => setText(e.target.value)} rows={2} className="flex-1 bg-surface-0 rounded-lg p-2 text-sm" />
        <button disabled={!text.trim() || isAdding} className="bg-brand text-black rounded-lg px-4 disabled:opacity-50">Add to Queue</button>
      </form>
    </details>
    {error && <p role="alert" className="text-accent-crimson mt-2 text-sm">{error}</p>}
  </section>;
}
