import copy
import hashlib
import json
import multiprocessing
import os
import queue
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from .bot_runtime import RuntimeManager
from .cloud_protocol import ACTIONS, command_problem


def _safe(value, secrets):
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if any(part in str(k).lower() for part in
                ("token", "password", "secret", "credential", "authorization", "api_key"))
                else _safe(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, secrets) for item in value]
    return value


def redact(value, secrets=()):
    """Public redaction used on every worker record: masks secret-looking keys and
    any exact secret values. Hosts reuse it so redaction rules never diverge."""
    return _safe(value, set(secrets))


def _runtime_process(connection, events, heartbeat, dropped, instance_id):
    events.cancel_join_thread()
    secrets = set()

    def emit(event):
        try:
            events.put_nowait(_safe(event.to_dict(), secrets))
        except queue.Full:
            with dropped.get_lock():
                dropped.value += 1

    def give_up(reason):
        # The connection watchdog could not repair the client in this process. Exit so the supervisor
        # reports the instance as crashed and the Cloud starts it again. The pause lets the last events
        # (what the watchdog saw) leave through the queue feeder thread.
        time.sleep(1.5)
        os._exit(70)

    manager = RuntimeManager(event_callback=emit, fatal_callback=give_up)
    started = False
    try:
        while True:
            heartbeat.value = time.monotonic()
            if not connection.poll(0.2):
                continue
            command = connection.recv()
            action = command["action"]
            try:
                if action == "start":
                    secrets.add(command["credentials"]["token"].strip())
                    manager.start_instance(command["preset_name"], command["preset_data"],
                                           command["credentials"], instance_id=instance_id)
                    started = True
                    result = manager.get_status(instance_id)
                elif action == "stop":
                    result = {"stopped": manager.stop_instance(instance_id)}
                elif action == "restart":
                    result = {"restarted": manager.restart_instance(instance_id)}
                elif action == "preset_update":
                    result = manager.apply_preset(instance_id, command["preset_data"])
                elif action == "status":
                    result = manager.get_status(instance_id)
                elif action == "shutdown":
                    manager.shutdown_all()
                    connection.send({"success": True, "result": {"stopped": True}})
                    break
                else:
                    raise ValueError("Unsupported action")
                connection.send(_safe({"success": True, "result": result}, secrets))
            except Exception:
                connection.send({"success": False, "error": "runtime_command_failed"})
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if started:
            manager.shutdown_all()
        connection.close()
        events.close()


class _Slot:
    def __init__(self, key=None):
        self.key = key
        self.lock = threading.RLock()
        self.process = None
        self.connection = None
        self.events = None
        self.heartbeat = None
        self.dropped = None
        self.secrets = set()
        self.state = "stopped"
        self.failed = False
        self.seen = OrderedDict()
        self.start_command = None
        self.crash_reported = False
        self.backlog = []
        self.synthetic = []


