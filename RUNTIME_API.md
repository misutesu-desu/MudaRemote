# Runtime API

`mudae_core.bot_runtime.RuntimeManager` manages bot instances in the current
Python process. It is not a cloud service or a persistence layer. Validate
`preset_data` before calling it and keep credentials outside the preset.

## Start

```python
instance_id = manager.start_instance(
    preset_name, preset_data, {"token": token}, instance_id=None, block=False
)
```

`start_instance` owns one account and returns its ID. `credentials` must contain
one non-empty `token`. With `block=True`, startup waits up to 30 seconds for
`RUNNING` or `FAILED`, but the method still returns the ID when the wait times
out or startup fails; inspect `get_status(instance_id)`.

Transient runtime exceptions retry up to `_runtime_max_retries` (default 10),
waiting `_runtime_retry_delay` seconds between attempts (default 60). Invalid
presets and Discord token rejection are terminal `FAILED` states and are not
retried. An intentional stop interrupts the retry wait and reports `STOPPED`.

For multiple accounts, use:

```python
ids = manager.start_instances_from_preset(
    preset_name, preset_data, {"tokens": [token_a, token_b]}, block=False
)
```

This expands one instance per token and returns their IDs. A singular `token`
is also accepted by this helper. Do not pass `tokens` to `start_instance`.

## Lifecycle

- `stop_instance(id, timeout=12.0) -> bool`: `True` means the worker stopped
  within the timeout; `False` means it may still be stopping.
- Stop sets the worker stop signal, cancels its root event-loop task, and
  cancels queued preset outcomes. A timeout is bounded by the caller and may
  leave the instance in `STOPPING`; later status checks determine completion.
- `restart_instance(id, timeout=12.0) -> bool`: stops, waits one second, then
  starts with `block=True`; a failed stop does not start a replacement.
- `shutdown_all(timeout=12.0)`: applies the timeout to each instance.
- `get_status(id)`, `get_all_statuses()`, `list_instances()`, and
  `remove_instance(id)` expose status/list management. Removal only succeeds
  for a stopped instance.

## Live apply and callbacks

`apply_preset(id, preset_data)` validates and queues a live update. The immediate
result is:

```python
{"status": "queued" | "inactive" | "invalid",
 "request_id": int | None,
 "restart_required": list[str], "errors": list[str]}
```

`queued` means accepted, not applied. `request_id` correlates the later
`preset_outcome` event. Construct the manager with
`RuntimeManager(event_callback=callback)`; the callback receives
`InstanceEvent(instance_id, timestamp, event_type, data)`. A preset outcome can
be `applied`, `restart_required`, `deferred`, `rejected`, `superseded`, or
`cancelled`, with `changed_keys`/`restart_keys` where applicable. Callbacks run
on runtime/event-loop threads. There is no built-in outcome wait or timeout;
implement any host-side deadline around the callback correlation.

Restart-only keys are reported rather than silently changed live. The definitive
list is `mudae_core.preset_reload.RESTART_ONLY_KEYS`; the current set includes
channel, command-channel, claim/roll timing, rolling, loot lifecycle, and
startup settings. Credential changes require a new start/restart.

## Example

See [examples/runtime_api_examples.py](examples/runtime_api_examples.py) for
minimal single-account and multi-account examples. They require project
dependencies and real Discord credentials; they are not offline tests.
