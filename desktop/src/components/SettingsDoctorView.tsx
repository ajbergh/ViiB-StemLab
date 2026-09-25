import React, { useState, useEffect } from 'react';
import {
  Settings,
  Activity,
  HardDrive,
  DownloadCloud,
  CheckCircle2,
  AlertTriangle,
  Folder,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { DoctorReport } from '../types';
import { api } from '../api';

interface SettingsDoctorViewProps {
  libraryPath: string;
  onUpdateLibraryPath: (path: string) => void;
  defaultModel: string;
  onUpdateDefaultModel: (model: string) => void;
  devicePreference: string;
  onUpdateDevicePreference: (device: string) => void;
  fallbackToCpu: boolean;
  onUpdateFallbackToCpu: (val: boolean) => void;
}

export const SettingsDoctorView: React.FC<SettingsDoctorViewProps> = ({
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
  const [downloadingModel, setDownloadingModel] = useState<string | null>(null);

  const fetchDoctor = async () => {
    setIsLoading(true);
    try {
      const doc = await api.getDoctor();
      setDoctor(doc);
    } catch (e) {
      console.error('Failed to load system doctor:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDoctor();
  }, []);

  const handleDownloadModel = async (modelName: string) => {
    setDownloadingModel(modelName);
    try {
      await api.downloadModel(modelName);
      // Poll doctor after brief delay
      setTimeout(fetchDoctor, 2500);
    } catch (e) {
      console.error('Model download error:', e);
    } finally {
      setDownloadingModel(null);
    }
  };

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Settings Panel */}
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 space-y-4">
          <h3 className="text-card font-medium text-text-main flex items-center gap-2 pb-2 border-b border-surface-3">
            <Folder className="w-4 h-4 text-brand" />
            Library & Output Settings
          </h3>

          <div>
            <label className="block text-xs font-semibold text-text-subtle uppercase tracking-wider mb-1.5">
              Default Stem Library Path
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={libraryPath}
                onChange={e => onUpdateLibraryPath(e.target.value)}
                placeholder="C:\Users\...\Music\ViiB Stems"
                className="flex-1 bg-surface-0 border border-surface-3 rounded-lg px-3 py-2 text-xs font-mono text-text-main placeholder-text-subtle focus:outline-none focus:border-brand"
              />
              <button
                type="button"
                onClick={async () => {
                  try {
                    const res = await api.pickFolder('Select Stem Library Folder', libraryPath);
                    if (res.path) {
                      onUpdateLibraryPath(res.path);
                    }
                  } catch (err) {
                    console.error('Failed to pick folder', err);
                  }
                }}
                className="px-3 py-2 bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg text-xs font-medium text-text-main transition-colors whitespace-nowrap"
              >
                Browse...
              </button>
            </div>
            <p className="text-[11px] text-text-subtle mt-1">
              Generated .viibstems packages are written here and automatically discovered by ViiB MediaHub.
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
              <option value="htdemucs_6s">
                htdemucs_6s (Recommended 6-Stem: Vocals, Drums, Bass, Other, Guitar, Piano)
              </option>
              <option value="htdemucs">
                htdemucs (4-Stem Standard: Vocals, Drums, Bass, Other)
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

        {/* Model Cache Management */}
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 space-y-4">
          <h3 className="text-card font-medium text-text-main flex items-center gap-2 pb-2 border-b border-surface-3">
            <DownloadCloud className="w-4 h-4 text-accent-blue" />
            Model Weight Cache
          </h3>

          <div className="text-xs text-text-subtle">
            Cache Directory:{' '}
            <span className="font-mono text-text-secondary break-all">
              {doctor?.modelCache?.directory || 'Loading...'}
            </span>
          </div>

          <div className="space-y-3">
            {doctor?.modelCache?.models.map(m => {
              const isDownloading = downloadingModel === m.name;
              const sizeMb = m.sizeBytes
                ? Math.round(m.sizeBytes / (1024 * 1024))
                : m.expectedSizeBytes
                ? Math.round(m.expectedSizeBytes / (1024 * 1024))
                : null;

              return (
                <div
                  key={m.name}
                  className="bg-surface-0 border border-surface-3 rounded-lg p-3 flex items-center justify-between"
                >
                  <div>
                    <div className="font-medium text-text-main text-xs flex items-center gap-2">
                      <Zap className="w-3.5 h-3.5 text-brand" />
                      {m.name}
                      {m.name === defaultModel && (
                        <span className="text-[10px] bg-brand/20 text-brand px-1.5 py-0.2 rounded font-mono">
                          Active Default
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-text-subtle mt-0.5">
                      {sizeMb ? `~${sizeMb} MB` : ''} • {m.filename}
                    </div>
                  </div>

                  <div>
                    {m.cached ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-accent-green bg-accent-green/10 border border-accent-green/20 px-2 py-1 rounded-md">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Cached
                      </span>
                    ) : (
                      <button
                        onClick={() => handleDownloadModel(m.name)}
                        disabled={isDownloading}
                        className="flex items-center gap-1 text-xs font-medium bg-brand/10 hover:bg-brand/20 text-brand border border-brand/30 px-2.5 py-1 rounded-md transition-colors disabled:opacity-50"
                      >
                        <DownloadCloud className="w-3.5 h-3.5" />
                        {isDownloading ? 'Downloading...' : 'Download Weights'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
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
                CUDA GPU:{' '}
                <span
                  className={
                    doctor.torch.cudaAvailable ? 'text-accent-green' : 'text-text-subtle'
                  }
                >
                  {doctor.torch.cudaAvailable
                    ? `Active (${doctor.torch.cudaRuntime || 'Ready'})`
                    : 'No'}
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
