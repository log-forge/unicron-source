"""Inventory-centric Socket.IO event handlers for the Herald client."""

import socketio

from .inventory import register_inventory_refresh_events

__all__ = ["register_inventory_events"]


def register_inventory_events(sio: socketio.AsyncClient) -> None:
    """Register inventory-related events on the provided AsyncClient."""

    register_inventory_refresh_events(sio)
