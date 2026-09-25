import React, { useState, useEffect } from 'react';
import {
  FolderArchive,
  Search,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Sliders,
  Disc3,
  Clock,
  Sparkles,
} from 'lucide-react';
import { StemPackageInfo } from '../types';
import { api } from '../api';

interface LibraryViewProps {
  libraryPath: string;
}

export const LibraryView: React.FC<LibraryViewProps> = ({ libraryPath }) => {
  const [packages, setPackages] = useState<StemPackageInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [validatingPath, setValidatingPath] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<
    Record<string, { valid: boolean; error?: string }>
  >({});

  const fetchLibrary = async () => {
    setIsLoading(true);
    try {
      const res = await api.getLibrary(libraryPath);
      setPackages(res.packages);
    } catch (e) {
      console.error('Failed to fetch library:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLibrary();
  }, [libraryPath]);

  const handleValidate = async (pkgPath: string) => {
    setValidatingPath(pkgPath);
    try {
      const res = await api.validatePackage(pkgPath);
      setValidationResults(prev => ({
        ...prev,
        [pkgPath]: { valid: res.valid, error: res.error },
      }));
    } catch (e: any) {
      setValidationResults(prev => ({
        ...prev,
        [pkgPath]: { valid: false, error: e.message },
      }));
    } finally {
      setValidatingPath(null);
    }
  };

  const filteredPackages = packages.filter(pkg => {
    const term = search.toLowerCase();
    const name = pkg.folder_name.toLowerCase();
    const id = pkg.package_id?.toLowerCase() || '';
    return name.includes(term) || id.includes(term);
  });

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header and Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-text-main flex items-center gap-2">
            <FolderArchive className="w-5 h-5 text-brand" />
            Stem Library Browser
          </h2>
          <p className="text-xs text-text-subtle mt-0.5 font-mono truncate max-w-xl">
            {libraryPath || 'Default Stem Library'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-text-subtle absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search packages..."
              className="bg-surface-1 border border-surface-3 rounded-lg pl-9 pr-3 py-1.5 text-xs text-text-main placeholder-text-subtle focus:outline-none focus:border-brand w-48 sm:w-64"
            />
          </div>

          <button
            onClick={fetchLibrary}
            disabled={isLoading}
            className="p-2 text-text-secondary hover:text-text-main bg-surface-1 hover:bg-surface-2 border border-surface-3 rounded-lg transition-colors"
            title="Refresh Library"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Package Grid / List */}
      {filteredPackages.length === 0 ? (
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-16 text-center">
          <Disc3 className="w-12 h-12 text-surface-3 mx-auto mb-3" />
          <h4 className="text-text-secondary font-medium mb-1">
            No stem packages found
          </h4>
          <p className="text-text-subtle text-xs max-w-sm mx-auto">
            Once queue jobs complete, separated .viibstems packages will appear here ready for ViiB MediaHub.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredPackages.map(pkg => {
            const val = validationResults[pkg.path];
            return (
              <div
                key={pkg.path}
                className="bg-surface-1 border border-surface-3 hover:border-surface-3/80 rounded-xl p-4 flex flex-col justify-between space-y-3 transition-all"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h3
                      className="font-semibold text-text-main text-sm truncate flex-1"
                      title={pkg.folder_name}
                    >
                      {pkg.folder_name.replace('.viibstems', '')}
                    </h3>
                    <span className="text-[10px] bg-brand/10 text-brand px-2 py-0.5 rounded font-mono uppercase tracking-wider font-semibold">
                      .viibstems
                    </span>
                  </div>

                  <div className="text-xs text-text-subtle font-mono truncate mt-0.5">
                    ID: {pkg.package_id || 'unassigned'}
                  </div>

                  <div className="flex items-center gap-3 text-xs text-text-subtle mt-2">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {formatDuration(pkg.source?.durationSeconds)}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Sparkles className="w-3.5 h-3.5 text-accent-blue" />
                      {pkg.model?.name || 'htdemucs'}
                    </span>
                    <span>•</span>
                    <span>{formatBytes(pkg.size_bytes)}</span>
                  </div>

                  {/* Stem pills */}
                  <div className="flex flex-wrap gap-1 mt-3">
                    {pkg.stems.map(stem => (
                      <span
                        key={stem}
                        className="text-[11px] px-2 py-0.5 bg-surface-2 text-text-secondary rounded-md border border-surface-3"
                      >
                        {stem}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Validation Status & Action */}
                <div className="pt-2 border-t border-surface-3 flex items-center justify-between text-xs">
                  {val ? (
                    val.valid ? (
                      <span className="flex items-center gap-1 text-accent-green font-medium">
                        <CheckCircle className="w-3.5 h-3.5" />
                        Valid ViiB Package
                      </span>
                    ) : (
                      <span
                        className="flex items-center gap-1 text-accent-crimson font-medium truncate max-w-[200px]"
                        title={val.error}
                      >
                        <AlertCircle className="w-3.5 h-3.5" />
                        Corrupt / Invalid
                      </span>
                    )
                  ) : (
                    <span className="text-text-subtle">Not validated</span>
                  )}

                  <button
                    onClick={() => handleValidate(pkg.path)}
                    disabled={validatingPath === pkg.path}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-surface-2 hover:bg-surface-3 text-text-secondary hover:text-text-main border border-surface-3 rounded-lg transition-colors disabled:opacity-50"
                  >
                    <Sliders className="w-3.5 h-3.5" />
                    {validatingPath === pkg.path ? 'Verifying...' : 'Validate'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
