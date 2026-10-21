import { invoke, isTauri } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { getCurrentWebview } from '@tauri-apps/api/webview';

export interface Connection { url: string; token: string }
export const nativeDesktop = () => isTauri();

export async function desktopConnection(): Promise<Connection> {
  if (!nativeDesktop()) return { url: '', token: '' };
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    const state = await invoke<{ connection?: Connection; error?: string }>('backend_connection');
    if (state.error) throw new Error(state.error);
    if (state.connection) return state.connection;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('The audio engine did not start within 60 seconds. Close and reopen StemLab.');
}

export async function pickAudio(folder = false): Promise<string[]> {
  const selected = await open(folder
    ? { directory: true, multiple: false }
    : { multiple: true, filters: [{ name: 'Audio', extensions: ['wav', 'flac', 'mp3', 'ogg'] }] });
  return selected ? (Array.isArray(selected) ? selected : [selected]) : [];
}

export async function listenForFiles(onDrop: (paths: string[]) => void): Promise<() => void> {
  return getCurrentWebview().onDragDropEvent(event => {
    if (event.payload.type === 'drop') onDrop(event.payload.paths);
  });
}
