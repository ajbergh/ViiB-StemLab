#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;
mod bootstrap;
use bootstrap::{Bootstrap, Installer};
use std::{path::PathBuf, sync::atomic::Ordering};

#[derive(Clone, Deserialize, Serialize)]
struct Connection {
    url: String,
    token: String,
}

#[derive(Default)]
struct Backend {
    child: Option<Child>,
    connection: Option<Connection>,
    error: Option<String>,
}

type SharedBackend = Arc<Mutex<Backend>>;

#[derive(Serialize)]
struct BackendStatus {
    connection: Option<Connection>,
    error: Option<String>,
}

#[tauri::command]
fn backend_connection(state: tauri::State<'_, SharedBackend>) -> BackendStatus {
    let mut backend = state.lock().unwrap();
    if let Some(child) = backend.child.as_mut() {
        if let Ok(Some(status)) = child.try_wait() {
            backend.connection = None;
            backend.error = Some(format!("Audio engine exited ({status}). Reopen StemLab; see backend-stderr.log in app data."));
        }
    }
    BackendStatus {
        connection: backend.connection.clone(),
        error: backend.error.clone(),
    }
}

fn start_backend(
    app: &tauri::AppHandle,
    state: SharedBackend,
    executable: Option<PathBuf>,
    setup: &Bootstrap,
) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = match std::env::var_os("VIIB_STEMLAB_HOME") {
        Some(path) => std::path::PathBuf::from(path),
        None => app.path().app_local_data_dir()?,
    };
    if !data_dir.is_absolute() {
        return Err("VIIB_STEMLAB_HOME must be an absolute path".into());
    }
    fs::create_dir_all(&data_dir)?;
    let stderr = OpenOptions::new()
        .create(true)
        .append(true)
        .open(data_dir.join("backend-stderr.log"))?;
    let mut command;
    if let Some(exe) = executable {
        command = Command::new(exe);
    } else if cfg!(debug_assertions) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let python = std::env::var_os("VIIB_STEMLAB_PYTHON")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| {
                root.join(if cfg!(windows) {
                    ".venv/Scripts/python.exe"
                } else {
                    ".venv/bin/python"
                })
            });
        command = Command::new(python);
        command
            .args(["-m", "viib_stemlab.desktop_backend"])
            .current_dir(root);
    } else {
        let exe = app
            .path()
            .resource_dir()?
            .join("runtime")
            .join(if cfg!(windows) {
                "stemlab-backend.exe"
            } else {
                "stemlab-backend"
            });
        command = Command::new(exe);
    }
    command
        .env("VIIB_STEMLAB_HOME", &data_dir)
        .env("TORCH_HOME", data_dir.join("torch"))
        .env_remove("VIIB_STEMLAB_CACHE_DIR")
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(stderr);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    // Serialize spawn with shutdown so closing during setup cannot orphan a backend.
    let mut backend = state.lock().unwrap();
    setup.check_cancelled()?;
    let mut child = command.spawn()?;
    let stdout = child
        .stdout
        .take()
        .ok_or("Backend did not provide stdout")?;
    backend.child = Some(child);
    drop(backend);
    thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(stdout)
            .read_line(&mut line)
            .map_err(|e| e.to_string())
            .and_then(|count| {
                if count == 0 {
                    return Err(
                        "Audio engine exited before startup. See backend-stderr.log in app data."
                            .into(),
                    );
                }
                serde_json::from_str::<Connection>(&line).map_err(|_| {
                    "Invalid audio engine startup response. See backend-stderr.log in app data."
                        .into()
                })
            });
        let mut backend = state.lock().unwrap();
        match result {
            Ok(connection) => backend.connection = Some(connection),
            Err(error) => backend.error = Some(error),
        }
    });
    Ok(())
}

#[tauri::command]
fn runtime_status(setup: tauri::State<'_, Arc<Bootstrap>>) -> bootstrap::Status {
    setup.status()
}

fn begin_setup(app: tauri::AppHandle, state: SharedBackend, setup: Arc<Bootstrap>, download: bool) {
    if setup.running.swap(true, Ordering::AcqRel) {
        return;
    }
    setup.cancelled.store(false, Ordering::Release);
    setup.update("checking", "Checking processing components…", None);
    thread::spawn(move || {
        let result = setup.prepare(download).and_then(|executable| {
            if executable.is_none() && setup.installer.flavor != "development" {
                return Ok(());
            }
            setup.check_cancelled()?;
            {
                let mut backend = state.lock().unwrap();
                backend.error = None;
            }
            setup.update("starting", "Starting your audio engine…", None);
            start_backend(&app, state.clone(), executable, &setup).map_err(|e| e.to_string())?;
            setup.update(
                "ready",
                "Processing components are ready for offline use.",
                Some(1.0),
            );
            Ok(())
        });
        if let Err(error) = result {
            let phase = if setup.cancelled.load(Ordering::Acquire) {
                "cancelled"
            } else {
                "failed"
            };
            setup.update(phase, &error, None);
        }
        setup.running.store(false, Ordering::Release);
    });
}

#[tauri::command]
fn runtime_install(
    app: tauri::AppHandle,
    state: tauri::State<'_, SharedBackend>,
    setup: tauri::State<'_, Arc<Bootstrap>>,
) {
    if state.lock().unwrap().child.is_some() {
        return;
    }
    begin_setup(app, state.inner().clone(), setup.inner().clone(), true);
}

#[tauri::command]
fn runtime_cancel(setup: tauri::State<'_, Arc<Bootstrap>>) {
    setup.cancelled.store(true, Ordering::Release);
}

fn stop_backend(state: &SharedBackend) {
    let child = state.lock().unwrap().child.take();
    if let Some(mut child) = child {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(b"shutdown\n");
        }
        let deadline = Instant::now() + Duration::from_secs(15);
        while Instant::now() < deadline {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn main() {
    let state: SharedBackend = Arc::new(Mutex::new(Backend::default()));
    let setup_state = state.clone();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .manage(state.clone())
        .invoke_handler(tauri::generate_handler![
            backend_connection,
            runtime_status,
            runtime_install,
            runtime_cancel
        ])
        .setup(move |app| {
            let data = std::env::var_os("VIIB_STEMLAB_HOME")
                .map(PathBuf::from)
                .unwrap_or(app.path().app_local_data_dir()?);
            let resources = app.path().resource_dir()?;
            let installer = if cfg!(debug_assertions)
                || !cfg!(any(
                    windows,
                    all(target_os = "macos", target_arch = "aarch64"),
                    all(target_os = "linux", target_arch = "x86_64")
                )) {
                Installer {
                    flavor: "development".into(),
                    manifest_url: None,
                }
            } else {
                serde_json::from_str::<Installer>(&fs::read_to_string(
                    resources.join("installer.json"),
                )?)?
            };
            let setup = Arc::new(Bootstrap::new(data, resources, installer));
            app.manage(setup.clone());
            begin_setup(app.handle().clone(), setup_state.clone(), setup, false);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running ViiB StemLab");
    app.run(move |app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            app.state::<Arc<Bootstrap>>()
                .cancelled
                .store(true, Ordering::Release);
            stop_backend(&state);
            // Let setup terminate its probe and remove staging files before exit.
            let deadline = Instant::now() + Duration::from_secs(6);
            while app
                .state::<Arc<Bootstrap>>()
                .running
                .load(Ordering::Acquire)
                && Instant::now() < deadline
            {
                thread::sleep(Duration::from_millis(50));
            }
        }
    });
}
