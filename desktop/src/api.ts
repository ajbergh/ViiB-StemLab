import {
  DoctorReport,
  IngestResult,
  LibraryResponse,
  QueueResponse,
  JobRecord,
} from './types';

const BASE_URL = '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(errorBody.error || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export const api = {
  getQueue: (status?: string): Promise<QueueResponse> => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return fetchJson<QueueResponse>(`/api/queue${q}`);
  },

  addPaths: (
    paths: string[],
    options?: {
      output_library?: string;
      model?: string;
      device?: string;
      fallback_to_cpu?: boolean;
      overwrite?: boolean;
    }
  ): Promise<IngestResult> => {
    return fetchJson<IngestResult>('/api/queue/add', {
      method: 'POST',
      body: JSON.stringify({
        paths,
        ...options,
      }),
    });
  },

  startQueue: (): Promise<{ status: string; is_running: boolean }> => {
    return fetchJson('/api/queue/start', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  stopQueue: (cancelActive = false): Promise<{ status: string; is_running: boolean }> => {
    return fetchJson('/api/queue/stop', {
      method: 'POST',
      body: JSON.stringify({ cancel_active: cancelActive }),
    });
  },

  cancelJob: (jobId: string, reason?: string): Promise<{ job_id: string; cancelled: boolean }> => {
    return fetchJson('/api/queue/cancel', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId, reason }),
    });
  },

  retryJob: (jobId: string): Promise<{ job: JobRecord }> => {
    return fetchJson('/api/queue/retry', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId }),
    });
  },

  removeJob: (jobId: string): Promise<{ job_id: string; deleted: boolean }> => {
    return fetchJson('/api/queue/remove', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId }),
    });
  },

  clearJobs: (status?: string): Promise<{ cleared_count: number }> => {
    return fetchJson('/api/queue/clear', {
      method: 'POST',
      body: JSON.stringify({ status }),
    });
  },

  getDoctor: (): Promise<DoctorReport> => {
    return fetchJson<DoctorReport>('/api/doctor');
  },

  getModels: (): Promise<{
    cache_dir: string;
    models: Array<{
      name: string;
      signature: string;
      filename: string;
      cached: boolean;
      size_bytes?: number;
      expected_size_bytes?: number;
      is_default: boolean;
    }>;
  }> => {
    return fetchJson('/api/models');
  },

  downloadModel: (model: string): Promise<{ status: string; model: string }> => {
    return fetchJson('/api/models/download', {
      method: 'POST',
      body: JSON.stringify({ model }),
    });
  },

  getLibrary: (path?: string): Promise<LibraryResponse> => {
    const q = path ? `?path=${encodeURIComponent(path)}` : '';
    return fetchJson<LibraryResponse>(`/api/library${q}`);
  },

  validatePackage: (
    packagePath: string,
    sourcePath?: string
  ): Promise<{ valid: boolean; package_id?: string; error?: string }> => {
    return fetchJson('/api/package/validate', {
      method: 'POST',
      body: JSON.stringify({ package_path: packagePath, source_path: sourcePath }),
    });
  },

  pickFolder: (
    title?: string,
    initialDir?: string
  ): Promise<{ path?: string | null; cancelled?: boolean; unsupported?: boolean }> => {
    return fetchJson('/api/dialog/folder', {
      method: 'POST',
      body: JSON.stringify({ title, initial_dir: initialDir }),
    });
  },

  pickFiles: (
    title?: string,
    initialDir?: string
  ): Promise<{ paths: string[]; cancelled?: boolean; unsupported?: boolean }> => {
    return fetchJson('/api/dialog/files', {
      method: 'POST',
      body: JSON.stringify({ title, initial_dir: initialDir }),
    });
  },
};
