import inspect

import socketio


def _participant_sid(participant: object) -> str | None:
    if isinstance(participant, str):
        return participant
    if isinstance(participant, tuple) and participant and isinstance(participant[0], str):
        return participant[0]
    if isinstance(participant, list) and participant and isinstance(participant[0], str):
        return participant[0]
    return None


def _normalize_participants(participants: set[str], values) -> None:
    for participant in values:
        sid = _participant_sid(participant)
        if sid is not None:
            participants.add(sid)


async def get_room_participants(
    sio: socketio.AsyncServer,
    room: str,
    *,
    namespace: str = "/",
) -> set[str]:
    """Return the set of Socket.IO sids currently in a room.

    Works with both the default in-memory manager and AsyncRedisManager.
    """
    mgr = getattr(sio, "manager", None)
    if mgr is None:
        return set()

    getp = getattr(mgr, "get_participants", None)
    if getp is None:
        return set()

    res = getp(namespace, room)
    if inspect.isawaitable(res):
        res = await res

    try:
        participants: set[str] = set()
        _normalize_participants(participants, res)
        return participants
    except TypeError:
        participants: set[str] = set()
        try:
            async for participant in res:  # type: ignore[misc]
                sid = _participant_sid(participant)
                if sid is not None:
                    participants.add(sid)
        except TypeError:
            return set()
        return participants


async def disconnect_room(
    sio: socketio.AsyncServer,
    room: str,
    *,
    namespace: str = "/",
) -> int:
    """Disconnect all Socket.IO sessions currently in a room.

    Returns the number of sids attempted.
    """
    sids = await get_room_participants(sio, room, namespace=namespace)
    attempted = 0
    for sid in sids:
        attempted += 1
        try:
            await sio.disconnect(sid, namespace=namespace)
        except Exception:
            # Best-effort: disconnect should not break the caller flow.
            pass
    return attempted


__all__ = ["get_room_participants", "disconnect_room"]
