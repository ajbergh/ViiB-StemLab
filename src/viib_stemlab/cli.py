from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from viib_stemlab import __version__
from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.constants import CANONICAL_STEMS, DEFAULT_MODEL
from viib_stemlab.doctor import get_doctor_report
from viib_stemlab.engines.demucs import DemucsEngine
from viib_stemlab.errors import GenerationCancelledError, StemLabError
from viib_stemlab.models import ModelCacheManager
from viib_stemlab.package import build_package_from_stems
from viib_stemlab.progress import ProgressUpdate
from viib_stemlab.queue import (
    JobRecord,
    JobStatus,
    QueueRunner,
    QueueStore,
    ingest_paths,
)
from viib_stemlab.services.generate import generate_package
from viib_stemlab.validation import PackageValidationError, validate_package


def _doctor(as_json: bool) -> int:
    report = get_doctor_report()
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"ViiB-StemLab {__version__}")
        print(f"Python: {report['python']}")
        print(f"Platform: {report['platform']} ({report['machine']})")
        print(
            "PyTorch: "
            + (f"{report['torch']['version']}" if report['torch']['available'] else "not installed")
        )
        print(f"CUDA available: {'yes' if report['torch']['cudaAvailable'] else 'no'}")
        if report['torch']['cudaRuntime']:
            print(f"CUDA runtime: {report['torch']['cudaRuntime']}")
        print(f"MPS available: {'yes' if report['torch']['mpsAvailable'] else 'no'}")
        print(f"Demucs: {'available' if report['demucs']['available'] else 'not available'}")
        print(f"Demucs version: {report['demucs']['version'] or '-'}")
        print(f"Devices: {', '.join(report['demucs']['devices'])}")
        print(f"Auto device: {report['demucs']['autoDevice']}")
        print(f"Supported inputs: {', '.join(report['input']['extensions'])}")
        print(f"FFmpeg available: {'yes' if report['input']['ffmpegAvailable'] else 'no'}")
        print(f"FFprobe available: {'yes' if report['input']['ffprobeAvailable'] else 'no'}")
        print(f"Model cache dir: {report['modelCache']['directory']}")
        for m in report['modelCache']['models']:
            size_mb = (m.get('sizeBytes') or 0) // 1048576
            status_str = f"cached ({size_mb} MB)" if m['cached'] else "not cached"
            print(f"Model {m['name']}: {status_str}")
        print(f"Disk free (current drive): {report['disk']['freeGb']} GB")
        detail = report['demucs']['detail'] or report['torch']['detail']
        if detail:
            print(f"Detail: {detail}")
    return 0


