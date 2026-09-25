import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from './api';
import { QueueResponse, DoctorReport, LibraryResponse } from './types';

describe('ViiB-StemLab Frontend API Client', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('getQueue fetches queue jobs and summary counts', async () => {
    const mockData: QueueResponse = {
      jobs: [
        {
          id: 'job-123',
          source_path: '/music/track.wav',
          output_library: '/music/stems',
          model: 'htdemucs_6s',
          device: 'cuda',
          actual_device: 'cuda',
          fallback_to_cpu: true,
          overwrite: false,
          status: 'queued',
          progress: 0,
          created_at: '2026-09-25T12:00:00Z',
        },
      ],
      counts: {
        total: 1,
        queued: 1,
        active: 0,
        complete: 0,
        failed: 0,
        cancelled: 0,
      },
      is_running: false,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as any);

    const result = await api.getQueue();
    expect(result.counts.total).toBe(1);
    expect(result.jobs[0].id).toBe('job-123');
    expect(result.jobs[0].status).toBe('queued');
  });

  it('addPaths posts audio paths and options', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        added: [
          {
            id: 'job-abc',
            source_path: '/music/song.flac',
            output_library: '/library',
            model: 'htdemucs_6s',
            device: 'auto',
            fallback_to_cpu: true,
            overwrite: false,
            status: 'queued',
            progress: 0,
            created_at: '2026-09-25T12:00:00Z',
          },
        ],
        added_count: 1,
        skipped_duplicate_queue: [],
        skipped_existing_package: [],
        invalid_files: [],
      }),
    } as any);

    const result = await api.addPaths(['/music/song.flac'], {
      output_library: '/library',
      model: 'htdemucs_6s',
      device: 'auto',
    });

    expect(result.added_count).toBe(1);
    expect(result.added[0].id).toBe('job-abc');
  });

  it('getDoctor fetches system capabilities', async () => {
    const mockDoc: DoctorReport = {
      stemLabVersion: '0.1.0',
      python: '3.13.7',
      platform: 'Windows-10',
      machine: 'AMD64',
      torch: {
        available: true,
        version: '2.6.0',
        cudaAvailable: true,
        mpsAvailable: false,
      },
      demucs: {
        available: true,
        version: '4.0.1',
        devices: ['cpu', 'cuda'],
        autoDevice: 'cuda',
      },
      input: {
        extensions: ['.wav', '.flac', '.mp3', '.ogg'],
        ffmpegAvailable: true,
        ffprobeAvailable: true,
      },
      modelCache: {
        directory: '/checkpoints',
        models: [],
      },
      disk: {
        target: 'C:\\',
        totalBytes: 1000000,
        freeBytes: 500000,
        freeGb: 500.0,
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDoc,
    } as any);

    const doc = await api.getDoctor();
    expect(doc.stemLabVersion).toBe('0.1.0');
    expect(doc.torch.cudaAvailable).toBe(true);
    expect(doc.demucs.autoDevice).toBe('cuda');
  });

  it('getLibrary fetches packages from output library', async () => {
    const mockLib: LibraryResponse = {
      library_path: '/stems',
      packages: [
        {
          path: '/stems/Track1.viibstems',
          folder_name: 'Track1.viibstems',
          package_id: 'pkg-123',
          stems: ['vocals', 'drums', 'bass', 'other', 'guitar', 'piano'],
          size_bytes: 45000000,
        },
      ],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockLib,
    } as any);

    const lib = await api.getLibrary('/stems');
    expect(lib.packages.length).toBe(1);
    expect(lib.packages[0].stems.length).toBe(6);
  });

  it('pickFolder posts to /api/dialog/folder', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ path: '/music/dj_folder', cancelled: false }),
    } as any);

    const res = await api.pickFolder('Select Audio Folder');
    expect(res.path).toBe('/music/dj_folder');
    expect(res.cancelled).toBe(false);
  });

  it('pickFiles posts to /api/dialog/files', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ paths: ['/music/song1.wav', '/music/song2.mp3'], cancelled: false }),
    } as any);

    const res = await api.pickFiles('Select Audio Files');
    expect(res.paths.length).toBe(2);
    expect(res.paths[0]).toBe('/music/song1.wav');
  });
});
