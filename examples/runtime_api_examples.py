"""Minimal RuntimeManager examples; credentials come from the environment."""

import os
import time

from mudae_core.bot_runtime import RuntimeManager


def make_preset():
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("Set DISCORD_CHANNEL_ID")
    return {
        "channel_id": channel_id,
        "prefix": "$",
        "mudae_prefix": "$",
        "roll_command": "wa",
        "rolling": True,
    }


def on_event(event):
    print(event.instance_id, event.event_type, event.data)


def single_account():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN")

    manager = RuntimeManager(event_callback=on_event)
    instance_id = manager.start_instance(
        "Example", make_preset(), {"token": token}, block=True
    )
    try:
        print("startup:", manager.get_status(instance_id))
        updated = make_preset()
        updated["min_kakera"] = 200
        print("apply accepted:", manager.apply_preset(instance_id, updated))
        # The matching preset_outcome event is asynchronous when queued.
        time.sleep(15)
    finally:
        print("stopped:", manager.stop_instance(instance_id, timeout=12.0))


def multiple_accounts():
    tokens = [os.environ.get(name) for name in (
        "DISCORD_TOKEN", "DISCORD_TOKEN_2", "DISCORD_TOKEN_3"
    )]
    tokens = [token for token in tokens if token]
    if not tokens:
        raise RuntimeError("Set at least DISCORD_TOKEN")

    manager = RuntimeManager(event_callback=on_event)
    ids = manager.start_instances_from_preset(
        "Example", make_preset(), {"tokens": tokens}, block=True
    )
    try:
        for instance_id in ids:
            print(instance_id, manager.get_status(instance_id))
        time.sleep(15)
    finally:
        manager.shutdown_all(timeout=12.0)


if __name__ == "__main__":
    single_account()
