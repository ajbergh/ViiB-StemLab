//! Native setup works before Python or the processing engine exists.
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    thread,
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, String>;
fn err(error: impl std::fmt::Display) -> String {
    error.to_string()
}
const MAX_UNPACKED: u64 = 4 * 1024 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Installer {
    pub flavor: String,
    pub manifest_url: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    pub phase: String,
    pub message: String,
    pub progress: Option<f64>,
    pub flavor: String,
    pub download_bytes: Option<u64>,
    pub required_bytes: Option<u64>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct Release {
    protocol: u32,
    app_version: String,
    version: String,
    platform: String,
    url: String,
    size: u64,
    sha256: String,
    unpacked_size: u64,
}

#[derive(Clone, Deserialize, Serialize)]
struct Entry {
    size: u64,
    sha256: String,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct Payload {
    protocol: u32,
    app_version: String,
    version: String,
    platform: String,
    executable: String,
    model: String,
    files: BTreeMap<String, Entry>,
}

pub struct Bootstrap {
    pub data: PathBuf,
    pub resources: PathBuf,
    pub installer: Installer,
    pub running: AtomicBool,
    pub cancelled: AtomicBool,
    status: Mutex<Status>,
}

pub fn safe_path(name: &str) -> Result<PathBuf> {
    let mut path = PathBuf::new();
    if name.is_empty() || name.contains('\\') || name.starts_with('/') {
        return Err("Unsafe component path".into());
    }
    for part in name.trim_end_matches('/').split('/') {
        let base = part.split('.').next().unwrap_or("").to_ascii_uppercase();
        if part.is_empty()
            || part == "."
            || part == ".."
            || part.contains(':')
            || part.ends_with(['.', ' '])
            || part.chars().any(|c| c.is_control())
            || ["CON", "PRN", "AUX", "NUL"].contains(&base.as_str())
            || (base.len() == 4
                && (base.starts_with("COM") || base.starts_with("LPT"))
                && base.as_bytes()[3].is_ascii_digit())
        {
            return Err("Unsafe component path".into());
        }
        path.push(part);
    }
    Ok(path)
}

fn owned(root: &Path, path: &Path) -> Result<()> {
    if !path.starts_with(root) {
        return Err("Component path escapes app data".into());
    }
    for component in path.ancestors() {
        if let Ok(metadata) = fs::symlink_metadata(component) {
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if metadata.file_attributes() & 0x400 != 0 {
                    return Err("Component paths cannot be links or junctions".into());
                }
            }
            if metadata.file_type().is_symlink() {
                return Err("Component paths cannot be links".into());
            }
        }
        if component == root {
            break;
        }
    }
    Ok(())
}

fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn valid_version(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 100
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        && value.as_bytes()[0].is_ascii_alphanumeric()
}
fn compatible(protocol: u32, app: &str, platform: &str, version: &str) -> Result<()> {
    if protocol != 1
        || app != env!("CARGO_PKG_VERSION")
        || platform != "windows-x64"
        || !valid_version(version)
    {
        return Err("Processing components do not match this application version".into());
    }
    Ok(())
}

impl Bootstrap {
    pub fn new(data: PathBuf, resources: PathBuf, installer: Installer) -> Self {
        Self {
            data,
            resources,
            status: Mutex::new(Status {
                phase: "checking".into(),
                message: "Checking processing components…".into(),
                progress: None,
                flavor: installer.flavor.clone(),
                download_bytes: None,
                required_bytes: None,
            }),
            installer,
            running: AtomicBool::new(false),
            cancelled: AtomicBool::new(false),
        }
    }
    pub fn status(&self) -> Status {
        self.status.lock().unwrap().clone()
    }
    pub fn update(&self, phase: &str, message: &str, progress: Option<f64>) {
        let mut state = self.status.lock().unwrap();
        state.phase = phase.into();
        state.message = message.into();
        state.progress = progress;
    }
    pub fn check_cancelled(&self) -> Result<()> {
        if self.cancelled.load(Ordering::Acquire) {
            Err("Setup cancelled. Retry when you are ready.".into())
        } else {
            Ok(())
        }
    }
    fn hash(&self, path: &Path) -> Result<String> {
        let mut input = File::open(path).map_err(err)?;
        let mut hash = Sha256::new();
        let mut buffer = vec![0; 1024 * 1024];
        loop {
            self.check_cancelled()?;
            let count = input.read(&mut buffer).map_err(err)?;
            if count == 0 {
                break;
            }
            hash.update(&buffer[..count]);
        }
        Ok(format!("{:x}", hash.finalize()))
    }
    fn payload(&self, root: &Path) -> Result<Payload> {
        owned(root, &root.join("payload.json"))?;
        let file = File::open(root.join("payload.json")).map_err(err)?;
        let mut data = String::new();
        file.take(8 * 1024 * 1024 + 1)
            .read_to_string(&mut data)
            .map_err(err)?;
        if data.len() > 8 * 1024 * 1024 {
            return Err("Component inventory is too large".into());
        }
        let payload: Payload = serde_json::from_str(&data).map_err(err)?;
        compatible(
            payload.protocol,
            &payload.app_version,
            &payload.platform,
            &payload.version,
        )?;
        if payload.executable != "stemlab-backend.exe"
            || payload.model != "models/5c90dfd2-34c22ccb.th"
            || !payload.files.contains_key(&payload.executable)
            || !payload.files.contains_key(&payload.model)
            || !payload
                .files
                .contains_key("_internal/audio-tools/ffmpeg.exe")
            || !payload
                .files
                .contains_key("_internal/audio-tools/ffprobe.exe")
            || payload.files.len() > 100000
        {
            return Err("Invalid processing component inventory".into());
        }
        let mut names = HashSet::new();
        let mut actual = HashSet::new();
        let mut directories = vec![root.to_path_buf()];
        while let Some(directory) = directories.pop() {
            for entry in fs::read_dir(&directory).map_err(err)? {
                self.check_cancelled()?;
                let path = entry.map_err(err)?.path();
                owned(root, &path)?;
                if path.is_dir() {
                    directories.push(path);
                } else {
                    let name = path
                        .strip_prefix(root)
                        .map_err(err)?
                        .to_string_lossy()
                        .replace('\\', "/");
                    if name != "payload.json" {
                        actual.insert(name);
                    }
                }
                if actual.len() + directories.len() > 100000 {
                    return Err("Component inventory is too large".into());
                }
            }
        }
        if actual != payload.files.keys().cloned().collect() {
            return Err("Unexpected or missing processing component files".into());
        }
        let mut total = 0_u64;
        for (name, entry) in &payload.files {
            let path = root.join(safe_path(name)?);
            owned(root, &path)?;
            total = total
                .checked_add(entry.size)
                .ok_or("Component inventory overflow")?;
            if !names.insert(name.to_lowercase())
                || !valid_hash(&entry.sha256)
                || total > MAX_UNPACKED
            {
                return Err("Invalid component inventory entry".into());
            }
            if fs::metadata(&path).map_err(err)?.len() != entry.size
                || self.hash(&path)? != entry.sha256
            {
                return Err(format!("Processing component verification failed: {name}"));
            }
        }
        // Model identity is pinned independently of a remotely supplied inventory.
        let model = &payload.files[&payload.model];
        if model.size != 54996327
            || model.sha256 != "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd"
        {
            return Err("Unexpected six-stem model".into());
        }
        Ok(payload)
    }
    fn seed_model(&self, root: &Path, payload: &Payload) -> Result<()> {
        self.update("verifying", "Preparing your offline audio model…", None);
        let cache = self.data.join("torch/hub/checkpoints");
        owned(&self.data, &cache)?;
        fs::create_dir_all(&cache).map_err(err)?;
        let target = cache.join("5c90dfd2-34c22ccb.th");
        owned(&self.data, &target)?;
        let entry = &payload.files[&payload.model];
        if target.is_file() && self.hash(&target)? == entry.sha256 {
            return Ok(());
        }
        let mut temporary = tempfile::NamedTempFile::new_in(&cache).map_err(err)?;
        let mut input = File::open(root.join(&payload.model)).map_err(err)?;
        let mut buffer = vec![0; 1024 * 1024];
        loop {
            self.check_cancelled()?;
            let count = input.read(&mut buffer).map_err(err)?;
            if count == 0 {
                break;
            }
            temporary.write_all(&buffer[..count]).map_err(err)?;
        }
        temporary.as_file().sync_all().map_err(err)?;
        self.check_cancelled()?;
        temporary.persist(target).map_err(err)?;
        Ok(())
    }
    fn probe(&self, executable: &Path) -> Result<()> {
        self.update(
            "verifying",
            "Checking that your audio engine can run…",
            None,
        );
        self.check_cancelled()?;
        let errors = OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.data.join("setup-probe.log"))
            .map_err(err)?;
        let mut command = Command::new(executable);
        command
            .arg("--runtime-probe")
            .env("PYINSTALLER_RESET_ENVIRONMENT", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(errors);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|error| format!("Could not start the audio engine check: {error}"))?;
        let deadline = Instant::now() + Duration::from_secs(90);
        loop {
            if self.check_cancelled().is_err() || Instant::now() > deadline {
                let _ = child.kill();
                let _ = child.wait();
                self.check_cancelled()?;
                return Err(
                    "Audio engine check timed out. See setup-probe.log in app data.".into(),
                );
            }
            match child.try_wait() {
                Ok(Some(status)) if status.success() => return Ok(()),
                Ok(Some(_)) => return Err(
                    "Audio engine check failed. See setup-probe.log in app data, then retry setup."
                        .into(),
                ),
                Err(error) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(err(error));
                }
                Ok(None) => thread::sleep(Duration::from_millis(100)),
            }
        }
    }
    fn promote_directory(&self, source: &Path, destination: &Path) -> Result<()> {
        owned(&self.data, source)?;
        owned(&self.data, destination)?;
        for attempt in 0..=15 {
            self.check_cancelled()?;
            match fs::rename(source, destination) {
                Ok(()) => return Ok(()),
                Err(error) if attempt < 15 && matches!(error.raw_os_error(), Some(5 | 32 | 33)) => {
                    self.update(
                        "verifying",
                        "Waiting for Windows to release downloaded files…",
                        None,
                    );
                    for _ in 0..20 {
                        self.check_cancelled()?;
                        thread::sleep(Duration::from_millis(100));
                    }
                }
                Err(error) => {
                    return Err(format!(
                    "Could not activate downloaded components. Retry setup in a moment: {error}"
                ))
                }
            }
        }
        unreachable!()
    }
    fn client(&self) -> Result<reqwest::Client> {
        let mut builder = reqwest::Client::builder()
            .https_only(true)
            .connect_timeout(Duration::from_secs(15))
            .read_timeout(Duration::from_secs(5))
            .user_agent("ViiB-StemLab-Setup/0.1");
        // Operator override for private HTTPS hosting/testing; validation is never disabled.
        if let Some(path) = std::env::var_os("VIIB_STEMLAB_SETUP_CA_CERT") {
            let cert =
                reqwest::Certificate::from_pem(&fs::read(path).map_err(err)?).map_err(err)?;
            builder = builder.add_root_certificate(cert);
        }
        builder.build().map_err(err)
    }
    async fn await_http<F, T>(&self, future: F) -> Result<T>
    where
        F: std::future::Future<Output = std::result::Result<T, reqwest::Error>>,
    {
        let mut pending = Box::pin(future);
        loop {
            self.check_cancelled()?;
            match tokio::time::timeout(Duration::from_millis(100), &mut pending).await {
                Ok(result) => return result.map_err(err),
                Err(_) => continue,
            }
        }
    }
    async fn release(&self, client: &reqwest::Client) -> Result<Release> {
        let url = std::env::var("VIIB_STEMLAB_CPU_MANIFEST_URL")
            .ok()
            .or_else(|| self.installer.manifest_url.clone())
            .ok_or("No processing download release is configured")?;
        if !url.starts_with("https://") {
            return Err("Processing downloads require HTTPS".into());
        }
        let response = self
            .await_http(client.get(&url).timeout(Duration::from_secs(30)).send())
            .await?;
        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Err("The processing download release has not been published yet. Use the Full installer or retry after it is available.".into());
        }
        let mut response = response.error_for_status().map_err(err)?;
        let mut text = Vec::new();
        while let Some(chunk) = self.await_http(response.chunk()).await? {
            self.check_cancelled()?;
            if text.len() + chunk.len() > 65536 {
                return Err("Download manifest is too large".into());
            }
            text.extend_from_slice(&chunk);
        }
        let release: Release = serde_json::from_slice(&text).map_err(err)?;
        compatible(
            release.protocol,
            &release.app_version,
            &release.platform,
            &release.version,
        )?;
        if !release.url.starts_with("https://")
            || !valid_hash(&release.sha256)
            || release.size == 0
            || release.size > MAX_UNPACKED
            || release.unpacked_size == 0
            || release.unpacked_size > MAX_UNPACKED
        {
            return Err("Invalid processing download manifest".into());
        }
        Ok(release)
    }
    fn extract(&self, archive: &Path, destination: &Path, release: &Release) -> Result<()> {
        let mut zip = zip::ZipArchive::new(File::open(archive).map_err(err)?).map_err(err)?;
        if zip.len() > 100000 {
            return Err("Too many component archive entries".into());
        }
        let mut names = HashSet::new();
        let mut expanded = 0_u64;
        for index in 0..zip.len() {
            self.check_cancelled()?;
            let mut entry = zip.by_index(index).map_err(err)?;
            let name = entry.name().to_string();
            let path = destination.join(safe_path(&name)?);
            if !names.insert(name.trim_end_matches('/').to_lowercase())
                || entry
                    .unix_mode()
                    .is_some_and(|mode| mode & 0o170000 == 0o120000)
            {
                return Err("Duplicate or linked component archive entry".into());
            }
            expanded = expanded
                .checked_add(entry.size())
                .ok_or("Archive size overflow")?;
            if expanded > release.unpacked_size {
                return Err("Component archive exceeds declared size".into());
            }
            if entry.is_dir() {
                fs::create_dir_all(&path).map_err(err)?;
                continue;
            }
            fs::create_dir_all(path.parent().ok_or("Invalid archive path")?).map_err(err)?;
            let mut output = File::create(&path).map_err(err)?;
            let mut buffer = vec![0; 1024 * 1024];
            let mut written = 0_u64;
            loop {
                self.check_cancelled()?;
                let count = entry.read(&mut buffer).map_err(err)?;
                if count == 0 {
                    break;
                }
                written += count as u64;
                if written > entry.size() {
                    return Err("Archive entry exceeds declared size".into());
                }
                output.write_all(&buffer[..count]).map_err(err)?;
            }
            if written != entry.size() {
                return Err("Archive entry size mismatch".into());
            }
        }
        if expanded != release.unpacked_size {
            return Err("Component archive size mismatch".into());
        }
        Ok(())
    }
    async fn download(&self, root: &Path) -> Result<PathBuf> {
        self.update(
            "checking",
            "Checking processing download and disk requirements…",
            None,
        );
        self.check_cancelled()?;
        let client = self.client()?;
        let release = self.release(&client).await?;
        let required = release.size + release.unpacked_size + 128 * 1024 * 1024;
        {
            let mut state = self.status.lock().unwrap();
            state.download_bytes = Some(release.size);
            state.required_bytes = Some(required);
        }
        if fs2::available_space(root).map_err(err)? < required {
            return Err("Not enough free disk space to set up processing components".into());
        }
        let stage = tempfile::Builder::new()
            .prefix("setup-")
            .tempdir_in(root)
            .map_err(err)?;
        let archive = stage.path().join("payload.zip");
        self.update(
            "downloading",
            "Downloading the audio engine, decoder tools and six-stem model…",
            Some(0.0),
        );
        let mut response = self
            .await_http(client.get(&release.url).send())
            .await?
            .error_for_status()
            .map_err(err)?;
        let mut output = File::create(&archive).map_err(err)?;
        let mut hash = Sha256::new();
        let mut downloaded = 0_u64;
        loop {
            self.check_cancelled()?;
            let Some(chunk) = self.await_http(response.chunk()).await? else {
                break;
            };
            downloaded += chunk.len() as u64;
            if downloaded > release.size {
                return Err("Download exceeds declared size".into());
            }
            output.write_all(&chunk).map_err(err)?;
            hash.update(&chunk);
            self.update(
                "downloading",
                "Downloading the audio engine, decoder tools and six-stem model…",
                Some(downloaded as f64 / release.size as f64),
            );
        }
        drop(output);
        if downloaded != release.size || format!("{:x}", hash.finalize()) != release.sha256 {
            return Err("Processing download size/checksum mismatch. Retry setup.".into());
        }
        self.update(
            "verifying",
            "Verifying and extracting processing components…",
            None,
        );
        let extracted = stage.path().join("runtime");
        fs::create_dir(&extracted).map_err(err)?;
        self.extract(&archive, &extracted, &release)?;
        let payload = self.payload(&extracted)?;
        if payload.version != release.version {
            return Err("Downloaded payload version mismatch".into());
        }
        self.seed_model(&extracted, &payload)?;
        self.check_cancelled()?;
        let generation = tempfile::Builder::new()
            .prefix("runtime-")
            .tempdir_in(root)
            .map_err(err)?;
        let destination = generation.path().join("payload");
        self.promote_directory(&extracted, &destination)?;
        // Probe at the final generation path. Windows can retain image/DLL locks
        // briefly after exit, so do not rename a directory that just ran code.
        self.probe(&destination.join(&payload.executable))?;
        self.check_cancelled()?;
        let name = generation
            .path()
            .file_name()
            .ok_or("Missing generation name")?
            .to_string_lossy()
            .to_string();
        let mut receipt = tempfile::NamedTempFile::new_in(root).map_err(err)?;
        receipt
            .write_all(serde_json::to_string(&name).map_err(err)?.as_bytes())
            .map_err(err)?;
        receipt.as_file().sync_all().map_err(err)?;
        self.check_cancelled()?;
        let kept = generation.keep();
        if let Err(error) = receipt.persist(root.join("current.json")) {
            // The old receipt and generation remain valid if promotion fails.
            return Err(format!(
                "Could not activate components at {}: {error}",
                kept.display()
            ));
        }
        Ok(destination.join(payload.executable))
    }
    pub fn prepare(&self, download: bool) -> Result<Option<PathBuf>> {
        self.update("checking", "Verifying processing components…", None);
        if self.installer.flavor == "development" {
            return Ok(None);
        }
        if !self.data.is_absolute() {
            return Err("Application data must use an absolute path".into());
        }
        owned(&self.data, &self.data)?;
        fs::create_dir_all(&self.data).map_err(err)?;
        if self.installer.flavor == "full" {
            let runtime = self.resources.join("runtime");
            let payload = self.payload(&runtime)?;
            self.seed_model(&runtime, &payload)?;
            self.probe(&runtime.join(&payload.executable))?;
            return Ok(Some(runtime.join(payload.executable)));
        }
        if self.installer.flavor != "ondemand" {
            return Err("Unknown installer flavor".into());
        }
        let root = self.data.join("cpu-runtimes");
        owned(&self.data, &root)?;
        fs::create_dir_all(&root).map_err(err)?;
        let lock_path = root.join("setup.lock");
        owned(&root, &lock_path)?;
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(lock_path)
            .map_err(err)?;
        lock.try_lock_exclusive().map_err(|_| {
            "Another StemLab process is preparing processing components".to_string()
        })?;
        let receipt = root.join("current.json");
        owned(&root, &receipt)?;
        if let Ok(text) = fs::read_to_string(&receipt) {
            if let Ok(name) = serde_json::from_str::<String>(&text) {
                if valid_version(&name) {
                    let runtime = root.join(name).join("payload");
                    owned(&root, &runtime)?;
                    if let Ok(payload) = self.payload(&runtime) {
                        self.seed_model(&runtime, &payload)?;
                        self.probe(&runtime.join(&payload.executable))?;
                        return Ok(Some(runtime.join(payload.executable)));
                    }
                }
            }
        }
        self.check_cancelled()?;
        if download {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .map_err(err)?
                .block_on(self.download(&root))
                .map(Some)
        } else {
            self.update("needed", "Download the audio engine, decoder tools and six-stem model once. Processing then works offline.", None);
            Ok(None)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cancels_a_stalled_network_operation() {
        let temp = tempfile::tempdir().unwrap();
        let setup = std::sync::Arc::new(Bootstrap::new(
            temp.path().into(),
            temp.path().into(),
            Installer {
                flavor: "ondemand".into(),
                manifest_url: None,
            },
        ));
        let cancellation = setup.clone();
        let worker = thread::spawn(move || {
            thread::sleep(Duration::from_millis(50));
            cancellation.cancelled.store(true, Ordering::Release);
        });
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let result = runtime.block_on(setup.await_http(std::future::pending::<
            std::result::Result<(), reqwest::Error>,
        >()));
        assert!(result.unwrap_err().contains("cancelled"));
        worker.join().unwrap();
    }
    #[test]
    #[ignore = "requires a built CPU payload and a locally trusted HTTPS fixture"]
    fn real_full_and_ondemand_payloads() {
        let resources = PathBuf::from(
            std::env::var("VIIB_TEST_FULL_RESOURCES").expect("Full resources directory"),
        );
        let url = std::env::var("VIIB_TEST_CPU_MANIFEST").expect("HTTPS fixture manifest");
        let data = tempfile::tempdir().unwrap();
        let full = Bootstrap::new(
            data.path().join("full"),
            resources.clone(),
            Installer {
                flavor: "full".into(),
                manifest_url: None,
            },
        );
        let exe = full.prepare(false).unwrap().unwrap();
        assert!(exe.is_file());
        assert_eq!(
            fs::metadata(
                data.path()
                    .join("full/torch/hub/checkpoints/5c90dfd2-34c22ccb.th")
            )
            .unwrap()
            .len(),
            54996327
        );
        let online = Bootstrap::new(
            data.path().join("online"),
            resources.clone(),
            Installer {
                flavor: "ondemand".into(),
                manifest_url: Some(url.clone()),
            },
        );
        let downloaded = online.prepare(true).unwrap().unwrap();
        assert!(downloaded.is_file());
        let offline = Bootstrap::new(
            data.path().join("online"),
            resources.clone(),
            Installer {
                flavor: "ondemand".into(),
                manifest_url: Some("https://127.0.0.1:1/unreachable".into()),
            },
        );
        assert_eq!(offline.prepare(false).unwrap().unwrap(), downloaded);
        fs::remove_file(&downloaded).unwrap();
        assert!(offline.prepare(false).unwrap().is_none());
        let repaired = online.prepare(true).unwrap().unwrap();
        assert!(repaired.is_file());
        assert_ne!(repaired, downloaded);
        let bad = Bootstrap::new(
            data.path().join("bad"),
            resources,
            Installer {
                flavor: "ondemand".into(),
                manifest_url: Some(url.replace("windows-cpu.json", "bad-sha.json")),
            },
        );
        assert!(bad.prepare(true).unwrap_err().contains("checksum mismatch"));
        assert!(!data.path().join("bad/cpu-runtimes/current.json").exists());
        println!("Full offline, HTTPS download/probe, offline reuse, repair, and checksum rejection passed.");
    }
    #[test]
    fn rejects_unsafe_paths() {
        for name in [
            "../x", "/x", "C:/x", "a\\x", "a/../x", "a/./x", "CON.txt", "a/file.", "LPT1", "a//x",
        ] {
            assert!(safe_path(name).is_err(), "{name}");
        }
        assert_eq!(
            safe_path("_internal/torch/lib/a.dll").unwrap(),
            PathBuf::from("_internal/torch/lib/a.dll")
        );
    }
    #[test]
    fn offline_first_launch_needs_setup_without_network() {
        let temp = tempfile::tempdir().unwrap();
        let bootstrap = Bootstrap::new(
            temp.path().to_path_buf(),
            temp.path().join("resources"),
            Installer {
                flavor: "ondemand".into(),
                manifest_url: Some("https://invalid.example/manifest.json".into()),
            },
        );
        assert!(bootstrap.prepare(false).unwrap().is_none());
        assert_eq!(bootstrap.status().phase, "needed");
        bootstrap.cancelled.store(true, Ordering::Release);
        assert!(bootstrap.prepare(true).unwrap_err().contains("cancelled"));
    }
    #[test]
    fn rejects_wrong_release_protocol_and_version() {
        assert!(compatible(2, env!("CARGO_PKG_VERSION"), "windows-x64", "v1").is_err());
        assert!(compatible(1, "99.0.0", "windows-x64", "v1").is_err());
        assert!(compatible(1, env!("CARGO_PKG_VERSION"), "windows-x64", "../v1").is_err());
    }
    #[test]
    fn refuses_archive_traversal_and_size_mismatch() {
        let temp = tempfile::tempdir().unwrap();
        let bootstrap = Bootstrap::new(
            temp.path().to_path_buf(),
            temp.path().into(),
            Installer {
                flavor: "ondemand".into(),
                manifest_url: None,
            },
        );
        let archive = temp.path().join("test.zip");
        let mut writer = zip::ZipWriter::new(File::create(&archive).unwrap());
        writer
            .start_file("../outside", zip::write::SimpleFileOptions::default())
            .unwrap();
        writer.write_all(b"test").unwrap();
        writer.finish().unwrap();
        let release = Release {
            protocol: 1,
            app_version: env!("CARGO_PKG_VERSION").into(),
            version: "v1".into(),
            platform: "windows-x64".into(),
            url: "https://example.test/a.zip".into(),
            size: 1,
            sha256: "0".repeat(64),
            unpacked_size: 4,
        };
        assert!(bootstrap
            .extract(&archive, &temp.path().join("extract"), &release)
            .is_err());
        assert!(!temp.path().join("outside").exists());
    }
}
