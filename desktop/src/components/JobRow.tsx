import React, { useState } from 'react';
import {
  Clock,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Trash2,
  X,
  ChevronDown,
  ChevronUp,
  Cpu,
  Zap,
} from 'lucide-react';
import { JobRecord, JobStatus } from '../types';

interface JobRowProps {
  job: JobRecord;
  isActive: boolean;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onRemove: (jobId: string) => void;
}

export const JobRow: React.FC<JobRowProps> = ({
  job,
  isActive,
  onCancel,
  onRetry,
  onRemove,
}) => {
  const [showDetails, setShowDetails] = useState(false);

  // Extract clean filename from source_path
  const filename = job.source_path.split(/[/\\]/).pop() || job.source_path;

  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case 'queued':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-surface-2 text-text-secondary border border-surface-3">
            <Clock className="w-3.5 h-3.5 text-accent-orange" />
            Queued
          </span>
        );
      case 'preparing':
      case 'separating':
      case 'packaging':
      case 'validating':
      case 'finalizing':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-brand/15 text-brand border border-brand/30 animate-pulse">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-brand" />
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </span>
        );
      case 'complete':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-accent-green/10 text-accent-green border border-accent-green/30">
            <CheckCircle2 className="w-3.5 h-3.5 text-accent-green" />
            Complete
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-accent-crimson/10 text-accent-crimson border border-accent-crimson/30">
            <AlertTriangle className="w-3.5 h-3.5 text-accent-crimson" />
            Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-surface-2 text-text-subtle border border-surface-3">
            <X className="w-3.5 h-3.5" />
            Cancelled
          </span>
        );
    }
  };

  const isRunning = [
    'preparing',
    'separating',
    'packaging',
    'validating',
    'finalizing',
  ].includes(job.status);

  return (
    <div
      className={`bg-surface-1 border rounded-xl transition-all overflow-hidden ${
        isActive
          ? 'border-brand/50 shadow-md shadow-brand/5'
          : 'border-surface-3 hover:border-surface-3/80'
      }`}
    >
      <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Track Title and Meta */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            {getStatusBadge(job.status)}
            <h4
              className="font-medium text-text-main text-sm truncate"
              title={job.source_path}
            >
              {filename}
            </h4>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-text-subtle">
            <span title={job.source_path} className="truncate max-w-xs font-mono">
              {job.source_path}
            </span>
            <span>•</span>
            <span className="flex items-center gap-1 text-text-secondary">
              <Zap className="w-3 h-3 text-brand" />
              {job.model}
            </span>
            <span>•</span>
            <span className="flex items-center gap-1 text-text-secondary uppercase">
              <Cpu className="w-3 h-3 text-accent-blue" />
              {job.actual_device || job.device}
            </span>
          </div>
        </div>

        {/* Progress Display (if active) */}
        {isRunning && (
          <div className="w-full sm:w-48 flex flex-col justify-center gap-1">
            <div className="flex justify-between text-xs">
              <span className="text-text-secondary truncate max-w-[120px]">
                {job.stage || job.progress_message || 'Processing'}
              </span>
              <span className="font-mono text-brand font-medium">
                {Math.round(job.progress)}%
              </span>
            </div>
            <div className="w-full bg-surface-2 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-brand h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${Math.max(4, Math.min(100, job.progress))}%` }}
              />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 self-end sm:self-center">
          {isRunning && (
            <button
              onClick={() => onCancel(job.id)}
              className="p-1.5 text-text-secondary hover:text-accent-crimson hover:bg-surface-2 rounded-lg transition-colors"
              title="Cancel Job"
            >
              <X className="w-4 h-4" />
            </button>
          )}

          {job.status === 'queued' && (
            <button
              onClick={() => onCancel(job.id)}
              className="p-1.5 text-text-secondary hover:text-accent-crimson hover:bg-surface-2 rounded-lg transition-colors"
              title="Cancel Queued Job"
            >
              <X className="w-4 h-4" />
            </button>
          )}

          {(job.status === 'failed' || job.status === 'cancelled') && (
            <button
              onClick={() => onRetry(job.id)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-brand hover:text-white hover:bg-brand/20 border border-brand/30 rounded-lg transition-colors"
              title="Retry Job"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Retry
            </button>
          )}

          {(job.status === 'complete' ||
            job.status === 'failed' ||
            job.status === 'cancelled') && (
            <button
              onClick={() => onRemove(job.id)}
              className="p-1.5 text-text-subtle hover:text-accent-crimson hover:bg-surface-2 rounded-lg transition-colors"
              title="Remove from List"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}

          {(job.error_code || job.package_path) && (
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="p-1.5 text-text-subtle hover:text-text-main hover:bg-surface-2 rounded-lg transition-colors"
              title={showDetails ? 'Hide Details' : 'Show Details'}
            >
              {showDetails ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Expanded Details / Errors */}
      {showDetails && (
        <div className="bg-surface-0 px-4 py-3 border-t border-surface-3 text-xs">
          {job.error_code && (
            <div className="mb-2">
              <span className="font-semibold text-accent-crimson">
                Error [{job.error_code}]:{' '}
              </span>
              <span className="text-text-secondary font-mono">
                {job.diagnostic_message || 'Separation failed.'}
              </span>
            </div>
          )}

          {job.package_path && (
            <div>
              <span className="font-semibold text-accent-green">Package: </span>
              <span className="text-text-secondary font-mono">{job.package_path}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
