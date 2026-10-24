import React, { useState, useEffect } from 'react';
import {
  Settings,
  Activity,
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  Folder,
  RefreshCw,
} from 'lucide-react';
import { DoctorReport, Preferences } from '../types';
import { api } from '../api';
import { ModelSetup } from './ModelSetup';
import { CudaSetup } from './CudaSetup';
import { nativeDesktop, pickAudio } from '../desktop';

interface SettingsDoctorViewProps {
  concurrency: Preferences['concurrency'];
  onUpdateConcurrency: (value: Preferences['concurrency']) => void;
  outputFormat: Preferences['output_format'];
  onUpdateOutputFormat: (format: Preferences['output_format']) => void;
  libraryPath: string;
  onUpdateLibraryPath: (path: string) => Promise<unknown>;
  defaultModel: string;
  onUpdateDefaultModel: (model: string) => void;
  devicePreference: string;
  onUpdateDevicePreference: (device: string) => void;
  fallbackToCpu: boolean;
  onUpdateFallbackToCpu: (val: boolean) => void;
}

export const SettingsDoctorView: React.FC<SettingsDoctorViewProps> = ({
  concurrency,
  onUpdateConcurrency,
  outputFormat,
  onUpdateOutputFormat,
  libraryPath,
  onUpdateLibraryPath,
  defaultModel,
  onUpdateDefaultModel,
  devicePreference,
  onUpdateDevicePreference,
  fallbackToCpu,
  onUpdateFallbackToCpu,
}) => {
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [libraryDraft, setLibraryDraft] = useState(libraryPath);
  const [error, setError] = useState('');
  const saveLibrary = async (path: string) => {
    try { await onUpdateLibraryPath(path); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  const fetchDoctor = async () => {
    setIsLoading(true);
    try {
      const doc = await api.getDoctor();
      setDoctor(doc);
    } catch (e) {
      setError(`Could not inspect audio engine: ${e instanceof Error ? e.message : e}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDoctor();
  }, []);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-main flex items-center gap-2">
            <Settings className="w-5 h-5 text-brand" />
            Engine Settings & System Diagnostics
          </h2>
          <p className="text-xs text-text-subtle mt-0.5">
            Configure output directories, hardware acceleration, and inspect runtime capabilities.
          </p>
        </div>

        <button
          onClick={fetchDoctor}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-secondary hover:text-text-main bg-surface-1 hover:bg-surface-2 border border-surface-3 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Run Doctor
        </button>
      </div>

      {error && <p role="alert" className="text-accent-crimson">{error}</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Settings Panel */}
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 space-y-4">
          <h3 className="text-card font-medium text-text-main flex items-center gap-2 pb-2 border-b border-surface-3">
            <Folder className="w-4 h-4 text-brand" />
            Library & Output Settings
          </h3>

          <div>
            <label htmlFor="song-concurrency" className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Songs at the same time
            </label>
            <select id="song-concurrency" value={concurrency}
              onChange={e => onUpdateConcurrency(Number(e.target.value) as Preferences['concurrency'])}
              className="w-full bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-brand">
              <option value={1}>1 song (default)</option>
              <option value={2}>2 songs</option>
              <option value={3}>3 songs</option>
            </select>
            <p className="text-xs text-text-subtle mt-1.5">More songs use more RAM and GPU memory and may not finish faster. Changes apply as slots become available; running songs finish when you lower the limit.</p>
          </div>

          <div>
            <label htmlFor="output-format" className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Stem Export Format
            </label>
            <select id="output-format" value={outputFormat}
              onChange={e => onUpdateOutputFormat(e.target.value as Preferences['output_format'])}
              className="w-full bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-brand">
              <option value="wav">WAV (default)</option>
              <option value="ogg">OGG Vorbis</option>
              <option value="mp3">MP3</option>
            </select>
            <p className="text-xs text-text-subtle mt-1.5">Applies to newly added tracks. Only the selected format is saved. OGG and MP3 use less storage with lossy compression.</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Default Stem Library Path
            </label>
            <input
              type="text"
              value={libraryDraft}
              onChange={e => setLibraryDraft(e.target.value)}
              placeholder="C:\Users\...\Music\ViiB Stems"
              className="w-full bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs font-mono text-text-main placeholder-text-subtle focus:outline-none focus:border-brand"
            />
            <div className="flex gap-3 mt-2">
              <button className="bg-surface-2 px-3 py-1 rounded" onClick={() => saveLibrary(libraryDraft)}>Save folder</button>
              {nativeDesktop() && <button className="bg-surface-2 px-3 py-1 rounded" onClick={async () => {
                try { const paths = await pickAudio(true); if (paths[0]) { setLibraryDraft(paths[0]); await saveLibrary(paths[0]); } }
                catch (e) { setError(String(e)); }
              }}>Choose folder...</button>}
            </div>
            <p className="text-[11px] text-text-subtle mt-1">
              Generated .viibstems packages are written here.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Default Model
            </label>
            <select
              value={defaultModel}
              onChange={e => onUpdateDefaultModel(e.target.value)}
              className="w-full bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-brand"
            >
              <option value="htdemucs_ft">
                htdemucs_ft (4-Stem: Vocals, Drums, Bass, Other)
              </option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Compute Device Preference
            </label>
            <select
              value={devicePreference}
              onChange={e => onUpdateDevicePreference(e.target.value)}
              className="w-full bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-brand"
            >
              <option value="auto">Auto (Choose fastest available: CUDA &gt; MPS &gt; CPU)</option>
              <option value="cuda">CUDA (NVIDIA GPU Acceleration)</option>
              <option value="mps">MPS (Apple Silicon Metal Performance Shaders)</option>
              <option value="cpu">CPU (Safe multi-threaded CPU fallback)</option>
            </select>
          </div>

          <div className="pt-2">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={fallbackToCpu}
                onChange={e => onUpdateFallbackToCpu(e.target.checked)}
                className="w-4 h-4 rounded text-brand focus:ring-brand border-surface-3 bg-surface-0"
              />
              <span className="text-xs text-text-secondary">
                Automatically fall back to CPU if GPU runs out of VRAM or encounters errors
              </span>
            </label>
          </div>
        </div>

        <ModelSetup />
        <CudaSetup />
      </div>

      {/* System Doctor & Environment Card */}
      {doctor && (
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 space-y-4">
          <h3 className="text-card font-medium text-text-main flex items-center gap-2 pb-2 border-b border-surface-3">
            <Activity className="w-4 h-4 text-accent-green" />
            Environment Diagnostics (Doctor)
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            {/* PyTorch Card */}
            <div className="bg-surface-0 border border-surface-3 rounded-lg p-3 space-y-1.5">
              <div className="font-semibold text-text-secondary flex items-center justify-between">
                <span>PyTorch Engine</span>
                {doctor.torch.available ? (
                  <CheckCircle2 className="w-4 h-4 text-accent-green" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-accent-crimson" />
                )}
              </div>
              <div className="text-text-main font-mono">
                {doctor.torch.available ? `v${doctor.torch.version}` : 'Not available'}
              </div>
              <div className="text-text-subtle text-[11px]">
                CUDA acceleration:{' '}
                <span
                  className={
                    doctor.torch.cudaAvailable || doctor.cudaWorker?.ready ? 'text-accent-green' : 'text-text-subtle'
                  }
                >
                  {doctor.torch.cudaAvailable
                    ? `Active (${doctor.torch.cudaRuntime || 'Ready'})`
                    : doctor.cudaWorker?.ready ? 'Ready (downloaded worker)' : 'Not ready'}
                </span>
              </div>
              <div className="text-text-subtle text-[11px]">
                Apple MPS:{' '}
                <span
                  className={
                    doctor.torch.mpsAvailable ? 'text-accent-green' : 'text-text-subtle'
                  }
                >
                  {doctor.torch.mpsAvailable ? 'Active' : 'No'}
                </span>
              </div>
            </div>

            {/* Demucs Card */}
            <div className="bg-surface-0 border border-surface-3 rounded-lg p-3 space-y-1.5">
              <div className="font-semibold text-text-secondary flex items-center justify-between">
                <span>Demucs Separation</span>
                {doctor.demucs.available ? (
                  <CheckCircle2 className="w-4 h-4 text-accent-green" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-accent-orange" />
                )}
              </div>
              <div className="text-text-main font-mono">
                {doctor.demucs.available ? `v${doctor.demucs.version}` : 'Not installed'}
              </div>
              <div className="text-text-subtle text-[11px]">
                Auto Device:{' '}
                <span className="text-brand font-medium uppercase">
                  {doctor.demucs.autoDevice}
                </span>
              </div>
              <div className="text-text-subtle text-[11px] truncate">
                Available: {doctor.demucs.devices.join(', ')}
              </div>
            </div>

            {/* FFmpeg Tools */}
            <div className="bg-surface-0 border border-surface-3 rounded-lg p-3 space-y-1.5">
              <div className="font-semibold text-text-secondary flex items-center justify-between">
                <span>Audio Tools</span>
                {doctor.input.ffmpegAvailable && doctor.input.ffprobeAvailable ? (
                  <CheckCircle2 className="w-4 h-4 text-accent-green" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-accent-orange" />
                )}
              </div>
              <div className="text-text-subtle text-[11px]">
                FFmpeg:{' '}
                <span
                  className={
                    doctor.input.ffmpegAvailable ? 'text-accent-green' : 'text-accent-crimson'
                  }
                >
                  {doctor.input.ffmpegAvailable ? 'Available' : 'Missing'}
                </span>
              </div>
              <div className="text-text-subtle text-[11px]">
                FFprobe:{' '}
                <span
                  className={
                    doctor.input.ffprobeAvailable ? 'text-accent-green' : 'text-accent-crimson'
                  }
                >
                  {doctor.input.ffprobeAvailable ? 'Available' : 'Missing'}
                </span>
              </div>
              <div className="text-text-subtle text-[11px] truncate">
                Formats: {doctor.input.extensions.join(' ')}
              </div>
            </div>

            {/* Disk Space */}
            <div className="bg-surface-0 border border-surface-3 rounded-lg p-3 space-y-1.5">
              <div className="font-semibold text-text-secondary flex items-center justify-between">
                <span>Storage Free</span>
                <HardDrive className="w-4 h-4 text-brand" />
              </div>
              <div className="text-text-main font-mono font-bold text-sm">
                {doctor.disk.freeGb} GB
              </div>
              <div className="text-text-subtle text-[11px] truncate" title={doctor.disk.target}>
                Drive: {doctor.disk.target}
              </div>
              <div className="text-text-subtle text-[11px]">
                Platform: {doctor.platform}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
