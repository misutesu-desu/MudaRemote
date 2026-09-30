"""
Reusable cloud-capable bot runtime with instance isolation and lifecycle management.

External API:
    BotInstance: Start/stop/restart individual bot accounts with external credentials
    RuntimeManager: Multi-instance coordinator with event callbacks
    InstanceState: Status enumeration (STARTING, RUNNING, STOPPING, STOPPED, FAILED)
    InstanceEvent: Structured events (state changes, errors, important actions)

Design:
    - Each instance runs in its own thread with isolated state
    - External credentials never persisted to files/logs/errors
    - Structured events separate from log scraping
    - Deterministic shutdown with timeout
    - Live preset application with restart-required tracking
    - Compatible with existing desktop launcher via shared bot entry point
"""

import asyncio
import copy
import threading
import time
import traceback
import re
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from .activity_events import ActivityClassifier
from .watchdog import ConnectionWatchdog


def _redact_credentials(obj, known_secrets=None):
    """
    Recursively redact credential strings from any data structure.

    Args:
        obj: Object to redact
        known_secrets: Optional set of exact secret strings to redact
    """
    if known_secrets is None:
        known_secrets = set()

    if isinstance(obj, str):
        # Exact match redaction for known secrets (handles short tokens, embedded strings)
        for secret in known_secrets:
            if secret and secret in obj:
                obj = obj.replace(secret, "[REDACTED]")

        # Pattern-based redaction for Discord tokens (length > 50, contains dots)
        if len(obj) > 50 and '.' in obj and obj.count('.') >= 2:
            return "[REDACTED_TOKEN]"
        return obj
    elif isinstance(obj, dict):
        # Redact sensitive keys and recurse through values
        result = {}
        for k, v in obj.items():
            if k in ('token', 'tokens', 'credentials', 'password', 'secret', 'api_key'):
                result[k] = "[REDACTED]"
            else:
                result[k] = _redact_credentials(v, known_secrets)
        return result
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_redact_credentials(item, known_secrets) for item in obj)
    else:
        return obj


class InstanceState(Enum):
    """Runtime instance lifecycle states."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class InstanceEvent:
    """Structured event from a runtime instance."""
    instance_id: str
    timestamp: datetime
    event_type: str  # state_change, error, claim, roll_reset, kakera, wishlist, preset_applied, etc
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with credentials redacted."""
        return {
            "instance_id": self.instance_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "data": _redact_credentials(self.data),
        }