def _validate(package: Path, source: Path | None, no_hashes: bool) -> int:
    try:
        manifest = validate_package(
            package,
            source_path=source,
            verify_hashes=not no_hashes,
        )
    except PackageValidationError as exc:
        print("INVALID", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(f"VALID {manifest.packageId}")
    return 0


def _inspect(package: Path) -> int:
    try:
        manifest = validate_package(package, verify_hashes=False)
    except PackageValidationError as exc:
        print("Package is not structurally valid:", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(json.dumps(manifest.to_dict(), indent=2))
    return 0


def _package_build(args: argparse.Namespace) -> int:
    stems = {name: args.stems_dir / f"{name}.wav" for name in CANONICAL_STEMS}
    try:
        package = build_package_from_stems(
            source=args.source,
            stems=stems,
            output_root=args.output,
            engine_name=args.engine,
            model_name=args.model,
            model_version=args.model_version,
            device=args.device,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"package build failed: {exc}", file=sys.stderr)
        return 1

    print(package)
    return 0


def _generate(args: argparse.Namespace) -> int:
    engine = DemucsEngine(model=args.model, cache_dir=args.cache_dir)
    token = CancellationToken()
    last_percent: dict[str, int] = {}

    def progress(stage: str, value: float | None, message: str | None) -> None:
        if value is None:
            if message:
                print(f"[{stage}] {message}", file=sys.stderr)
            return
        percent = int(value * 100)
        if last_percent.get(stage) == percent:
            return
        last_percent[stage] = percent
        suffix = f" - {message}" if message else ""
        print(f"[{stage}] {percent}%{suffix}", file=sys.stderr)

    try:
        package = generate_package(
            source=args.source,
            output_root=args.output,
            engine=engine,
            device=args.device,
            overwrite=args.overwrite,
            fallback_to_cpu=args.fallback_to_cpu,
            cancellation_token=token,
            cache_dir=args.cache_dir,
            skip_preflight=args.skip_preflight,
            progress=progress,
        )
    except (KeyboardInterrupt, GenerationCancelledError):
        token.cancel()
        print("generation cancelled", file=sys.stderr)
        return 130
    except StemLabError as exc:
        print(f"generation failed: {exc.format_user_message()}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 1
    print(package)
    return 0


def _model_status(args: argparse.Namespace) -> int:
    mgr = ModelCacheManager(args.cache_dir)
    print(f"Model cache directory: {mgr.cache_dir}")
    for info in mgr.list_known_models():
        status = f"CACHED ({info.size_bytes // 1048576} MB)" if info.cached else "NOT CACHED"
        print(f"  {info.name} [{info.signature}]: {status}")
    return 0


def _model_download(args: argparse.Namespace) -> int:
    mgr = ModelCacheManager(args.cache_dir)
    model_name = args.model
    print(f"Downloading model '{model_name}' weights to {mgr.cache_dir}...", file=sys.stderr)
    try:
        path = mgr.download_model(
            model_name,
            progress=lambda stage, val, msg: print(
                f"[{stage}] {int(val * 100) if val is not None else 0}% - {msg}", file=sys.stderr
            ),
        )
    except Exception as exc:
        print(f"Model download failed: {exc}", file=sys.stderr)
        return 1
    print(f"Model weights saved: {path}")
    return 0


def _queue_add(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    result = ingest_paths(
        args.paths,
        store=store,
        output_library=args.output,
        model=args.model,
        device=args.device,
        fallback_to_cpu=args.fallback_to_cpu,
        overwrite=args.overwrite,
        recursive=not args.no_recursive,
    )
    print("Batch Ingestion Result:")
    print(f"  Added to queue:        {len(result.added)}")
    print(f"  Skipped (in queue):    {len(result.skipped_duplicate_queue)}")
    print(f"  Skipped (existing pkg):{len(result.skipped_existing_package)}")
    if result.invalid_files:
        print(f"  Invalid / skipped:     {len(result.invalid_files)}")
    return 0


def _queue_list(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    status_filter = JobStatus(args.status) if args.status else None
    jobs = store.list_jobs(status=status_filter, limit=args.limit)
    if args.as_json:
        print(json.dumps([j.to_dict() for j in jobs], indent=2))
        return 0

    if not jobs:
        filter_msg = f" with status '{args.status}'" if args.status else ""
        print(f"No jobs found in queue{filter_msg}.")
        return 0

    print(f"{'ID':<38} {'STATUS':<12} {'PROGRESS':<10} {'STAGE':<12} {'SOURCE'}")
    print("-" * 100)
    for j in jobs:
        pct = f"{int(j.progress * 100)}%" if j.progress is not None else "-"
        src_name = Path(j.source_path).name
        stage_str = j.stage or "-"
        print(f"{j.id:<38} {j.status.value:<12} {pct:<10} {stage_str:<12} {src_name}")
        if j.error_code:
            print(f"  -> Error [{j.error_code}]: {j.diagnostic_message or ''}")
    return 0


def _queue_start(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    recovered = store.recover_interrupted_jobs()
    if recovered:
        print(
            f"Recovered {recovered} orphan in-progress job(s) from previous run.",
            file=sys.stderr,
        )

    queued_count = store.count_jobs(JobStatus.QUEUED)
    if queued_count == 0:
        print("Queue is empty. No jobs to run.")
        return 0

    print(f"Starting queue processing ({queued_count} queued jobs)...", file=sys.stderr)

    def _on_prog(job: JobRecord, update: ProgressUpdate) -> None:
        pct = f"{int(update.progress * 100)}%" if update.progress is not None else "..."
        msg = f" - {update.message}" if update.message else ""
        print(f"[{Path(job.source_path).name}] [{update.stage}] {pct}{msg}", file=sys.stderr)

    runner = QueueRunner(store, on_progress=_on_prog)

    try:
        completed = runner.run_until_empty(max_jobs=args.max_jobs, recover_orphans=False)
        print(f"Queue processing complete. Successfully finished {completed} job(s).")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user. Cancelling active job...", file=sys.stderr)
        runner.cancel_current_job("Queue stopped by user interrupt (Ctrl+C)")
        return 130


def _queue_cancel(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    job = store.get_job(args.job_id)
    if not job:
        print(f"Job not found: {args.job_id}", file=sys.stderr)
        return 1
    store.mark_cancelled(args.job_id, args.reason)
    print(f"Job {args.job_id} marked cancelled.")
    return 0


def _queue_retry(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    job = store.retry_job(args.job_id)
    if not job:
        print(
            f"Job not found or not in failed/cancelled state: {args.job_id}",
            file=sys.stderr,
        )
        return 1
    print(f"Job {args.job_id} reset to queued.")
    return 0


def _queue_remove(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    deleted = store.delete_job(args.job_id)
    if not deleted:
        print(f"Job not found: {args.job_id}", file=sys.stderr)
        return 1
    print(f"Job {args.job_id} removed from queue.")
    return 0


def _queue_clear(args: argparse.Namespace) -> int:
    store = QueueStore(args.db)
    status_filter = JobStatus(args.status) if args.status else None
    count = store.clear_jobs(status=status_filter)
    status_desc = f"with status '{args.status}'" if args.status else "completed/failed/cancelled"
    print(f"Cleared {count} {status_desc} job(s) from queue.")
    return 0


def _ui(args: argparse.Namespace) -> int:
    import webbrowser

    from viib_stemlab.queue.runner import QueueRunner
    from viib_stemlab.queue.store import QueueStore
    from viib_stemlab.ui.server import StemLabHTTPServer

    store = QueueStore(args.db)
    runner = QueueRunner(store)
    static_dir = args.static_dir
    if static_dir is None:
        repo_dist = Path(__file__).resolve().parent.parent.parent / "desktop" / "dist"
        if repo_dist.is_dir():
            static_dir = repo_dist

    server = StemLabHTTPServer(
        (args.host, args.port),
        store=store,
        runner=runner,
        static_dir=static_dir,
        default_library_path=str(args.library) if args.library else None,
    )
    url = f"http://{args.host}:{args.port}"
    print(f"ViiB-StemLab Desktop UI running at: {url}")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down UI server...")
        runner.stop_background_worker(cancel_active=False)
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viib-stemlab",
        description="Prepare versioned local stem packages for ViiB MediaHub.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Inspect local separation capabilities.")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    generate = sub.add_parser("generate", help="Generate a ViiB Stem Package.")
    generate.add_argument("source", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--model", default=DEFAULT_MODEL)
    generate.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    generate.add_argument("--overwrite", action="store_true")
    generate.add_argument(
        "--fallback-to-cpu",
        action="store_true",
        help="Explicitly fall back to CPU if GPU separation fails or runs out of memory.",
    )
    generate.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Custom directory for model weight cache.",
    )
    generate.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight disk space and model cache checks.",
    )

    package = sub.add_parser("package", help="Build, inspect, or validate a stem package.")
    package_sub = package.add_subparsers(dest="package_command", required=True)

    build = package_sub.add_parser(
        "build",
        help="Package an existing six-stem WAV directory without running a separator.",
    )
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--stems-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--engine", default="external")
    build.add_argument("--model", default="external-six-stem")
    build.add_argument("--model-version", default="unknown")
    build.add_argument("--device", default="external")
    build.add_argument("--overwrite", action="store_true")

    validate = package_sub.add_parser("validate", help="Validate a ViiB Stem Package.")
    validate.add_argument("package", type=Path)
    validate.add_argument("--source", type=Path)
    validate.add_argument("--no-hashes", action="store_true")

    inspect = package_sub.add_parser("inspect", help="Print normalized package metadata.")
    inspect.add_argument("package", type=Path)

    model = sub.add_parser("model", help="Inspect and manage pretrained model weights.")
    model_sub = model.add_subparsers(dest="model_command", required=True)

    m_status = model_sub.add_parser("status", help="List model cache status and locations.")
    m_status.add_argument("--cache-dir", type=Path, default=None)

    m_download = model_sub.add_parser("download", help="Pre-download model weights to cache.")
    m_download.add_argument("model", default=DEFAULT_MODEL, nargs="?")
    m_download.add_argument("--cache-dir", type=Path, default=None)

    queue = sub.add_parser(
        "queue",
        help="Manage and process the durable stem preparation queue.",
    )
    queue_sub = queue.add_subparsers(dest="queue_command", required=True)

    q_add = queue_sub.add_parser("add", help="Add files or directories to the queue.")
    q_add.add_argument("paths", nargs="+", type=Path, help="Audio files or folders to add.")
    q_add.add_argument("--output", type=Path, required=True, help="Stem library directory.")
    q_add.add_argument("--model", default=DEFAULT_MODEL, help="Model name.")
    q_add.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    q_add.add_argument(
        "--fallback-to-cpu",
        action="store_true",
        default=True,
        help="Fall back to CPU on GPU error.",
    )
    q_add.add_argument("--overwrite", action="store_true", help="Overwrite existing packages.")
    q_add.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recursively scan subdirectories.",
    )
    q_add.add_argument("--db", type=Path, default=None, help="Custom queue database path.")

    q_list = queue_sub.add_parser("list", help="List jobs in the queue.")
    q_list.add_argument(
        "--status",
        choices=[s.value for s in JobStatus],
        default=None,
        help="Filter by status.",
    )
    q_list.add_argument("--limit", type=int, default=None, help="Max jobs to return.")
    q_list.add_argument("--json", action="store_true", dest="as_json")
    q_list.add_argument("--db", type=Path, default=None)

    q_start = queue_sub.add_parser("start", help="Process queued jobs.")
    q_start.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum number of jobs to run.",
    )
    q_start.add_argument("--db", type=Path, default=None)

    q_cancel = queue_sub.add_parser("cancel", help="Cancel a job in the queue.")
    q_cancel.add_argument("job_id", help="Job ID.")
    q_cancel.add_argument("--reason", default="Cancelled via CLI", help="Cancellation reason.")
    q_cancel.add_argument("--db", type=Path, default=None)

    q_retry = queue_sub.add_parser("retry", help="Retry a failed or cancelled job.")
    q_retry.add_argument("job_id", help="Job ID.")
    q_retry.add_argument("--db", type=Path, default=None)

    q_remove = queue_sub.add_parser("remove", help="Remove a job from the queue.")
    q_remove.add_argument("job_id", help="Job ID.")
    q_remove.add_argument("--db", type=Path, default=None)

    q_clear = queue_sub.add_parser("clear", help="Clear terminal jobs from the queue.")
    q_clear.add_argument(
        "--status",
        choices=[s.value for s in JobStatus],
        default=None,
        help="Filter by status.",
    )
    q_clear.add_argument("--db", type=Path, default=None)

    ui = sub.add_parser("ui", help="Launch the ViiB-StemLab desktop interface.")
    ui.add_argument("--port", type=int, default=8765, help="Port to serve UI (default: 8765).")
    ui.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1).")
    ui.add_argument("--no-browser", action="store_true", help="Do not open browser automatically.")
    ui.add_argument("--library", type=Path, default=None, help="Default stem library directory.")
    ui.add_argument("--static-dir", type=Path, default=None, help="Custom static frontend dist directory.")
    ui.add_argument("--db", type=Path, default=None, help="Custom queue database path.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ui":
        return _ui(args)
    if args.command == "doctor":
        return _doctor(args.as_json)
    if args.command == "generate":
        return _generate(args)
    if args.command == "package" and args.package_command == "build":
        return _package_build(args)
    if args.command == "package" and args.package_command == "validate":
        return _validate(args.package, args.source, args.no_hashes)
    if args.command == "package" and args.package_command == "inspect":
        return _inspect(args.package)
    if args.command == "model" and args.model_command == "status":
        return _model_status(args)
    if args.command == "model" and args.model_command == "download":
        return _model_download(args)
    if args.command == "queue":
        if args.queue_command == "add":
            return _queue_add(args)
        if args.queue_command == "list":
            return _queue_list(args)
        if args.queue_command == "start":
            return _queue_start(args)
        if args.queue_command == "cancel":
            return _queue_cancel(args)
        if args.queue_command == "retry":
            return _queue_retry(args)
        if args.queue_command == "remove":
            return _queue_remove(args)
        if args.queue_command == "clear":
            return _queue_clear(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
