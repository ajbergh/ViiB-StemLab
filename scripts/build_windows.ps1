[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$CudaWorker,
    [ValidateSet('Full', 'OnDemand', 'Both')]
    [string]$Installer = 'Both',
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
if ($Help) {
    Write-Host @'
Usage: scripts\build_windows.bat [-Installer Full|OnDemand|Both] [-CheckOnly] [-CudaWorker]

Builds both unsigned Windows x64 installer variants by default.
Full includes Python, Demucs, FFmpeg/FFprobe, model weights and offline WebView2.
OnDemand includes the UI and downloads verified processing components on first use.

Prerequisites: x64 Python 3.12/3.13 (or an existing packaging environment),
Node.js 22+, Rust/Cargo, and Visual Studio C++ build tools with a Windows SDK.
Internet access is required for dependencies on the first build.

-CheckOnly checks prerequisites without installing dependencies or building.
-CudaWorker builds a separate downloadable CUDA archive and release manifest.
CUDA worker mode only requires Python; it does not require Node or Rust.
Close running StemLab development/release windows before a full build.
Output: dist\windows\ViiB StemLab_<version>_x64-full-setup.exe / ...-ondemand-setup.exe
On-demand release payload: dist\components\windows-cpu.json and CPU archive.
'@
    exit 0
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = Join-Path $repoRoot 'build'
$python = Join-Path $buildRoot 'packaging-venv\Scripts\python.exe'
$runtime = Join-Path $repoRoot 'desktop\src-tauri\runtime'
$staging = Join-Path $buildRoot 'windows-runtime-next'
if ($CudaWorker) {
    $python = Join-Path $buildRoot 'cuda-packaging-venv\Scripts\python.exe'
    $staging = Join-Path $buildRoot 'windows-cuda-next'
}
$previous = Join-Path $buildRoot 'windows-runtime-previous'
$releaseRuntime = Join-Path $repoRoot 'desktop\src-tauri\target\release\runtime'
$managedDirectories = @($runtime, $staging, $previous, $releaseRuntime)

function Invoke-Native {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE."
    }
}

function Get-FileSha256 {
    param([string]$LiteralPath)
    # Use .NET directly: Get-FileHash may be unavailable in the build shell.
    $stream = $null
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($LiteralPath)
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        if ($stream) { $stream.Dispose() }
        $algorithm.Dispose()
    }
}

