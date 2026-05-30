"""Control-channel event grouping for the Herald Socket.IO client.""" """Control-channel event grouping for the Herald Socket.IO client.

This package exposes a single `register_control_events` entrypoint that
aggregates the sub-groups of control channel handlers. New event groups
can be added by creating sibling modules with their own
`register_*_events` helper and importing them here.
"""

import socketio

from .base import register_base_control_events

__all__ = ["register_control_events"]


def register_control_events(sio: socketio.AsyncClient) -> None:
    """Register all control-channel events on the provided AsyncClient."""

    register_base_control_events(sio)
