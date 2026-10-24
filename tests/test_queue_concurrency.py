from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from viib_stemlab.queue.models import JobStatus
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.ui.settings import SettingsStore


class GatedGeneration:
    def __init__(self, monkeypatch, root):
        self.condition = threading.Condition()
        self.started = []
        self.releases = {str(root / f'{i}.wav'): threading.Event() for i in range(6)}
        monkeypatch.setattr('viib_stemlab.queue.runner.generate_package', self.generate)

    def generate(self, *, source, output_root, cancellation_token, **kwargs):
        release = self.releases[str(source)]
        cancellation_token.add_callback(release.set)
        with self.condition:
            self.started.append(str(source))
            self.condition.notify_all()
        assert release.wait(10), 'Test did not release song'
        cancellation_token.raise_if_cancelled()
        return output_root / source.stem

    def wait_started(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.started) >= count, timeout=5)

    def release_all(self):
        for event in self.releases.values():
            event.set()


def setup_queue(tmp_path, monkeypatch, count=5, concurrency=1):
    store = QueueStore(tmp_path / 'queue.db')
    jobs = [store.add_job(tmp_path / f'{i}.wav', tmp_path / 'out') for i in range(count)]
    gate = GatedGeneration(monkeypatch, tmp_path)
    runner = QueueRunner(store, engine=object(), concurrency=concurrency)
    return store, jobs, gate, runner


@pytest.mark.parametrize('limit', [1, 2, 3])
def test_concurrency_limit_and_completion(tmp_path, monkeypatch, limit):
    store, jobs, gate, runner = setup_queue(tmp_path, monkeypatch, concurrency=limit)
    thread = runner.start_background_worker()
    try:
        gate.wait_started(limit)
        assert len(runner.active_job_ids) == limit
        assert store.count_jobs(JobStatus.QUEUED) == len(jobs) - limit
        assert len(gate.started) == limit
    finally:
        gate.release_all()
        thread.join(10)
    assert not thread.is_alive()
    assert len(gate.started) == len(set(gate.started)) == len(jobs)
    assert store.count_jobs(JobStatus.COMPLETE) == len(jobs)
    assert runner.active_job_ids == []


def test_cancel_one_song_and_pause_drains_peers(tmp_path, monkeypatch):
    store, jobs, gate, runner = setup_queue(tmp_path, monkeypatch, concurrency=3)
    thread = runner.start_background_worker()
    try:
        gate.wait_started(3)
        runner.request_stop()
        assert runner.cancel_job(jobs[0].id)
        gate.releases[jobs[1].source_path].set()
        gate.releases[jobs[2].source_path].set()
        thread.join(10)
        assert not thread.is_alive()
        assert store.get_job(jobs[0].id).status == JobStatus.CANCELLED
        assert all(store.get_job(j.id).status == JobStatus.COMPLETE for j in jobs[1:3])
        assert store.count_jobs(JobStatus.QUEUED) == 2
        assert len(gate.started) == 3
    finally:
        gate.release_all()
        thread.join(10)


def test_stop_cancels_every_active_song_and_can_restart(tmp_path, monkeypatch):
    store, jobs, gate, runner = setup_queue(tmp_path, monkeypatch, concurrency=3)
    thread = runner.start_background_worker()
    try:
        gate.wait_started(3)
        runner.stop_background_worker(cancel_active=True)
        assert not thread.is_alive()
        assert store.count_jobs(JobStatus.CANCELLED) == 3
        assert store.count_jobs(JobStatus.QUEUED) == 2
        gate.release_all()
        runner.start_background_worker().join(10)
        assert store.count_jobs(JobStatus.COMPLETE) == 2
    finally:
        gate.release_all()
        thread.join(10)


def test_live_limit_changes_and_recovery_guard(tmp_path, monkeypatch):
    store, jobs, gate, runner = setup_queue(tmp_path, monkeypatch, concurrency=1)
    completed = []
    def on_completed(job):
        with gate.condition:
            completed.append(job.id)
            gate.condition.notify_all()
    runner.on_job_completed = on_completed
    thread = runner.start_background_worker()
    try:
        gate.wait_started(1)
        with pytest.raises(RuntimeError, match='already processing'):
            runner.run_until_empty()
        assert store.get_job(jobs[0].id).status == JobStatus.PREPARING
        runner.concurrency = 3
        gate.wait_started(3)
        runner.concurrency = 1
        gate.releases[jobs[0].source_path].set()
        gate.releases[jobs[1].source_path].set()
        with gate.condition:
            assert gate.condition.wait_for(lambda: len(completed) == 2, timeout=5)
        assert len(gate.started) == 3
        assert store.count_jobs(JobStatus.QUEUED) == 2
        gate.releases[jobs[2].source_path].set()
        gate.wait_started(4)
        assert len(runner.active_job_ids) == 1
        assert store.count_jobs(JobStatus.QUEUED) == 1
        gate.release_all()
        thread.join(10)
        assert store.count_jobs(JobStatus.COMPLETE) == 5
    finally:
        gate.release_all()
        thread.join(10)


