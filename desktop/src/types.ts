export type JobStatus =
  | 'queued'
  | 'preparing'
  | 'separating'
  | 'packaging'
  | 'validating'
  | 'finalizing'
  | 'complete'
  | 'failed'
  | 'cancelled';

export interface JobRecord {
  id: string;
  source_path: string;
  output_library: string;
  source_hash?: string;
  model: string;
  device: string;
  actual_device?: string;
  fallback_to_cpu: boolean;
  overwrite: boolean;
  status: JobStatus;
  stage?: string;
  progress: number;
  progress_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_code?: string;
  diagnostic_message?: string;
  package_path?: string;
}

export interface QueueCounts {
  total: number;
  queued: number;
  active: number;
  complete: number;
  failed: number;
  cancelled: number;
}

export interface QueueResponse {
  jobs: JobRecord[];
  counts: QueueCounts;
  is_running: boolean;
  active_job_id?: string;
}

export interface IngestResult {
  added: JobRecord[];
  added_count: number;
  skipped_duplicate_queue: string[];
  skipped_existing_package: string[];
  invalid_files: string[];
}

export interface DoctorReport {
  stemLabVersion: string;
  python: string;
  platform: string;
  machine: string;
  torch: {
    available: boolean;
    version?: string;
    cudaAvailable: boolean;
    cudaRuntime?: string;
    mpsAvailable: boolean;
    detail?: string;
  };
  demucs: {
    available: boolean;
    version?: string;
    devices: string[];
    autoDevice: string;
    detail?: string;
  };
  input: {
    extensions: string[];
    ffmpegAvailable: boolean;
    ffprobeAvailable: boolean;
  };
  modelCache: {
    directory: string;
    models: Array<{
      name: string;
      signature: string;
      filename: string;
      url: string;
      cached: boolean;
      localPath?: string;
      sizeBytes?: number;
      expectedSizeBytes?: number;
    }>;
  };
  disk: {
    target: string;
    totalBytes: number;
    freeBytes: number;
    freeGb: number;
  };
}

export interface StemPackageInfo {
  path: string;
  folder_name: string;
  package_id?: string;
  created_at?: string;
  source?: {
    originalFilename?: string;
    format?: string;
    durationSeconds?: number;
  };
  model?: {
    engine?: string;
    name?: string;
    device?: string;
  };
  audio?: {
    sampleRate?: number;
    channels?: number;
  };
  stems: string[];
  size_bytes: number;
}

export interface LibraryResponse {
  library_path: string;
  packages: StemPackageInfo[];
}
