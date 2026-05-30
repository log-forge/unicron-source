import unittest
from types import SimpleNamespace

from app.utils.socket_io_utils import get_room_participants


class SocketIoUtilsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_room_participants_normalizes_sid_tuples(self) -> None:
        manager = SimpleNamespace(get_participants=lambda namespace, room: [("sid-a", "eio-a")])
        sio = SimpleNamespace(manager=manager)

        participants = await get_room_participants(sio, "room:global")

        self.assertEqual(participants, {"sid-a"})


if __name__ == "__main__":
    unittest.main()