def test_atomic_claims_and_duplicate_output_protection(tmp_path):
    store = QueueStore(tmp_path / 'queue.db')
    first = store.add_job(tmp_path / 'same.wav', tmp_path / 'out', source_hash='same')
    duplicate = store.add_job(tmp_path / 'copy.wav', tmp_path / 'out', source_hash='same')
    others = [store.add_job(tmp_path / f'{i}.wav', tmp_path / 'out') for i in range(4)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: store.claim_next_queued_job(), range(6)))
    ids = [j.id for j in claims if j]
    assert len(ids) == len(set(ids)) == 5
    assert set(ids) == {first.id, *(j.id for j in others)}
    assert not store.cancel_queued_job(first.id, 'too late')
    assert not store.delete_job(first.id)
    assert store.clear_jobs(JobStatus.PREPARING) == 0
    store.mark_completed(first.id, tmp_path / 'done')
    assert store.claim_next_queued_job().id == duplicate.id


def test_max_jobs_and_peer_failure(tmp_path, monkeypatch):
    store = QueueStore(tmp_path / 'queue.db')
    for i in range(5):
        store.add_job(tmp_path / f'{i}.wav', tmp_path / 'out')

    def generate(**kwargs):
        if kwargs['source'].stem == '0':
            raise RuntimeError('bad song')
        return tmp_path / kwargs['source'].stem

    monkeypatch.setattr('viib_stemlab.queue.runner.generate_package', generate)
    runner = QueueRunner(store, engine=object(), concurrency=3)
    assert runner.run_until_empty(max_jobs=3) == 3
    assert store.count_jobs(JobStatus.FAILED) == 1
    assert store.count_jobs(JobStatus.COMPLETE) == 2
    assert store.count_jobs(JobStatus.QUEUED) == 2
    assert runner.active_job_ids == []


def test_concurrency_preferences_persist_and_validate(tmp_path):
    path = tmp_path / 'settings.json'
    settings = SettingsStore(path, str(tmp_path))
    assert settings.get()['concurrency'] == 1
    for limit in (2, 3, 1):
        settings.update({'concurrency': limit})
        assert SettingsStore(path, str(tmp_path)).get()['concurrency'] == limit
    for invalid in (0, 4, True, 2.0, '2', None):
        with pytest.raises(ValueError):
            settings.update({'concurrency': invalid})
        with pytest.raises(ValueError):
            QueueRunner(QueueStore(tmp_path / 'queue.db'), concurrency=invalid)


def test_same_output_name_without_hash_is_serialized(tmp_path):
    store = QueueStore(tmp_path / 'queue.db')
    first = store.add_job(tmp_path / 'a' / 'Song.wav', tmp_path / 'out', overwrite=True)
    second = store.add_job(tmp_path / 'b' / 'song.wav', tmp_path / 'out', overwrite=True)
    assert store.claim_next_queued_job().id == first.id
    assert store.claim_next_queued_job() is None
    store.mark_completed(first.id, tmp_path / 'out' / 'song.viibstems')
    assert store.claim_next_queued_job().id == second.id


def test_cancel_as_generation_returns_is_honored(tmp_path, monkeypatch):
    store = QueueStore(tmp_path / 'queue.db')
    job = store.add_job(tmp_path / 'song.wav', tmp_path / 'out')
    runner = QueueRunner(store, engine=object())

    def generate(**kwargs):
        assert runner.cancel_job(job.id)
        return tmp_path / 'package'

    monkeypatch.setattr('viib_stemlab.queue.runner.generate_package', generate)
    assert not runner.run_next()
    assert store.get_job(job.id).status == JobStatus.CANCELLED
    store.retry_job(job.id)
    monkeypatch.setattr('viib_stemlab.queue.runner.generate_package', lambda **kwargs: tmp_path / 'package')
    assert runner.run_next()
    assert not runner.cancel_job(job.id)
    assert store.get_job(job.id).status == JobStatus.COMPLETE
