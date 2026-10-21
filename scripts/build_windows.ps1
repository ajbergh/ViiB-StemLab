[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
if ($Help) {
    Write-Host @'
Usage: scripts\build_windows.bat [-CheckOnly]

Builds the unsigned Windows x64 CPU installer, including Python, Demucs,
FFmpeg/FFprobe, notices, and the offline WebView2 installer.

Prerequisites: x64 Python 3.12/3.13 (or an existing packaging environment),
Node.js 22+, Rust/Cargo, and Visual Studio C++ build tools with a Windows SDK.
Internet access is required for dependencies on the first build.

-CheckOnly checks prerequisites without installing dependencies or building.
Close running StemLab development/release windows before a full build.
Output: dist\windows\ViiB StemLab_<version>_x64-setup.exe
'@
    exit 0
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = Join-Path $repoRoot 'build'
$python = Join-Path $buildRoot 'packaging-venv\Scripts\python.exe'
$runtime = Join-Path $repoRoot 'desktop\src-tauri\runtime'
$staging = Join-Path $buildRoot 'windows-runtime-next'
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

Push-Location $repoRoot
try {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $cargo = (Get-Command cargo.exe -ErrorAction Stop).Source
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
    Invoke-Native -Executable $npm -Arguments @('--version')
    Invoke-Native -Executable $node -Arguments @('-e', 'if (parseInt(process.versions.node, 10) < 22) process.exit(1)')
    Invoke-Native -Executable $cargo -Arguments @('--version')
    if ($CheckOnly) {
        Write-Host 'Prerequisites found. Visual Studio C++/SDK availability is checked by Cargo during a full build.'
        exit 0
    }
    if (Get-Process -Name 'viib-stemlab-desktop' -ErrorAction SilentlyContinue) {
        throw 'Close StemLab windows before building so the release executable is not locked.'
    }

    Write-Host '[1/6] Preparing isolated CPU packaging environment...'
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    $buildLock = [IO.File]::Open((Join-Path $buildRoot 'windows-build.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if (-not (Test-Path -LiteralPath $python)) {
        Invoke-Native -Executable $bootstrap -Arguments ($bootstrapArguments + @('-m', 'venv', (Join-Path $buildRoot 'packaging-venv')))
    }
    if ($uv) {
        Invoke-Native -Executable $uv.Source -Arguments @('pip', 'install', '--python', $python, 'torch==2.6.0+cpu', 'torchaudio==2.6.0+cpu', '--index-url', 'https://download.pytorch.org/whl/cpu')
        Invoke-Native -Executable $uv.Source -Arguments @('pip', 'install', '--python', $python, '-e', '.[demucs,packaging]')
    } else {
        Invoke-Native -Executable $python -Arguments @('-m', 'ensurepip', '--upgrade')
        Invoke-Native -Executable $python -Arguments @('-m', 'pip', 'install', 'torch==2.6.0+cpu', 'torchaudio==2.6.0+cpu', '--index-url', 'https://download.pytorch.org/whl/cpu')
        Invoke-Native -Executable $python -Arguments @('-m', 'pip', 'install', '-e', '.[demucs,packaging]')
    }

    Write-Host '[2/6] Preparing pinned decoder tools...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $archive = Join-Path $buildRoot 'ffmpeg-8.1.2-essentials_build.zip'
    $decoderHash = 'db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec'
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip' -OutFile "$archive.download"
        if ((Get-FileHash -LiteralPath "$archive.download" -Algorithm SHA256).Hash.ToLower() -ne $decoderHash) {
            throw 'Downloaded decoder checksum mismatch.'
        }
        Move-Item -LiteralPath "$archive.download" -Destination $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $decoderHash) {
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
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'ci')
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'run', 'test')

    Write-Host '[4/6] Building and checking the bundled backend...'
    Remove-GeneratedDirectory $staging
    Invoke-Native -Executable $python -Arguments @('packaging/build_backend.py', '--ffmpeg-dir', (Join-Path $decoder 'bin'), '--ffmpeg-notices', $notices, '--output', $staging)
    Invoke-Native -Executable $python -Arguments @('packaging/smoke_backend.py', (Join-Path $staging 'stemlab-backend.exe'), '--require-runtime')
    $noticeRoot = Join-Path $staging 'notices'
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'sbom', '--sbom-format', 'cyclonedx') | Set-Content -Encoding UTF8 (Join-Path $noticeRoot 'frontend-sbom.json')
    Invoke-Native -Executable $cargo -Arguments @('metadata', '--locked', '--manifest-path', 'desktop/src-tauri/Cargo.toml', '--format-version', '1', '--filter-platform', 'x86_64-pc-windows-msvc') | Set-Content -Encoding UTF8 (Join-Path $noticeRoot 'rust-dependencies.json')

    Write-Host '[5/6] Building Windows installer...'
    Assert-ManagedDirectory $runtime
    Assert-ManagedDirectory $previous
    Remove-GeneratedDirectory $previous
    if (Test-Path -LiteralPath $runtime) {
        Move-Item -LiteralPath $runtime -Destination $previous
    }
    Move-Item -LiteralPath $staging -Destination $runtime
    Remove-GeneratedDirectory $releaseRuntime
    Invoke-Native -Executable $npm -Arguments @('--prefix', 'desktop', 'run', 'package', '--', '--bundles', 'nsis')

    Write-Host '[6/6] Collecting installer...'
    $version = (Get-Content -Raw -LiteralPath 'desktop/package.json' | ConvertFrom-Json).version
    $name = "ViiB StemLab_${version}_x64-setup.exe"
    $installer = Join-Path $repoRoot "desktop\src-tauri\target\release\bundle\nsis\$name"
    if (-not (Test-Path -LiteralPath $installer)) { throw "Installer not found: $installer" }
    $output = Join-Path $repoRoot 'dist\windows'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    Copy-Item -LiteralPath $installer -Destination (Join-Path $output $name) -Force
    $hash = (Get-FileHash -LiteralPath (Join-Path $output $name) -Algorithm SHA256).Hash.ToLower()
    "$hash  $name" | Set-Content -Encoding ASCII (Join-Path $output "$name.sha256")
    Remove-GeneratedDirectory $previous
    Write-Host "Build complete: $(Join-Path $output $name)"
    Write-Host 'The installer is unsigned. Model weights download through the app on first use.'
} catch {
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($buildLock) { $buildLock.Dispose() }
    Pop-Location
}
