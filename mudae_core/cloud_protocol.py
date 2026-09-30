"""Canonical worker <-> Cloud API protocol.

This module is the single source of truth for identifiers, enumerations and
payload shapes exchanged on the two worker endpoints:

    POST {base}/poll    {"worker_id", "boot_id", "worker_version", "protocol_version"}
                        -> {"protocol_version", "commands": [Command, ...]}
    POST {base}/report  {"worker_id", "boot_id", "worker_version", "protocol_version",
                         "records": [Record, ...]}

Both are authenticated with ``Authorization: Bearer <worker token>``. The
token authenticates the *worker*; user authorization never crosses this
boundary, and the API re-derives every user/instance relationship from its own
database instead of trusting worker-supplied identifiers.

Command (API -> worker)
    command_id, user_id, instance_id, action, [revision],
    start:         preset_name, preset_data, credentials={"token"}
    preset_update: preset_data

Record (worker -> API), each carrying a unique ``record_id`` (idempotency key)
    command_result: command_id, user_id, instance_id, data={"success", "result"|"error"}
    event:          data={"record_id", "user_id", "instance_id", "event": InstanceEvent dict}
    health:         data={"closed", "instances": [{"user_id", "instance_id", "state", ...}]}
"""

PROTOCOL_VERSION = 1

ID_MAX_LENGTH = 200

ACTION_START = "start"
ACTION_STOP = "stop"
ACTION_RESTART = "restart"
ACTION_STATUS = "status"
ACTION_PRESET_UPDATE = "preset_update"
ACTIONS = frozenset({
    ACTION_START, ACTION_STOP, ACTION_RESTART, ACTION_STATUS, ACTION_PRESET_UPDATE,
})

COMMAND_PENDING = "pending"
COMMAND_RUNNING = "running"
COMMAND_SUCCEEDED = "succeeded"
COMMAND_FAILED = "failed"
COMMAND_STATES = (COMMAND_PENDING, COMMAND_RUNNING, COMMAND_SUCCEEDED, COMMAND_FAILED)
COMMAND_TERMINAL_STATES = frozenset({COMMAND_SUCCEEDED, COMMAND_FAILED})

# Mirrors mudae_core.bot_runtime.InstanceState values.
RUNTIME_STARTING = "starting"
RUNTIME_RUNNING = "running"
RUNTIME_STOPPING = "stopping"
RUNTIME_STOPPED = "stopped"
RUNTIME_FAILED = "failed"
RUNTIME_STATES = (
    RUNTIME_STARTING, RUNTIME_RUNNING, RUNTIME_STOPPING, RUNTIME_STOPPED, RUNTIME_FAILED,
)

RECORD_COMMAND_RESULT = "command_result"
RECORD_EVENT = "event"
RECORD_HEALTH = "health"
RECORD_TYPES = frozenset({RECORD_COMMAND_RESULT, RECORD_EVENT, RECORD_HEALTH})

# Stable machine-readable errors a worker may return in a failed result.
WORKER_ERRORS = frozenset({
    "invalid_command", "worker_stopped", "instance_not_found", "instance_limit",
    "command_id_conflict", "instance_exists", "instance_not_running",
    "runtime_unresponsive", "runtime_command_failed", "spawn_failed",
    "execution_failed",
})


def is_identifier(value):
    """True for a non-empty string identifier within the protocol length limit."""
    return isinstance(value, str) and 0 < len(value) <= ID_MAX_LENGTH


def command_problem(command):
    """Return a short reason if ``command`` is not a well-formed command, else None."""
    if not isinstance(command, dict):
        return "not an object"
    for key in ("command_id", "user_id", "instance_id", "action"):
        if not is_identifier(command.get(key)):
            return "invalid {}".format(key)
    if command["action"] not in ACTIONS:
        return "unsupported action"
    return None
