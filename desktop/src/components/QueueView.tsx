import React, { useState } from 'react';
import {
  Play,
  Square,
  Trash2,
  RefreshCw,
  ListFilter,
  Layers,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { QueueResponse, JobStatus } from '../types';
import { DropZone } from './DropZone';
import { JobRow } from './JobRow';

interface QueueViewProps {
  queueData: QueueResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
  onAddPaths: (paths: string[]) => void;
  onStartQueue: () => void;
  onStopQueue: () => void;
  onCancelJob: (jobId: string) => void;
  onRetryJob: (jobId: string) => void;
  onRemoveJob: (jobId: string) => void;
  onClearJobs: (status?: string) => void;
}

export const QueueView: React.FC<QueueViewProps> = ({
  queueData,
  isLoading,
  onRefresh,
  onAddPaths,
  onStartQueue,
  onStopQueue,
  onCancelJob,
  onRetryJob,
  onRemoveJob,
  onClearJobs,
}) => {
  const [filter, setFilter] = useState<'all' | JobStatus>('all');
  const [isAdding, setIsAdding] = useState(false);

  const jobs = queueData?.jobs || [];
  const counts = queueData?.counts || {
    total: 0,
    queued: 0,
    active: 0,
    complete: 0,
    failed: 0,
    cancelled: 0,
  };
  const isRunning = queueData?.is_running ?? false;

  const handleAdd = async (paths: string[]) => {
    setIsAdding(true);
    try {
      await onAddPaths(paths);
    } finally {
      setIsAdding(false);
    }
  };

  const filteredJobs = jobs.filter(job => {
    if (filter === 'all') return true;
    if (filter === 'preparing' || filter === 'separating') {
      return ['preparing', 'separating', 'packaging', 'validating', 'finalizing'].includes(
        job.status
      );
    }
    return job.status === filter;
  });

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* KPI Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-text-subtle uppercase tracking-wider">
              Total Jobs
            </div>
            <div className="text-2xl font-bold text-text-main mt-1">
              {counts.total}
            </div>
          </div>
          <Layers className="w-6 h-6 text-text-subtle" />
        </div>

        <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-text-subtle uppercase tracking-wider">
              Queued
            </div>
            <div className="text-2xl font-bold text-accent-orange mt-1">
              {counts.queued}
            </div>
          </div>
          <Clock className="w-6 h-6 text-accent-orange/60" />
        </div>

        <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-text-subtle uppercase tracking-wider">
              Processing
            </div>
            <div className="text-2xl font-bold text-brand mt-1">
              {counts.active}
            </div>
          </div>
          <div
            className={`w-3 h-3 rounded-full ${
              isRunning ? 'bg-brand animate-ping' : 'bg-surface-3'
            }`}
          />
        </div>

        <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-text-subtle uppercase tracking-wider">
              Complete
            </div>
            <div className="text-2xl font-bold text-accent-green mt-1">
              {counts.complete}
            </div>
          </div>
          <CheckCircle2 className="w-6 h-6 text-accent-green/60" />
        </div>

        <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 flex items-center justify-between col-span-2 sm:col-span-1">
          <div>
            <div className="text-xs font-semibold text-text-subtle uppercase tracking-wider">
              Failed
            </div>
            <div className="text-2xl font-bold text-accent-crimson mt-1">
              {counts.failed}
            </div>
          </div>
          <AlertTriangle className="w-6 h-6 text-accent-crimson/60" />
        </div>
      </div>

      {/* DropZone for adding files / folders */}
      <DropZone onAddPaths={handleAdd} isAdding={isAdding} />

      {/* Main Queue Management Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
        {/* Runner Controls */}
        <div className="flex items-center gap-2">
          {isRunning ? (
            <button
              onClick={onStopQueue}
              className="flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg text-sm font-medium text-accent-orange transition-colors"
            >
              <Square className="w-4 h-4 fill-current" />
              Pause Worker
            </button>
          ) : (
            <button
              onClick={onStartQueue}
              disabled={counts.queued === 0}
              className="flex items-center gap-2 px-5 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg text-sm font-medium shadow-md shadow-brand/20 transition-all disabled:opacity-50"
            >
              <Play className="w-4 h-4 fill-current" />
              Start Processing ({counts.queued})
            </button>
          )}

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-2 text-text-secondary hover:text-text-main bg-surface-1 hover:bg-surface-2 border border-surface-3 rounded-lg transition-colors"
            title="Refresh Queue"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Filters and Clear actions */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Status Filter Buttons */}
          <div className="flex items-center bg-surface-1 border border-surface-3 rounded-lg p-1 text-xs">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'all'
                  ? 'bg-surface-3 text-text-main font-medium'
                  : 'text-text-subtle hover:text-text-secondary'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilter('queued')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'queued'
                  ? 'bg-surface-3 text-accent-orange font-medium'
                  : 'text-text-subtle hover:text-text-secondary'
              }`}
            >
              Queued ({counts.queued})
            </button>
            <button
              onClick={() => setFilter('complete')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'complete'
                  ? 'bg-surface-3 text-accent-green font-medium'
                  : 'text-text-subtle hover:text-text-secondary'
              }`}
            >
              Done ({counts.complete})
            </button>
            <button
              onClick={() => setFilter('failed')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'failed'
                  ? 'bg-surface-3 text-accent-crimson font-medium'
                  : 'text-text-subtle hover:text-text-secondary'
              }`}
            >
              Failed ({counts.failed})
            </button>
          </div>

          {counts.complete > 0 && (
            <button
              onClick={() => onClearJobs('complete')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-subtle hover:text-text-secondary bg-surface-1 hover:bg-surface-2 border border-surface-3 rounded-lg transition-colors"
              title="Clear Completed Jobs"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear Done
            </button>
          )}

          {counts.failed > 0 && (
            <button
              onClick={() => onClearJobs('failed')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-accent-crimson/80 hover:text-accent-crimson bg-surface-1 hover:bg-surface-2 border border-surface-3 rounded-lg transition-colors"
              title="Clear Failed Jobs"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear Failed
            </button>
          )}
        </div>
      </div>

      {/* Queue Job List */}
      <div className="space-y-2.5">
        {filteredJobs.length === 0 ? (
          <div className="bg-surface-1 border border-surface-3 rounded-xl p-12 text-center">
            <ListFilter className="w-10 h-10 text-surface-3 mx-auto mb-3" />
            <h4 className="text-text-secondary font-medium mb-1">
              No jobs in this view
            </h4>
            <p className="text-text-subtle text-xs">
              Add audio tracks or change the filter above to view queue activity.
            </p>
          </div>
        ) : (
          filteredJobs.map(job => (
            <JobRow
              key={job.id}
              job={job}
              isActive={job.id === queueData?.active_job_id}
              onCancel={onCancelJob}
              onRetry={onRetryJob}
              onRemove={onRemoveJob}
            />
          ))
        )}
      </div>
    </div>
  );
};