class WorkerSupervisor:
    def __init__(self, max_instances=32, event_capacity=256, command_timeout=50.0,
                 health_timeout=65.0, history_size=256, context=None,
                 process_target=_runtime_process):
        if min(max_instances, event_capacity, command_timeout, history_size) <= 0:
            raise ValueError("Invalid worker limits")
        if health_timeout <= command_timeout:
            raise ValueError("Health timeout must exceed command timeout")
        self.context = context or multiprocessing.get_context("spawn")
        self.process_target = process_target
        self.max_instances = max_instances
        self.event_capacity = event_capacity
        self.command_timeout = command_timeout
        self.health_timeout = health_timeout
        self.history_size = history_size
        self.slots = {}
        self.lock = threading.RLock()
        self.closed = False

    def _validate(self, command):
        if command_problem(command) is not None:
            raise ValueError("Invalid command")
        if command["action"] in {"start", "preset_update"} or (
                command["action"] == "restart" and "preset_data" in command):
            preset = command.get("preset_data")
            if not isinstance(preset, dict) or any(
                not isinstance(k, str) or k.startswith("_") or k in
                {"token", "tokens", "credentials", "token_ref"} for k in preset
            ):
                raise ValueError("Invalid preset")
        if command["action"] == "start":
            credentials = command.get("credentials")
            if (not isinstance(credentials, dict) or set(credentials) != {"token"}
                    or not isinstance(credentials["token"], str) or not credentials["token"].strip()
                    or not isinstance(command.get("preset_name"), str) or not command["preset_name"]):
                raise ValueError("Invalid start payload")
        encoded = json.dumps(command, sort_keys=True, allow_nan=False)
        if len(encoded) > 1024 * 1024:
            raise ValueError("Command too large")
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _spawn(self, slot, key):
        parent, child = self.context.Pipe()
        slot.events = self.context.Queue(self.event_capacity)
        slot.heartbeat = self.context.Value("d", time.monotonic())
        slot.dropped = self.context.Value("L", 0)
        slot.connection = parent
        slot.failed = False
        slot.process = self.context.Process(
            target=self.process_target,
            args=(child, slot.events, slot.heartbeat, slot.dropped, key[1]),
            name="MudaRemote-instance",
        )
        try:
            slot.process.start()
        finally:
            child.close()

    def _mark_crashed(self, slot, message):
        """Record an unexpected runtime loss once so the Cloud can report it."""
        slot.failed = True
        slot.state = "failed"
        if slot.crash_reported or slot.key is None:
            return
        slot.crash_reported = True
        slot.synthetic.append({
            "instance_id": slot.key[1],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "process_crashed",
            "data": {"message": message, "fatal": True},
        })

    def _salvage_events(self, slot):
        # Events queued just before an exit are the most useful ones; keep them.
        while slot.events is not None and len(slot.backlog) < self.event_capacity:
            try:
                slot.backlog.append(slot.events.get_nowait())
            except (queue.Empty, OSError, ValueError):
                break

    def _dispose(self, slot):
        process = slot.process
        self._salvage_events(slot)
        if process is not None:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(3)
            if process.is_alive():
                process.kill()
                process.join(3)
            if process.is_alive():
                raise RuntimeError("Process did not exit")
            process.close()
        if slot.connection is not None:
            slot.connection.close()
        if slot.events is not None:
            slot.events.close()
        slot.process = None
        slot.connection = None
        slot.events = None

    def _request(self, slot, command):
        replies = queue.Queue(maxsize=1)
        connection = slot.connection

        def exchange():
            try:
                connection.send(command)
                replies.put((True, connection.recv()))
            except Exception:
                replies.put((False, None))

        thread = threading.Thread(target=exchange, daemon=True)
        thread.start()
        try:
            ok, response = replies.get(timeout=self.command_timeout)
            if not ok:
                raise EOFError()
            if not isinstance(response, dict) or "success" not in response:
                raise ValueError("Invalid runtime response")
            return _safe(response, slot.secrets)
        except (OSError, EOFError, queue.Empty, ValueError):
            self._mark_crashed(slot, "MudaRemote stopped unexpectedly.")
            self._dispose(slot)
            thread.join(1)
            return {"success": False, "error": "runtime_unresponsive"}

    def execute(self, command):
        try:
            command = copy.deepcopy(command)
            fingerprint = self._validate(command)
        except (ValueError, TypeError, RecursionError):
            return {"success": False, "error": "invalid_command"}
        key = (command["user_id"], command["instance_id"])
        with self.lock:
            if self.closed:
                return {"success": False, "error": "worker_stopped"}
            slot = self.slots.get(key)
            if slot is None:
                if command["action"] != "start":
                    return {"success": False, "error": "instance_not_found"}
                if len(self.slots) >= self.max_instances:
                    return {"success": False, "error": "instance_limit"}
                slot = self.slots[key] = _Slot(key)
        with slot.lock:
            if self.closed:
                return {"success": False, "error": "worker_stopped"}
            previous = slot.seen.get(command["command_id"])
            if previous is not None:
                if previous[0] != fingerprint:
                    return {"success": False, "error": "command_id_conflict"}
                return copy.deepcopy(previous[1])
            action = command["action"]
            alive = slot.process is not None and slot.process.is_alive()
            # A restart that carries the desired preset is a clean stop + start with
            # exactly that preset, so restart-only keys take effect and a stale
            # start command is never replayed.
            replace_preset = (action == "restart" and "preset_data" in command
                              and slot.start_command is not None)
            if action == "start" or (action == "restart" and slot.start_command
                                     and (not alive or replace_preset)):
                if action == "start" and alive and slot.state != "stopped":
                    response = {"success": False, "error": "instance_exists"}
                else:
                    if alive:
                        self._request(slot, {"action": "shutdown"})
                    self._dispose(slot)
                    if action == "start":
                        start_command = command
                    else:
                        start_command = copy.deepcopy(slot.start_command)
                        if "preset_data" in command:
                            start_command["preset_data"] = command["preset_data"]
                    slot.secrets.add(start_command["credentials"]["token"].strip())
                    slot.crash_reported = False
                    try:
                        self._spawn(slot, key)
                        response = self._request(slot, start_command)
                        slot.state = response.get("result", {}).get("state", "failed")
                        if response.get("success"):
                            slot.start_command = copy.deepcopy(start_command)
                        if action == "restart":
                            response.setdefault("result", {})["restarted"] = response["success"]
                    except Exception:
                        self._dispose(slot)
                        slot.failed = True
                        slot.state = "failed"
                        response = {"success": False, "error": "spawn_failed"}
            elif not alive:
                response = {"success": action in {"status", "stop"},
                            "result": {"state": "failed" if slot.failed or slot.process else "stopped"}}
                if not response["success"]:
                    response["error"] = "instance_not_running"
            else:
                response = self._request(slot, command)
                result = response.get("result", {})
                if action == "status":
                    slot.state = result.get("state", slot.state)
                elif action == "stop" and result.get("stopped"):
                    slot.state = "stopped"
                elif action == "restart" and result.get("restarted"):
                    slot.state = "running"
            slot.seen[command["command_id"]] = (fingerprint, copy.deepcopy(response))
            while len(slot.seen) > self.history_size:
                slot.seen.popitem(last=False)
            return response

    def drain_records(self, limit=100):
        records = []
        with self.lock:
            slots = list(self.slots.items())
        for (user_id, instance_id), slot in slots:
            if not slot.lock.acquire(blocking=False):
                continue
            try:
                if (slot.process is not None and not slot.process.is_alive()
                        and slot.state != "stopped" and not slot.crash_reported):
                    self._mark_crashed(slot, "MudaRemote stopped unexpectedly.")
                    self._salvage_events(slot)
                pending = slot.backlog + slot.synthetic
                slot.backlog, slot.synthetic = [], []
                while pending and len(records) < limit:
                    records.append({"record_id": uuid.uuid4().hex, "user_id": user_id,
                                    "instance_id": instance_id,
                                    "event": _safe(pending.pop(0), slot.secrets)})
                slot.backlog = pending
                while slot.events is not None and len(records) < limit:
                    try:
                        event = slot.events.get_nowait()
                    except (queue.Empty, OSError, ValueError):
                        break
                    records.append({"record_id": uuid.uuid4().hex, "user_id": user_id,
                                    "instance_id": instance_id, "event": _safe(event, slot.secrets)})
            finally:
                slot.lock.release()
        return records

    def health(self):
        now = time.monotonic()
        with self.lock:
            slots = list(self.slots.items())
        instances = []
        for (user_id, instance_id), slot in slots:
            if not slot.lock.acquire(blocking=False):
                instances.append({"user_id": user_id, "instance_id": instance_id,
                                  "health": "command_in_progress"})
                continue
            try:
                alive = slot.process is not None and slot.process.is_alive()
                age = max(0.0, now - slot.heartbeat.value) if slot.heartbeat else None
                if alive and age <= self.health_timeout:
                    response = self._request(slot, {"action": "status"})
                    slot.state = response.get("result", {}).get("state", slot.state)
                    alive = slot.process is not None and slot.process.is_alive()
                state = slot.state
                if slot.failed or (slot.process is not None and not alive):
                    state = "failed"
                instances.append({"user_id": user_id, "instance_id": instance_id,
                                  "state": state, "process_alive": alive,
                                  "heartbeat_age_seconds": age,
                                  "health": "unresponsive" if alive and age > self.health_timeout else
                                  "failed" if state == "failed" else "responsive" if alive else "stopped",
                                  "dropped_events": slot.dropped.value if slot.dropped else 0})
            finally:
                slot.lock.release()
        return {"closed": self.closed, "instances": instances}

    def close(self):
        with self.lock:
            self.closed = True
            slots = list(self.slots.values())
        for slot in slots:
            with slot.lock:
                if slot.process is not None and slot.process.is_alive():
                    self._request(slot, {"action": "shutdown"})
                    if slot.process is not None:
                        slot.process.join(1)
                self._dispose(slot)
                slot.state = "stopped"
