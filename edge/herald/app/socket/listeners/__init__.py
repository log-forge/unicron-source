"""Client-side Socket.IO event registry for Herald.

Provides a single entrypoint to register all event handlers on the
singleton AsyncClient. Split handlers into modules and call their
`register_*` functions here so adding new event groups is simple.
"""

import socketio

from .container_actions import register_container_action_events
from .control import register_control_events
from .inventory import register_inventory_events


def register_all_events(sio: socketio.AsyncClient) -> None:
    """Register all client-side event handlers on the given AsyncClient.

    Add new groups by importing and invoking their register functions here.
    """
    register_control_events(sio)
    register_inventory_events(sio)
    register_container_action_events(sio)
