import { useState, useEffect, useCallback, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { QueueView } from './components/QueueView';
import { LibraryView } from './components/LibraryView';
import { SettingsDoctorView } from './components/SettingsDoctorView';
import { QueueResponse, Preferences } from './types';
import { ModelSetup } from './components/ModelSetup';
import { api } from './api';

export function App({ initialPreferences }: { initialPreferences: Preferences }) {
  const [currentTab, setCurrentTab] = useState<'queue' | 'library' | 'settings'>('queue');
  const [queueData, setQueueData] = useState<QueueResponse | null>(null);
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);
  const [preferences, setPreferences] = useState(initialPreferences);
  const [connectionError, setConnectionError] = useState('');
  const { library_path: libraryPath, model: defaultModel, device: devicePreference, fallback_to_cpu: fallbackToCpu } = preferences;

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimeoutRef = useRef<number | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = window.setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  const savePreferences = async (values: Partial<Preferences>) => {
    try { setPreferences(await api.saveSettings(values)); }
    catch (e) { showToast(`Could not save settings: ${e instanceof Error ? e.message : e}`); throw e; }
  };
  const handleUpdateLibraryPath = (path: string) => savePreferences({ library_path: path });
  const handleUpdateDefaultModel = (model: string) => { void savePreferences({ model }).catch(() => {}); };
  const handleUpdateDevicePreference = (device: string) => { void savePreferences({ device }).catch(() => {}); };
  const handleUpdateFallbackToCpu = (fallback_to_cpu: boolean) => { void savePreferences({ fallback_to_cpu }).catch(() => {}); };

  const fetchQueue = useCallback(async () => {
    try {
      const data = await api.getQueue();
      setQueueData(data);
      setConnectionError('');
    } catch (e) {
      setConnectionError(`Audio engine connection lost. ${e instanceof Error ? e.message : e}. Close and reopen StemLab if the engine has stopped.`);
    }
  }, []);

  // Poll queue
  useEffect(() => {
    fetchQueue();

    const intervalMs = queueData?.counts.active || queueData?.is_running ? 1500 : 4000;
    const interval = setInterval(fetchQueue, intervalMs);
    return () => clearInterval(interval);
  }, [fetchQueue, queueData?.counts.active, queueData?.is_running]);

  const handleAddPaths = async (paths: string[]) => {
    try {
      const result = await api.addPaths(paths, {
        output_library: libraryPath || undefined,
        model: defaultModel,
        device: devicePreference,
        fallback_to_cpu: fallbackToCpu,
        output_format: preferences.output_format,
      });

      let msg = `Added ${result.added_count} track(s) to queue.`;
      if (result.skipped_existing_package.length > 0) {
        msg += ` Skipped ${result.skipped_existing_package.length} existing package(s).`;
      }
      if (result.skipped_duplicate_queue.length > 0) {
        msg += ` Skipped ${result.skipped_duplicate_queue.length} already queued.`;
      }
      if (result.invalid_files.length) msg += ` Unable to add: ${result.invalid_files.join(', ')}`;
      showToast(msg);
      await fetchQueue();
    } catch (e: any) {
      showToast(`Error adding tracks: ${e.message}`);
    }
  };

  const handleStartQueue = async () => {
    try {
      await api.startQueue();
      showToast('Queue processing started.');
      await fetchQueue();
    } catch (e: any) {
      showToast(`Failed to start queue: ${e.message}`);
    }
  };

  const handleStopQueue = async () => {
    try {
      await api.stopQueue(false);
      showToast('Queue worker paused.');
      await fetchQueue();
    } catch (e: any) {
      showToast(`Failed to stop queue: ${e.message}`);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelJob(jobId, 'Cancelled by user via UI');
      showToast('Job cancelled.');
      await fetchQueue();
    } catch (e: any) {
      showToast(`Cancel failed: ${e.message}`);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryJob(jobId);
      showToast('Job reset to queued.');
      await fetchQueue();
    } catch (e: any) {
      showToast(`Retry failed: ${e.message}`);
    }
  };

  const handleRemoveJob = async (jobId: string) => {
    try {
      await api.removeJob(jobId);
      showToast('Job removed from queue.');
      await fetchQueue();
    } catch (e: any) {
      showToast(`Remove failed: ${e.message}`);
    }
  };

  const handleClearJobs = async (status?: string) => {
    try {
      const res = await api.clearJobs(status);
      showToast(`Cleared ${res.cleared_count} job(s).`);
      await fetchQueue();
    } catch (e: any) {
      showToast(`Clear failed: ${e.message}`);
    }
  };

  // Find active track filename if running
  const activeJob = queueData?.jobs.find(j => j.id === queueData.active_job_id);
  const activeTrackName = activeJob
    ? activeJob.source_path.split(/[/\\]/).pop()
    : undefined;

  return (
    <div className="h-screen w-screen flex flex-col bg-surface-0 text-text-main">
      <Navbar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        queuedCount={queueData?.counts.queued || 0}
        isRunning={queueData?.is_running ?? false}
        activeTrackName={activeTrackName}
      />

      {connectionError && <div role="alert" className="bg-accent-crimson/10 text-accent-crimson p-3 text-sm">{connectionError}</div>}
      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden relative">
        {currentTab === 'queue' && (
          <div className="flex-1 flex flex-col min-h-0 min-w-0">
          <ModelSetup compact />
          <QueueView
            queueData={queueData}
            isLoading={isLoadingQueue}
            onRefresh={async () => {
              setIsLoadingQueue(true);
              await fetchQueue();
              setIsLoadingQueue(false);
            }}
            onAddPaths={handleAddPaths}
            onStartQueue={handleStartQueue}
            onStopQueue={handleStopQueue}
            onCancelJob={handleCancelJob}
            onRetryJob={handleRetryJob}
            onRemoveJob={handleRemoveJob}
            onClearJobs={handleClearJobs}
          />
          </div>
        )}

        {currentTab === 'library' && (
          <LibraryView libraryPath={libraryPath} />
        )}

        {currentTab === 'settings' && (
          <SettingsDoctorView
            outputFormat={preferences.output_format || 'wav'}
            onUpdateOutputFormat={output_format => { void savePreferences({ output_format }).catch(() => {}); }}
            libraryPath={libraryPath}
            onUpdateLibraryPath={handleUpdateLibraryPath}
            defaultModel={defaultModel}
            onUpdateDefaultModel={handleUpdateDefaultModel}
            devicePreference={devicePreference}
            onUpdateDevicePreference={handleUpdateDevicePreference}
            fallbackToCpu={fallbackToCpu}
            onUpdateFallbackToCpu={handleUpdateFallbackToCpu}
          />
        )}

        {/* Global Toast Notification */}
        {toastMessage && (
          <div className="absolute bottom-6 right-6 bg-surface-2 border border-brand/40 text-text-main text-xs px-4 py-2.5 rounded-xl shadow-xl shadow-black/50 z-50 animate-fade-in flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand" />
            {toastMessage}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