class BotInstance:
    """
    Single bot account runtime instance with lifecycle control.

    Lifecycle:
        1. Create instance with preset + credentials
        2. start() launches thread and connects to Discord
        3. apply_preset() updates settings live (may require restart for some keys)
        4. stop() gracefully shuts down (timeout enforced)
        5. restart() stops then starts

    State tracking:
        - state: current InstanceState
        - error: last error message if FAILED
        - restart_required: keys that need restart to apply
        - applied_preset_changes: track last successful live apply

    Thread safety:
        - All public methods are thread-safe
        - Callbacks execute on the instance's event loop or runtime thread
    """

    def __init__(
        self,
        instance_id: str,
        preset_name: str,
        preset_data: Dict[str, Any],
        credentials: Dict[str, Any],
        event_callback: Optional[Callable[[InstanceEvent], None]] = None,
        fatal_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize bot instance.

        Args:
            instance_id: Unique identifier for this instance
            preset_name: Display name for logging
            preset_data: Bot configuration (validated by caller)
            credentials: {"token": str} - single account only (use RuntimeManager for multi-account)
            event_callback: Optional callback for structured events
            fatal_callback: Optional; called with a reason when the connection watchdog could not
                recover the client by reconnecting. A worker process exits here so the Cloud restarts it.
        """
        self.instance_id = instance_id
        self.preset_name = preset_name
        self.preset_data = copy.deepcopy(preset_data)
        self.credentials = copy.deepcopy(credentials)
        self.event_callback = event_callback

        self._state = InstanceState.STOPPED
        self._state_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client = None
        self._client_lock = threading.Lock()
        self._client_loop = None  # Track event loop separately
        self._root_task = None
        self._error: Optional[str] = None
        self._restart_required: List[str] = []
        self._applied_preset_changes: List[str] = []
        self._pending_preset_request_id = 0
        self._preset_outcomes: Dict[int, Dict[str, Any]] = {}  # Track apply outcomes
        self._requested_presets: Dict[int, Dict[str, Any]] = {}

        # Single token only - multi-account handled by manager
        if set(credentials) != {"token"} or not isinstance(credentials["token"], str) or not credentials["token"].strip():
            raise ValueError("single-account credentials must contain only a nonempty 'token' string")
        token = credentials["token"].strip()
        self.credentials["token"] = token

        # Build known secrets set for comprehensive redaction
        self._known_secrets = {token}
        self._activity_classifier = ActivityClassifier()
        self._watchdog_tripped = False
        self._watchdog = None
        settings = preset_data.get("_runtime_watchdog", True)
        if settings is not False:
            self._watchdog = ConnectionWatchdog(
                self, fatal=fatal_callback, **(settings if isinstance(settings, dict) else {}))

        self.preset_data["token"] = token
        self.preset_data["_runtime_mode"] = True  # Signal to avoid desktop fallbacks
        self.preset_data["_live_preset_push_only"] = True  # No file polling
        self.preset_data["_runtime_instance_id"] = instance_id  # Unique correlation

    @property
    def state(self) -> InstanceState:
        with self._state_lock:
            return self._state

    @property
    def error(self) -> Optional[str]:
        with self._state_lock:
            return _redact_credentials(self._error, self._known_secrets) if self._error else None

    @property
    def restart_required(self) -> List[str]:
        with self._state_lock:
            return list(self._restart_required)

    def _set_state(self, new_state: InstanceState, error: Optional[str] = None):
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if error:
                self._error = error
            elif new_state != InstanceState.FAILED:
                self._error = None

        if old_state != new_state:
            self._emit_event("state_change", {
                "old_state": old_state.value,
                "new_state": new_state.value,
                "error": error,
            })

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        if self.event_callback:
            try:
                # Redact credentials before emitting
                safe_data = _redact_credentials(data, self._known_secrets)
                event = InstanceEvent(
                    instance_id=self.instance_id,
                    timestamp=datetime.utcnow(),
                    event_type=event_type,
                    data=safe_data,
                )
                self.event_callback(event)
            except Exception as e:
                # Callback exceptions must not crash the instance
                print(f"[{self.instance_id}] Event callback error: {e}")

    def start(self, block: bool = False) -> bool:
        """
        Start the bot instance.

        Args:
            block: If True, wait until connected (or failed)

        Returns:
            True if started successfully, False if already running
        """
        with self._state_lock:
            if self._state in (InstanceState.STARTING, InstanceState.RUNNING, InstanceState.STOPPING):
                return False
            if self._thread and self._thread.is_alive():
                return False
            old_state = self._state
            self._state = InstanceState.STARTING
            self._stop_event.clear()
            self._error = None
            self._thread = threading.Thread(
                target=self._run_lifecycle,
                name=f"BotInstance-{self.instance_id}", daemon=False,
            )
            self._thread.start()
        if self._watchdog is not None:
            self._watchdog.start()

        self._emit_event("state_change", {
            "old_state": old_state.value,
            "new_state": InstanceState.STARTING.value,
        })

        if block:
            # Wait for RUNNING or FAILED
            timeout = 30.0
            deadline = time.time() + timeout
            while time.time() < deadline:
                state = self.state
                if state in (InstanceState.RUNNING, InstanceState.FAILED):
                    return state == InstanceState.RUNNING
                time.sleep(0.1)
            return False

        return True

    def stop(self, timeout: float = 12.0) -> bool:
        """
        Stop the bot instance gracefully.

        Args:
            timeout: Maximum seconds to wait for shutdown

        Returns:
            True if stopped cleanly, False if timed out
        """
        with self._state_lock:
            thread = self._thread
            if thread is threading.current_thread() and self._state == InstanceState.STOPPED:
                return False  # Terminal callback: worker has not returned yet.
            if self._state == InstanceState.STOPPED and not (thread and thread.is_alive()):
                return True
            transition = self._state != InstanceState.STOPPING
            if transition:
                old_state = self._state
                self._state = InstanceState.STOPPING
            self._stop_event.set()
        if self._watchdog is not None:
            self._watchdog.stop()

        if transition:
            self._emit_event("state_change", {
                "old_state": old_state.value,
                "new_state": InstanceState.STOPPING.value,
            })

        # Signal client shutdown if it exists
        with self._client_lock:
            client = self._client
            loop = self._client_loop
            reload = getattr(client, "_preset_reload", None) if client else None

        if client and loop:
            try:
                if not loop.is_closed() and reload is not None:
                    loop.call_soon_threadsafe(reload.cancel_pending)
                with self._client_lock:
                    root_task = self._root_task
                if not loop.is_closed() and root_task is not None:
                    loop.call_soon_threadsafe(root_task.cancel)
            except Exception:
                pass

        # Wait for thread completion
        if thread and thread.is_alive():
            if thread is threading.current_thread():
                return False
            thread.join(max(0, timeout))
            if thread.is_alive():
                return False

        self._set_state(InstanceState.STOPPED)
        return True

    # ---- hooks for the connection watchdog (see watchdog.py) --------------------------------
    def watch_target(self):
        with self._client_lock:
            return self._client, self._client_loop

    def stopping(self) -> bool:
        return self._stop_event.is_set()

    def is_running(self) -> bool:
        return self.state == InstanceState.RUNNING

    def watchdog_event(self, event_type: str, reason: str, stage: str):
        if event_type == "watchdog_recovered":
            message = "Connection restored"
        elif stage == "hard":
            message = f"Discord connection could not be repaired ({reason}); restarting MudaRemote"
        else:
            message = f"Discord connection stalled ({reason}); reconnecting"
        self._emit_event(event_type, {"message": message, "reason": reason, "stage": stage})

    def soft_restart(self):
        """Ask the run loop to drop the current client and connect again (not counted as a crash)."""
        self._watchdog_tripped = True
        with self._client_lock:
            loop, task = self._client_loop, self._root_task
        try:
            if loop is not None and task is not None and not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)
        except Exception:
            pass

    def _on_preset_outcome(self, outcome: Dict[str, Any]):
        """Store and publish a redacted live preset request outcome."""
        safe_outcome = _redact_credentials(dict(outcome), self._known_secrets)
        request_id = safe_outcome.get("request_id")
        if request_id is not None:
            with self._state_lock:
                self._preset_outcomes[request_id] = safe_outcome
                terminal = safe_outcome.get("status") != "deferred"
                candidate = self._requested_presets.pop(request_id, None) if terminal else None
                if candidate is not None and safe_outcome.get("status") in ("applied", "restart_required"):
                    # Keep restart-only requested values for the next start, but
                    # never replace the running account's credential or hooks.
                    self.preset_data.update(candidate)
                if safe_outcome.get("status") == "restart_required":
                    self._restart_required = list(safe_outcome.get("restart_keys", []))
                elif safe_outcome.get("status") == "applied":
                    self._restart_required = []
        self._emit_event("preset_outcome", safe_outcome)

    def restart(self, timeout: float = 12.0) -> bool:
        """
        Restart the bot instance.

        Args:
            timeout: Maximum seconds to wait for shutdown before restart

        Returns:
            True if restarted successfully
        """
        if not self.stop(timeout):
            return False
        time.sleep(1.0)  # Brief pause between stop and start
        return self.start(block=True)

    def apply_preset(self, preset_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply new preset settings to running instance.

        Args:
            preset_data: New configuration (validated by caller)

        Returns:
            {
                "status": "queued" | "inactive" | "invalid",
                "request_id": int,  # Unique request ID for outcome correlation
                "restart_required": List[str],  # Keys requiring restart
                "errors": List[str],  # Validation errors if any
            }
        """
        from .preset_reload import validate_live_preset, RESTART_ONLY_KEYS, normalize_preset

        errors = validate_live_preset(preset_data)
        if errors:
            return {
                "status": "invalid",
                "request_id": None,
                "restart_required": [],
                "errors": errors,
            }

        with self._client_lock:
            if not self._client or self.state != InstanceState.RUNNING:
                return {
                    "status": "inactive",
                    "request_id": None,
                    "restart_required": [],
                    "errors": [],
                }

            reload = getattr(self._client, "_preset_reload", None)
            loop = getattr(self._client, "loop", None)
            if not reload or not loop or loop.is_closed():
                return {
                    "status": "inactive",
                    "request_id": None,
                    "restart_required": [],
                    "errors": [],
                }

            # Generate unique request ID for this apply
            with self._state_lock:
                self._pending_preset_request_id += 1
                request_id = self._pending_preset_request_id

            candidate_data = copy.deepcopy(preset_data)
            with self._state_lock:
                self._requested_presets[request_id] = {
                    key: value for key, value in candidate_data.items()
                    if key not in ("token", "tokens", "additional_tokens") and not key.startswith("_")
                }
            try:
                loop.call_soon_threadsafe(reload.offer, candidate_data, request_id)
            except RuntimeError:
                with self._state_lock:
                    self._requested_presets.pop(request_id, None)
                return {
                    "status": "inactive",
                    "request_id": None,
                    "restart_required": [],
                    "errors": [],
                }

            # Calculate restart-required keys
            candidate = normalize_preset(preset_data)
            initial = normalize_preset(self.preset_data)
            restart_keys = sorted(
                key for key in RESTART_ONLY_KEYS
                if candidate.get(key) != initial.get(key)
            )

            with self._state_lock:
                self._restart_required = restart_keys

            return {
                "status": "queued",
                "request_id": request_id,
                "restart_required": restart_keys,
                "errors": [],
            }

    def get_status(self) -> Dict[str, Any]:
        """
        Get current instance status.

        Returns:
            {
                "instance_id": str,
                "preset_name": str,
                "state": str,
                "error": Optional[str],  # Redacted
                "restart_required": List[str],
                "active_preset": Dict,  # Currently applied preset (immutable snapshot)
                "desired_preset": Dict,  # Latest requested preset (immutable snapshot)
            }
        """
        with self._client_lock:
            reload = getattr(self._client, "_preset_reload", None) if self._client else None
            active = _redact_credentials(copy.deepcopy(reload.active_preset), self._known_secrets) if reload else {}
            desired = _redact_credentials(copy.deepcopy(reload.desired_preset), self._known_secrets) if reload else {}

        with self._state_lock:
            return {
                "instance_id": self.instance_id,
                "preset_name": self.preset_name,
                "state": (InstanceState.STOPPING.value if self._state == InstanceState.STOPPED
                          and self._thread and self._thread.is_alive() else self._state.value),
                "error": _redact_credentials(self._error, self._known_secrets) if self._error else None,
                "restart_required": list(self._restart_required),
                "active_preset": active,
                "desired_preset": desired,
            }

    def _run_lifecycle(self):
        try:
            self._run_lifecycle_inner()
        finally:
            if self._watchdog is not None:
                self._watchdog.stop()

    def _run_lifecycle_inner(self):
        """Thread entry point: run bot with proper retry logic."""
        from .config import validate_preset

        # Import mudae_bot only in runtime thread
        try:
            import mudae_bot
        except ImportError as e:
            self._set_state(InstanceState.FAILED, f"Failed to import mudae_bot: {e}")
            return

        # Validate preset before entering retry loop
        validation_errors = validate_preset(
            self.preset_data,
            resolved_token=self.preset_data.get("token"),
        )
        if validation_errors:
            error_msg = "Preset validation failed: " + " | ".join(validation_errors)
            self._set_state(InstanceState.FAILED, error_msg)
            self._emit_event("error", {"message": error_msg, "fatal": True})
            return

        retry_count = 0
        self._ready_at = None
        try:
            max_retries = max(1, int(self.preset_data.get("_runtime_max_retries", 10)))
        except (TypeError, ValueError):
            max_retries = 10
        try:
            retry_delay = max(0.0, float(self.preset_data.get("_runtime_retry_delay", 60)))
        except (TypeError, ValueError):
            retry_delay = 60.0

        while not self._stop_event.is_set() and retry_count < max_retries:
            try:
                # Create event logging wrapper that redacts credentials BEFORE logging
                def log_wrapper(message, preset_name, level):
                    # Redact credentials from message before any logging
                    safe_message = _redact_credentials(message, self._known_secrets)
                    self._emit_event("log", {
                        "message": safe_message,
                        "preset_name": preset_name,
                        "level": level,
                    })

                    # Emit structured events for the moments a user cares about (see activity_events)
                    if level == "ERROR":
                        self._emit_event("error", {
                            "message": safe_message,
                            "fatal": False,
                        })
                    else:
                        for event_type, event_data in self._activity_classifier.classify(level, safe_message):
                            self._emit_event(event_type, event_data)

                def on_client_ready(client):
                    """Called by run_bot when client is ready."""
                    with self._client_lock:
                        if self._client is None:
                            self._client = client
                            self._client_loop = getattr(client, "loop", None)
                    self._ready_at = time.monotonic()
                    if not self._stop_event.is_set():
                        self._set_state(InstanceState.RUNNING)

                def on_client_created(client):
                    """Own the client as soon as run_bot registers it."""
                    with self._client_lock:
                        self._client = client

                def execute_client(client, token):
                    """Run this client on a loop owned and cancellable by the instance."""
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    task = loop.create_task(client.start(token))
                    with self._client_lock:
                        self._client = client
                        self._client_loop = loop
                        self._root_task = task
                    if self._stop_event.is_set():
                        task.cancel()
                    try:
                        try:
                            loop.run_until_complete(task)
                        except asyncio.CancelledError:
                            pass
                    finally:
                        async def cleanup():
                            client._runtime_stopping = True
                            for event_name in ("_runtime_state_event", "_immediate_check_event"):
                                event = getattr(client, event_name, None)
                                if event is not None:
                                    event.set()
                            reload = getattr(client, "_preset_reload", None)
                            if reload is not None:
                                reload.cancel_pending()
                            if not client.is_closed():
                                await client.close()
                            # Client.start can spawn health, loot and scheduled
                            # tasks which are not children of the start task.
                            while True:
                                pending = [t for t in asyncio.all_tasks(loop)
                                           if t is not asyncio.current_task() and not t.done()]
                                if not pending:
                                    break
                                for pending_task in pending:
                                    pending_task.cancel()
                                await asyncio.gather(*pending, return_exceptions=True)
                            await loop.shutdown_asyncgens()
                            shutdown_executor = getattr(loop, "shutdown_default_executor", None)
                            if shutdown_executor is not None:
                                await shutdown_executor()

                        try:
                            loop.run_until_complete(cleanup())
                        finally:
                            with self._client_lock:
                                if self._client is client:
                                    self._client = None
                                    self._client_loop = None
                                    self._root_task = None
                            loop.close()
                            asyncio.set_event_loop(None)
                    return not self._stop_event.is_set()

                # Install callback in preset_data
                self.preset_data["_runtime_client_created_callback"] = on_client_created
                self.preset_data["_runtime_ready_callback"] = on_client_ready
                self.preset_data["_runtime_execution_hook"] = execute_client
                self.preset_data["_runtime_instance_id"] = self.instance_id
                self.preset_data["_preset_outcome_observer"] = self._on_preset_outcome

                # Run the bot (blocks until disconnect/error)
                mudae_bot.run_bot(
                    self.preset_name,
                    self.preset_data,
                    log_function=log_wrapper,
                )

                if self._stop_event.is_set():
                    break
                # Test doubles and alternate launchers may return after
                # publishing readiness; the concrete runtime hook classifies
                # an unexpected client return before reaching this point.
                if self._stop_event.wait(5):
                    break

            except Exception as e:
                # Cancellation from an intentional stop is a normal exit.
                if self._stop_event.is_set():
                    break
                if self._watchdog_tripped:
                    # The watchdog dropped a dead connection on purpose: reconnect quickly, no crash.
                    self._watchdog_tripped = False
                    self._ready_at = None
                    self._set_state(InstanceState.STARTING)
                    if self._stop_event.wait(min(5.0, retry_delay)):
                        break
                    continue
                error_msg = f"Instance crashed: {e}"

                # Check for login failure (don't retry)
                try:
                    import discord
                    if isinstance(e, getattr(discord, "LoginFailure", ())):
                        self._set_state(
                            InstanceState.FAILED,
                            "Discord rejected token (401 Unauthorized)"
                        )
                        self._emit_event("error", {
                            "message": "Discord rejected token (401 Unauthorized)",
                            "fatal": True,
                        })
                        return
                except ImportError:
                    pass

                try:
                    stable = max(0.0, float(self.preset_data.get("_runtime_retry_reset_seconds", 600)))
                except (TypeError, ValueError):
                    stable = 600.0
                if self._ready_at is not None and time.monotonic() - self._ready_at >= stable:
                    retry_count = 0     # it ran fine for a long time: only failures in a row count
                self._ready_at = None
                retry_count += 1
                safe_error_msg = _redact_credentials(error_msg, self._known_secrets)
                self._emit_event("error", {
                    "message": safe_error_msg,
                    "traceback": str(traceback.format_exc()),
                    "fatal": False,
                    "retry_count": retry_count,
                })

                if retry_count >= max_retries:
                    self._set_state(InstanceState.FAILED, f"Max retries exceeded: {safe_error_msg}")
                    return

                # Do not leave a previously-ready instance reported as running
                # while its next connection attempt is pending.
                self._set_state(InstanceState.STARTING)
                if self._stop_event.wait(retry_delay):
                    break

        # Clean shutdown
        if self._watchdog is not None:
            self._watchdog.stop()
        if self.state not in (InstanceState.FAILED, InstanceState.STOPPED):
            self._set_state(InstanceState.STOPPED)


class RuntimeManager:
    """
    Multi-instance runtime coordinator.

    Manages multiple BotInstance objects with unified event handling and lifecycle control.
    Note: Each BotInstance runs a single Discord account. For multi-account support,
    use start_instances_from_preset() which expands tokens into separate instances.
    """

    def __init__(
        self,
        event_callback: Optional[Callable[[InstanceEvent], None]] = None,
        fatal_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize runtime manager.

        Args:
            event_callback: Optional callback for all instance events
            fatal_callback: Optional; see BotInstance. A host that can restart its own process passes one.
        """
        self.event_callback = event_callback
        self.fatal_callback = fatal_callback
        self._instances: Dict[str, BotInstance] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        self._starting_ids = set()

    def start_instance(
        self,
        preset_name: str,
        preset_data: Dict[str, Any],
        credentials: Dict[str, Any],
        instance_id: Optional[str] = None,
        block: bool = False,
    ) -> str:
        """
        Start a new bot instance (single account).

        Args:
            preset_name: Display name
            preset_data: Bot configuration (validated by caller)
            credentials: {"token": str} - single token only
            instance_id: Optional custom ID (auto-generated if None)
            block: Wait for connection before returning

        Returns:
            instance_id of started instance

        Raises:
            ValueError: If instance_id already exists or credentials invalid
        """
        with self._lock:
            if instance_id is None:
                instance_id = f"instance-{self._next_id}"
                self._next_id += 1
            if instance_id in self._instances:
                raise ValueError(f"Instance {instance_id} already exists")

            instance = BotInstance(
                instance_id=instance_id,
                preset_name=preset_name,
                preset_data=preset_data,
                credentials=credentials,
                event_callback=self.event_callback,
                fatal_callback=self.fatal_callback,
            )
            self._instances[instance_id] = instance
            self._starting_ids.add(instance_id)

        try:
            if not instance.start(block=block):
                raise RuntimeError(f"Failed to start instance {instance_id}")
        except Exception:
            with self._lock:
                self._starting_ids.discard(instance_id)
                current = self._instances.get(instance_id)
                thread = instance._thread
                if current is instance and not (thread and thread.is_alive()):
                    del self._instances[instance_id]
            raise
        finally:
            with self._lock:
                self._starting_ids.discard(instance_id)
        return instance_id

    def start_instances_from_preset(
        self,
        preset_name: str,
        preset_data: Dict[str, Any],
        credentials: Dict[str, Any],
        block: bool = False,
    ) -> List[str]:
        """
        Start multiple instances from a preset with multiple tokens.

        Args:
            preset_name: Base display name
            preset_data: Bot configuration
            credentials: {"token": str} or {"tokens": List[str]}
            block: Wait for all connections

        Returns:
            List of instance_ids created
        """
        if not isinstance(credentials, dict) or not credentials or set(credentials) - {"token", "tokens"}:
            raise ValueError("credentials must contain only 'token' or 'tokens'")
        if "tokens" in credentials:
            if "token" in credentials or not isinstance(credentials["tokens"], (list, tuple)):
                raise ValueError("provide either 'token' or a 'tokens' list, not both")
            tokens = credentials["tokens"]
        else:
            tokens = [credentials.get("token")]
        if not tokens or any(not isinstance(t, str) or not t.strip() for t in tokens):
            raise ValueError("credentials must contain nonempty token strings")
        tokens = [t.strip() for t in tokens]
        if len(set(tokens)) != len(tokens):
            raise ValueError("duplicate account tokens are not allowed")

        from .runtime import active_stagger_seconds
        with self._lock:
            if any(f"{preset_name.replace(' ', '-')}-{idx}" in self._instances
                   for idx in range(1, len(tokens) + 1)):
                raise ValueError("an account instance ID already exists")
            start_index = len(self._instances)

        # Create one instance per token
        instance_ids = []
        for idx, token in enumerate(tokens, 1):
            account_name = preset_name if idx == 1 else f"{preset_name} #{idx}"
            instance_id = self.start_instance(
                preset_name=account_name,
                preset_data={**copy.deepcopy(preset_data), "_source_preset_name": preset_name,
                             "persistent_stagger_seconds": active_stagger_seconds(start_index + idx - 1)},
                credentials={"token": token},
                instance_id=f"{preset_name.replace(' ', '-')}-{idx}",
                block=block,
            )
            instance_ids.append(instance_id)

        return instance_ids

    def stop_instance(self, instance_id: str, timeout: float = 12.0) -> bool:
        """
        Stop a running instance.

        Args:
            instance_id: Instance to stop
            timeout: Shutdown timeout in seconds

        Returns:
            True if stopped cleanly

        Raises:
            KeyError: If instance_id not found
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                raise KeyError(f"Instance {instance_id} not found")

        return instance.stop(timeout)

    def restart_instance(self, instance_id: str, timeout: float = 12.0) -> bool:
        """
        Restart an instance.

        Args:
            instance_id: Instance to restart
            timeout: Shutdown timeout in seconds

        Returns:
            True if restarted successfully

        Raises:
            KeyError: If instance_id not found
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                raise KeyError(f"Instance {instance_id} not found")

        return instance.restart(timeout)

    def apply_preset(
        self,
        instance_id: str,
        preset_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply new settings to a running instance.

        Args:
            instance_id: Target instance
            preset_data: New configuration

        Returns:
            {"status": str, "restart_required": List[str], "errors": List[str]}

        Raises:
            KeyError: If instance_id not found
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                raise KeyError(f"Instance {instance_id} not found")

        return instance.apply_preset(preset_data)

    def get_status(self, instance_id: str) -> Dict[str, Any]:
        """
        Get instance status.

        Args:
            instance_id: Instance to query

        Returns:
            Status dictionary

        Raises:
            KeyError: If instance_id not found
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                raise KeyError(f"Instance {instance_id} not found")

        return instance.get_status()

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all instances."""
        with self._lock:
            return {
                iid: instance.get_status()
                for iid, instance in self._instances.items()
            }

    def remove_instance(self, instance_id: str) -> bool:
        """
        Remove a stopped instance from the manager.

        Args:
            instance_id: Instance to remove

        Returns:
            True if removed, False if not stopped

        Raises:
            KeyError: If instance_id not found
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                raise KeyError(f"Instance {instance_id} not found")

            if instance_id in self._starting_ids:
                return False

            if instance.state != InstanceState.STOPPED or (instance._thread and instance._thread.is_alive()):
                return False

            del self._instances[instance_id]
            return True

    def shutdown_all(self, timeout: float = 12.0):
        """
        Stop all instances gracefully.

        Args:
            timeout: Per-instance shutdown timeout
        """
        with self._lock:
            instances = list(self._instances.values())

        for instance in instances:
            instance.stop(timeout)

    def list_instances(self) -> List[str]:
        """Get list of all instance IDs."""
        with self._lock:
            return list(self._instances.keys())
