import math
import os
import signal
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import requests

from .cloud_protocol import PROTOCOL_VERSION, command_problem
from .versioning import CURRENT_VERSION

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class CloudError(RuntimeError):
    pass


class RequestsTransport:
    def __init__(self, base_url, token, worker_id, timeout=(5.0, 30.0), session=None,
                 max_commands=32, boot_id=None, worker_version=CURRENT_VERSION,
                 allow_insecure_loopback=False):
        try:
            url = urlsplit(base_url)
            secure = url.scheme == "https" or (
                allow_insecure_loopback and url.scheme == "http"
                and url.hostname in _LOOPBACK_HOSTS)
            valid = (secure and url.hostname and url.port != 0
                     and url.username is None and url.password is None
                     and not url.query and not url.fragment
                     and "?" not in base_url and "#" not in base_url
                     and "\\" not in base_url
                     and not any(c.isspace() or ord(c) < 32 for c in base_url))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError("Invalid cloud URL")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError("Invalid worker token")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("Invalid worker ID")
        if len(timeout) != 2 or any(not math.isfinite(v) or v <= 0 for v in timeout):
            raise ValueError("Invalid request timeout")
        if max_commands < 1:
            raise ValueError("Invalid command limit")
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        # A fresh boot_id per process lets the API detect that in-memory runtime
        # state (and any command history) was lost across a worker restart.
        self.boot_id = boot_id or uuid.uuid4().hex
        self.worker_version = worker_version
        self.timeout = timeout
        self.max_commands = max_commands
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False
        self.headers = {"Authorization": "Bearer " + token}

    def _envelope(self, **fields):
        return dict(fields, worker_id=self.worker_id, boot_id=self.boot_id,
                    worker_version=self.worker_version, protocol_version=PROTOCOL_VERSION)

    def _post(self, path, payload, decode=False):
        response = None
        try:
            response = self.session.post(
                self.base_url + path, json=payload, headers=self.headers,
                timeout=self.timeout, allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                raise CloudError("Cloud request failed")
            return response.json() if decode else None
        except Exception:
            raise CloudError("Cloud request failed") from None
        finally:
            if response is not None:
                response.close()

    def poll(self):
        payload = self._post("/poll", self._envelope(), decode=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("commands"), list):
            raise CloudError("Invalid poll response")
        commands = payload["commands"]
        if len(commands) > self.max_commands:
            raise CloudError("Poll batch exceeds capacity")
        for command in commands:
            if command_problem(command) is not None:
                raise CloudError("Invalid command")
        return commands

    def report(self, records):
        self._post("/report", self._envelope(records=records))

    def close(self):
        self.session.close()


class CloudWorker:
    def __init__(self, supervisor, transport, max_workers=4, max_inflight=8,
                 max_commands=32, max_records=1024, report_batch=100,
                 poll_interval=1.0, health_interval=30.0, backoff_max=60.0,
                 shutdown_attempts=3, clock=time.monotonic, outbox=None):
        if min(max_workers, max_inflight, max_commands, report_batch, shutdown_attempts) < 1:
            raise ValueError("Invalid worker limits")
        if max_records < max_commands + max_inflight + 1:
            raise ValueError("Insufficient record capacity")
        if any(not math.isfinite(v) or v <= 0
               for v in (poll_interval, health_interval, backoff_max)):
            raise ValueError("Invalid worker intervals")
        self.supervisor = supervisor
        self.transport = transport
        self.max_inflight = max_inflight
        self.max_commands = max_commands
        self.max_records = max_records
        self.report_batch = report_batch
        self.poll_interval = poll_interval
        self.health_interval = health_interval
        self.backoff_max = backoff_max
        self.shutdown_attempts = shutdown_attempts
        self.clock = clock
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cloud")
        self.commands = deque()
        self.records = deque()
        self.futures = {}
        self.busy = set()
        self.next_poll = 0.0
        self.next_report = 0.0
        self.next_health = 0.0
        self.poll_failures = 0
        self.report_failures = 0
        self.closed = False
        self.outbox = outbox
        if outbox is not None:
            # Results/events a previous process produced but never delivered.
            self.records.extend(outbox.load(max_records))

    def stop(self):
        self.stop_event.set()

    def _record(self, kind, data, **fields):
        if len(self.records) >= self.max_records:
            raise CloudError("Record capacity exceeded")
        record = dict(fields, record_id=uuid.uuid4().hex, type=kind, data=data)
        self.records.append(record)
        if self.outbox is not None:
            try:
                self.outbox.add(record)
            except Exception:
                # Durability is best-effort; the in-memory queue still delivers.
                pass

    def _delay(self, failures):
        return min(self.backoff_max, self.poll_interval * 2 ** min(failures - 1, 16))

    def _collect(self):
        for future, command in list(self.futures.items()):
            if not future.done():
                continue
            try:
                result = future.result()
            except Exception:
                result = {"success": False, "error": "execution_failed"}
            if self.outbox is not None:
                try:
                    self.outbox.remember_result(command["command_id"], result)
                except Exception:
                    pass
            self._record("command_result", result, command_id=command["command_id"],
                         user_id=command["user_id"], instance_id=command["instance_id"])
            self.busy.remove((command["user_id"], command["instance_id"]))
            del self.futures[future]

    def _replayed(self, command):
        """Result of a command an earlier process already executed, if any."""
        if self.outbox is None:
            return None
        try:
            return self.outbox.recall_result(command["command_id"])
        except Exception:
            return None

    def _dispatch(self):
        for command in list(self.commands):
            if len(self.futures) >= self.max_inflight or self.stop_event.is_set():
                break
            key = (command["user_id"], command["instance_id"])
            if key in self.busy:
                continue
            self.commands.remove(command)
            previous = self._replayed(command)
            if previous is not None:
                # Redelivered after a restart: report the original outcome, never re-run.
                self._record("command_result", previous, command_id=command["command_id"],
                             user_id=command["user_id"], instance_id=command["instance_id"])
                continue
            self.busy.add(key)
            future = self.executor.submit(self.supervisor.execute, command)
            self.futures[future] = command

    def _report(self, now):
        if not self.records or now < self.next_report:
            return
        batch = list(self.records)[:self.report_batch]
        try:
            self.transport.report(batch)
        except Exception:
            self.report_failures += 1
            self.next_report = now + self._delay(self.report_failures)
            return
        for _ in batch:
            self.records.popleft()
        if self.outbox is not None:
            try:
                self.outbox.remove(batch)
            except Exception:
                pass
        self.report_failures = 0
        self.next_report = 0.0

    def _telemetry(self, now):
        available = self.max_records - len(self.records) - len(self.futures) - len(self.commands)
        if available <= 0:
            return
        drained = self.supervisor.drain_records(limit=available)
        if len(drained) > available:
            raise CloudError("Supervisor record capacity exceeded")
        for record in drained:
            self._record("event", record)
        if len(drained) < available and now >= self.next_health:
            self._record("health", self.supervisor.health())
            self.next_health = now + self.health_interval

    def tick(self):
        now = self.clock()
        self._collect()
        self._report(now)
        self._telemetry(now)
        self._dispatch()
        capacity = self.max_records - len(self.records) - len(self.futures)
        if (self.stop_event.is_set() or self.commands or now < self.next_poll
                or len(self.futures) >= self.max_inflight or capacity < self.max_commands):
            return
        try:
            commands = self.transport.poll()
            if len(commands) > self.max_commands:
                raise CloudError("Poll batch exceeds capacity")
        except Exception:
            self.poll_failures += 1
            self.next_poll = now + self._delay(self.poll_failures)
            return
        self.poll_failures = 0
        self.next_poll = now + self.poll_interval
        self.commands.extend(commands)
        self._dispatch()

    def run(self):
        try:
            while not self.stop_event.is_set():
                self.tick()
                self.stop_event.wait(min(0.1, self.poll_interval))
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop()
        try:
            self.supervisor.close()
        finally:
            self.executor.shutdown(wait=True)
            try:
                self._collect()
                while self.commands:
                    command = self.commands.popleft()
                    self._record("command_result", {"success": False, "error": "worker_stopped"},
                                 command_id=command["command_id"], user_id=command["user_id"],
                                 instance_id=command["instance_id"])
                self._telemetry(self.clock())
                for attempt in range(self.shutdown_attempts):
                    while self.records:
                        self.next_report = 0.0
                        self._report(self.clock())
                        if self.report_failures:
                            break
                    if not self.records:
                        break
                    if attempt + 1 < self.shutdown_attempts:
                        time.sleep(self._delay(self.report_failures))
            finally:
                self.transport.close()
                if self.outbox is not None:
                    self.outbox.close()
        if self.records:
            raise CloudError("Unreported records at shutdown")


def main():
    transport = None
    worker = None
    previous = {}
    try:
        transport = RequestsTransport(
            os.environ.get("MUDAREMOTE_CLOUD_URL", ""),
            os.environ.get("MUDAREMOTE_WORKER_TOKEN", ""),
            os.environ.get("MUDAREMOTE_WORKER_ID", ""),
            allow_insecure_loopback=os.environ.get("MUDAREMOTE_ALLOW_INSECURE_LOOPBACK") == "1",
        )
        from .worker import WorkerSupervisor
        from .worker_outbox import Outbox
        state_dir = os.environ.get("MUDAREMOTE_WORKER_STATE_DIR")
        outbox = Outbox(os.path.join(state_dir, "outbox.sqlite3")) if state_dir else None
        worker = CloudWorker(WorkerSupervisor(), transport, outbox=outbox)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: worker.stop())
        worker.run()
        return 0
    except (Exception, KeyboardInterrupt):
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if worker is not None and not worker.closed:
            try:
                worker.close()
            except Exception:
                pass
        elif worker is None and transport is not None:
            transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
