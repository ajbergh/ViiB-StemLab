import React from 'react';
import { Waves, Layers, FolderArchive, Settings, Cpu, Loader2 } from 'lucide-react';

interface NavbarProps {
  currentTab: 'queue' | 'library' | 'settings';
  onSelectTab: (tab: 'queue' | 'library' | 'settings') => void;
  queuedCount: number;
  isRunning: boolean;
  activeTrackName?: string;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  queuedCount,
  isRunning,
  activeTrackName,
}) => {
  return (
    <header className="h-16 bg-surface-1 border-b border-surface-3 px-6 flex items-center justify-between select-none">
      {/* Brand & Title */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-brand/15 border border-brand/30 flex items-center justify-center text-brand">
          <Waves className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-base font-bold text-text-main flex items-center gap-2">
            ViiB StemLab
            <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-surface-2 text-brand border border-brand/20">
              v0.1.0
            </span>
          </h1>
          <p className="text-[11px] text-text-subtle">
            Durable 6-Stem Preparation Engine for ViiB MediaHub
          </p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <nav className="flex items-center bg-surface-0 border border-surface-3 rounded-xl p-1 gap-1 text-xs">
        <button
          onClick={() => onSelectTab('queue')}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition-all ${
            currentTab === 'queue'
              ? 'bg-brand text-white shadow-sm'
              : 'text-text-subtle hover:text-text-secondary hover:bg-surface-2/60'
          }`}
        >
          <Layers className="w-4 h-4" />
          Queue
          {queuedCount > 0 && (
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                currentTab === 'queue'
                  ? 'bg-white/20 text-white'
                  : 'bg-surface-2 text-accent-orange border border-surface-3'
              }`}
            >
              {queuedCount}
            </span>
          )}
        </button>

        <button
          onClick={() => onSelectTab('library')}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition-all ${
            currentTab === 'library'
              ? 'bg-brand text-white shadow-sm'
              : 'text-text-subtle hover:text-text-secondary hover:bg-surface-2/60'
          }`}
        >
          <FolderArchive className="w-4 h-4" />
          Library
        </button>

        <button
          onClick={() => onSelectTab('settings')}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition-all ${
            currentTab === 'settings'
              ? 'bg-brand text-white shadow-sm'
              : 'text-text-subtle hover:text-text-secondary hover:bg-surface-2/60'
          }`}
        >
          <Settings className="w-4 h-4" />
          Settings & Doctor
        </button>
      </nav>

      {/* Engine Status Indicator */}
      <div className="flex items-center gap-2.5">
        {isRunning ? (
          <div className="flex items-center gap-2 bg-brand/10 border border-brand/30 px-3 py-1.5 rounded-lg text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-brand" />
            <div className="flex flex-col text-left">
              <span className="text-brand font-medium">Processing Queue</span>
              {activeTrackName && (
                <span className="text-[10px] text-text-subtle font-mono truncate max-w-[120px]">
                  {activeTrackName}
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 bg-surface-2 border border-surface-3 px-3 py-1.5 rounded-lg text-xs text-text-subtle">
            <Cpu className="w-3.5 h-3.5 text-text-subtle" />
            <span>Worker Idle</span>
          </div>
        )}
      </div>
    </header>
  );
};
