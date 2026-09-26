import React, { useRef, useState } from 'react';
import { Upload, FolderPlus, FileAudio, Plus } from 'lucide-react';

interface DropZoneProps {
  onAddPaths: (paths: string[]) => void;
  isAdding: boolean;
}

export const DropZone: React.FC<DropZoneProps> = ({ onAddPaths, isAdding }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [showTextInput, setShowTextInput] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const setFolderRef = (el: HTMLInputElement | null) => {
    if (el) {
      el.setAttribute('webkitdirectory', '');
      el.setAttribute('directory', '');
      (el as any).webkitdirectory = true;
      (el as any).directory = true;
      el.removeAttribute('multiple');
    }
    folderInputRef.current = el;
  };

  const handleAddFiles = () => {
    if (typeof window !== 'undefined' && (window as any).__TAURI__?.dialog?.open) {
      (window as any).__TAURI__.dialog
        .open({
          multiple: true,
          filters: [{ name: 'Audio', extensions: ['wav', 'flac', 'mp3', 'ogg', 'm4a', 'opus'] }],
        })
        .then((selected: string[] | string | null) => {
          if (selected) {
            const selPaths = Array.isArray(selected) ? selected : [selected];
            if (selPaths.length > 0) onAddPaths(selPaths);
          }
        })
        .catch(() => {
          fileInputRef.current?.click();
        });
      return;
    }
    fileInputRef.current?.click();
  };

  const handleAddFolder = () => {
    if (typeof window !== 'undefined' && (window as any).__TAURI__?.dialog?.open) {
      (window as any).__TAURI__.dialog
        .open({ directory: true })
        .then((selected: string | null) => {
          if (selected) {
            onAddPaths([selected]);
          }
        })
        .catch(() => {
          folderInputRef.current?.click();
        });
      return;
    }
    folderInputRef.current?.click();
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      const hasNativePath = files.some((f: any) => Boolean(f.path));
      if (hasNativePath) {
        const paths = files
          .map((f: any) => f.path)
          .filter(Boolean);
        if (paths.length > 0) {
          onAddPaths(paths);
        }
      } else {
        setShowTextInput(true);
        setTextInput(files.map(f => f.name).join('\n'));
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const fileList = Array.from(files);
      const hasNativePath = fileList.some((f: any) => Boolean(f.path));

      if (hasNativePath) {
        const paths = fileList
          .map((f: any) => f.path)
          .filter(Boolean);
        if (paths.length > 0) {
          onAddPaths(paths);
        }
      } else {
        // In browser sandbox where f.path is not exposed, extract folder name if available
        let detectedFolderName = '';
        for (const f of fileList) {
          if (f.webkitRelativePath) {
            const parts = f.webkitRelativePath.split('/');
            if (parts.length > 1) {
              detectedFolderName = parts[0];
              break;
            }
          }
        }
        setShowTextInput(true);
        if (detectedFolderName) {
          setTextInput(`C:\\Music\\${detectedFolderName}`);
        } else {
          setTextInput(fileList.map(f => f.name).join('\n'));
        }
      }
      e.target.value = '';
    }
  };

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const paths = textInput
      .split('\n')
      .map(p => p.trim())
      .filter(p => p.length > 0);
    if (paths.length > 0) {
      onAddPaths(paths);
      setTextInput('');
      setShowTextInput(false);
    }
  };

  return (
    <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 shadow-sm">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-6 text-center transition-all flex flex-col items-center justify-center cursor-pointer ${
          isDragging
            ? 'border-brand bg-brand/5 scale-[0.99]'
            : 'border-surface-3 hover:border-brand/50 hover:bg-surface-2/40'
        }`}
        onClick={handleAddFiles}
      >
        <div className="w-12 h-12 rounded-full bg-surface-2 flex items-center justify-center mb-3 text-brand">
          <Upload className="w-6 h-6" />
        </div>
        <h3 className="text-card font-medium text-text-main mb-1">
          Drop audio files or folders here
        </h3>
        <p className="text-body text-text-subtle max-w-md text-sm mb-4">
          Accepts high-resolution WAV, FLAC, MP3, and OGG tracks for 6-stem AI separation.
        </p>

        <div className="flex items-center gap-3" onClick={e => e.stopPropagation()}>
          <button
            type="button"
            disabled={isAdding}
            onClick={handleAddFiles}
            className="flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg text-sm font-medium text-text-main transition-colors disabled:opacity-50"
          >
            <FileAudio className="w-4 h-4 text-accent-blue" />
            Add Files
          </button>

          <button
            type="button"
            disabled={isAdding}
            onClick={handleAddFolder}
            className="flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg text-sm font-medium text-text-main transition-colors disabled:opacity-50"
          >
            <FolderPlus className="w-4 h-4 text-accent-purple" />
            Add Folder
          </button>

          <button
            type="button"
            disabled={isAdding}
            onClick={() => setShowTextInput(!showTextInput)}
            className="flex items-center gap-2 px-3 py-2 bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg text-sm font-medium text-text-secondary transition-colors"
            title="Paste file/directory paths"
          >
            <Plus className="w-4 h-4" />
            Enter Path
          </button>
        </div>

        {/* Hidden inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".wav,.flac,.mp3,.ogg,audio/*"
          className="hidden"
          onChange={handleFileChange}
        />
        <input
          ref={setFolderRef}
          type="file"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {showTextInput && (
        <form onSubmit={handleTextSubmit} className="mt-4 pt-4 border-t border-surface-3">
          <label className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1">
            Audio File or Directory Path (one per line):
          </label>
          <div className="flex gap-2">
            <textarea
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              placeholder="C:\Music\Track.wav&#10;C:\DJ_Collection\Electro"
              rows={2}
              className="flex-1 bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-sm text-text-main placeholder-text-subtle focus:outline-none focus:border-brand font-mono"
            />
            <button
              type="submit"
              disabled={!textInput.trim() || isAdding}
              className="px-4 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 self-end"
            >
              Add to Queue
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