function Assert-ManagedDirectory {
    param([string]$Path)
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute -notin $managedDirectories -or
        -not $absolute.StartsWith($repoRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify an unexpected generated directory: $absolute"
    }
    if ((Test-Path -LiteralPath $absolute) -and
        ((Get-Item -LiteralPath $absolute).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing to modify a linked generated directory: $absolute"
    }
}

function Remove-GeneratedDirectory {
    param([string]$Path)
    Assert-ManagedDirectory $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Move-GeneratedDirectory {
    param([string]$Source, [string]$Destination)
    Assert-ManagedDirectory $Source
    Assert-ManagedDirectory $Destination
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        if (Test-Path -LiteralPath $Destination) { throw "Runtime destination already exists: $Destination" }
        try {
            Move-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq 6) { throw }
            Write-Host "Waiting for Windows to release generated runtime files (attempt $attempt)..."
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}

Push-Location $repoRoot
try {
    if (-not $CudaWorker) {
        $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
        $node = (Get-Command node.exe -ErrorAction Stop).Source
        $cargo = (Get-Command cargo.exe -ErrorAction Stop).Source
    }
    $uv = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ((Test-Path -LiteralPath $buildRoot) -and
        ((Get-Item -LiteralPath $buildRoot).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The build directory must not be a symbolic link or junction.'
    }

    $bootstrap = $null
    $bootstrapArguments = @()
    if (-not (Test-Path -LiteralPath $python)) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($version in @('-3.12', '-3.13')) {
                $probePreference = $ErrorActionPreference
                $ErrorActionPreference = 'Continue'
                try {
                    & $launcher.Source $version -c 'import sys' 2>$null
                    $foundPython = $LASTEXITCODE -eq 0
                } finally {
                    $ErrorActionPreference = $probePreference
                }
                if ($foundPython) {
                    $bootstrap = $launcher.Source
                    $bootstrapArguments = @($version)
                    break
                }
            }
        }
        if (-not $bootstrap) {
            $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
            if (-not $candidate) { throw 'Install x64 Python 3.12 or 3.13 first.' }
            $bootstrap = $candidate.Source
        }
    }
    $versionCheck = 'import sys,struct,platform; assert (3,12) <= sys.version_info[:2] < (3,14) and struct.calcsize("P")==8 and platform.machine().lower() in ("amd64","x86_64"), "Use x64 Python 3.12 or 3.13"'
    # Use single quotes within Python code for Windows PowerShell 5.1 argument passing.
    $versionCheck = $versionCheck.Replace('"', "'")
    if (Test-Path -LiteralPath $python) {
        Invoke-Native -Executable $python -Arguments @('-c', $versionCheck)
    } else {
        Invoke-Native -Executable $bootstrap -Arguments ($bootstrapArguments + @('-c', $versionCheck))
    }
    if (-not $CudaWorker) {
        Invoke-Native -Executable $npm -Arguments @('--version')
        Invoke-Native -Executable $node -Arguments @('-e', 'if (parseInt(process.versions.node, 10) < 22) process.exit(1)')
        Invoke-Native -Executable $cargo -Arguments @('--version')
    }
    if ($CheckOnly) {
        $null = Get-FileSha256 -LiteralPath $PSCommandPath
        if ($CudaWorker) {
            Write-Host 'CUDA worker prerequisites found. GPU execution is verified when the worker is installed by the app.'
        } else {
            Write-Host 'Prerequisites found. Visual Studio C++/SDK availability is checked by Cargo during a full build.'
        }
        exit 0
    }
    if (Get-Process -Name 'viib-stemlab-desktop' -ErrorAction SilentlyContinue) {
        throw 'Close StemLab windows before building so the release executable is not locked.'
    }

    $flavor = if ($CudaWorker) { 'cu124' } else { 'cpu' }
    $environment = Split-Path (Split-Path $python -Parent) -Parent
    Write-Host "[1/6] Preparing isolated $flavor packaging environment..."
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    $buildLock = [IO.File]::Open((Join-Path $buildRoot 'windows-build.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if (-not (Test-Path -LiteralPath $python)) {
        Invoke-Native -Executable $bootstrap -Arguments ($bootstrapArguments + @('-m', 'venv', $environment))
    }
    if ($uv) {
        Invoke-Native -Executable $uv.Source -Arguments @('pip', 'install', '--python', $python, "torch==2.6.0+$flavor", "torchaudio==2.6.0+$flavor", '--index-url', "https://download.pytorch.org/whl/$flavor")
        Invoke-Native -Executable $uv.Source -Arguments @('pip', 'install', '--python', $python, '-e', '.[demucs,packaging]')
    } else {
        Invoke-Native -Executable $python -Arguments @('-m', 'ensurepip', '--upgrade')
        Invoke-Native -Executable $python -Arguments @('-m', 'pip', 'install', "torch==2.6.0+$flavor", "torchaudio==2.6.0+$flavor", '--index-url', "https://download.pytorch.org/whl/$flavor")
        Invoke-Native -Executable $python -Arguments @('-m', 'pip', 'install', '-e', '.[demucs,packaging]')
    }

    Write-Host '[2/6] Preparing pinned decoder tools...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $archive = Join-Path $buildRoot 'ffmpeg-8.1.2-essentials_build.zip'
    $decoderHash = 'db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec'
    if (-not (Test-Path -LiteralPath $archive)) {
        $download = "$archive.download"
        if (-not (Test-Path -LiteralPath $download) -or
            (Get-FileSha256 -LiteralPath $download) -ne $decoderHash) {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip' -OutFile $download
        }
        if ((Get-FileSha256 -LiteralPath $download) -ne $decoderHash) {
            throw 'Downloaded decoder checksum mismatch.'
        }
        Move-Item -LiteralPath $download -Destination $archive
    }
    if ((Get-FileSha256 -LiteralPath $archive) -ne $decoderHash) {
        throw "Cached decoder checksum mismatch. Remove $archive and retry."
    }
    $decoderRoot = Join-Path $buildRoot 'windows-decoder'
    Expand-Archive -LiteralPath $archive -DestinationPath $decoderRoot -Force
    $decoder = Join-Path $decoderRoot 'ffmpeg-8.1.2-essentials_build'
    $notices = Join-Path $buildRoot 'WINDOWS_DECODER_NOTICES.txt'
    Get-Content -LiteralPath (Join-Path $decoder 'LICENSE') | Set-Content -Encoding UTF8 $notices
    Get-Content -LiteralPath (Join-Path $decoder 'README.txt') | Add-Content -Encoding UTF8 $notices
    Add-Content -Encoding UTF8 $notices 'Binary/source provenance: https://www.gyan.dev/ffmpeg/builds/ ; FFmpeg 8.1.2 essentials GPLv3 static build.'

    Write-Host '[3/6] Installing and checking frontend dependencies...'
    if (-not $CudaWorker) {
        Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'ci')
        Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'run', 'test')
    }

    Write-Host '[4/6] Building and checking the bundled backend...'
    Remove-GeneratedDirectory $staging
    Invoke-Native -Executable $python -Arguments @('packaging/build_backend.py', '--ffmpeg-dir', (Join-Path $decoder 'bin'), '--ffmpeg-notices', $notices, '--output', $staging)
    Invoke-Native -Executable $python -Arguments @('packaging/smoke_backend.py', (Join-Path $staging 'stemlab-backend.exe'), '--require-runtime')
    if ($CudaWorker) {
        Invoke-Native -Executable $python -Arguments @('packaging/package_cuda.py', '--runtime', $staging, '--output', (Join-Path $repoRoot 'dist\cuda'))
        Write-Host 'CUDA worker built. Publish windows-cuda.json and ALL archive parts from dist\cuda to the cuda-worker-v1 GitHub release after GPU validation.'
        exit 0
    }
    $noticeRoot = Join-Path $staging 'notices'
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'sbom', '--sbom-format', 'cyclonedx') | Set-Content -Encoding UTF8 (Join-Path $noticeRoot 'frontend-sbom.json')
    Invoke-Native -Executable $cargo -Arguments @('metadata', '--locked', '--manifest-path', 'desktop/src-tauri/Cargo.toml', '--format-version', '1', '--filter-platform', 'x86_64-pc-windows-msvc') | Set-Content -Encoding UTF8 (Join-Path $noticeRoot 'rust-dependencies.json')
    Invoke-Native -Executable $python -Arguments @('packaging/prepare_cpu_payload.py', '--runtime', $staging, '--archive-output', (Join-Path $repoRoot 'dist\components'))
    Invoke-Native -Executable (Join-Path $staging 'stemlab-backend.exe') -Arguments @('--runtime-probe')

    Write-Host '[5/6] Building Windows installer...'
    Assert-ManagedDirectory $runtime
    Assert-ManagedDirectory $previous
    Remove-GeneratedDirectory $previous
    if (Test-Path -LiteralPath $runtime) {
        Move-GeneratedDirectory -Source $runtime -Destination $previous
    }
    try {
        Move-GeneratedDirectory -Source $staging -Destination $runtime
    } catch {
        if (-not (Test-Path -LiteralPath $runtime) -and (Test-Path -LiteralPath $previous)) {
            Move-GeneratedDirectory -Source $previous -Destination $runtime
        }
        throw
    }
    $version = (Get-Content -Raw -LiteralPath 'desktop/package.json' | ConvertFrom-Json).version
    $name = "ViiB StemLab_${version}_x64-setup.exe"
    $installerPath = Join-Path $repoRoot "desktop\src-tauri\target\release\bundle\nsis\$name"
    $output = Join-Path $repoRoot 'dist\windows'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    $variants = if ($Installer -eq 'Both') { @('Full', 'OnDemand') } else { @($Installer) }
    # The executable discovers flavor from installer.json at runtime. Compile it
    # once, then bundle different resource/WebView2 sets without recompiling.
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'run', 'tauri', '--', 'build', '--config', 'src-tauri/tauri.release.conf.json', '--no-bundle')
    foreach ($variant in $variants) {
        Remove-GeneratedDirectory $releaseRuntime
        $configuration = if ($variant -eq 'Full') { 'src-tauri/tauri.release.conf.json' } else { 'src-tauri/tauri.ondemand.conf.json' }
        Write-Host "Building $variant Windows installer..."
        Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'run', 'tauri', '--', 'bundle', '--config', $configuration, '--bundles', 'nsis')
        if (-not (Test-Path -LiteralPath $installerPath)) { throw "Installer not found: $installerPath" }
        $variantName = "ViiB StemLab_${version}_x64-$($variant.ToLower())-setup.exe"
        Copy-Item -LiteralPath $installerPath -Destination (Join-Path $output $variantName) -Force
        $hash = Get-FileSha256 -LiteralPath (Join-Path $output $variantName)
        "$hash  $variantName" | Set-Content -Encoding ASCII (Join-Path $output "$variantName.sha256")
        Write-Host "Build complete: $(Join-Path $output $variantName)"
    }
    Write-Host '[6/6] Installer variants and checksums collected.'
    Remove-GeneratedDirectory $previous
    Write-Host 'Installers are unsigned. Publish the dist\components manifest/archive before distributing OnDemand.'
} catch {
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($buildLock) { $buildLock.Dispose() }
    Pop-Location
}
