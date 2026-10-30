"""Setup failures must not leak real ASGI applications or hide transition errors."""

import asyncio

from django.test import SimpleTestCase

from asgiref.sync import async_to_sync

from .transition_socket_setup import connected_sockets


class SocketSetupTests(SimpleTestCase):
    def scenario(self, *, failing_connect=False, hanging=False, failing_body=False, failing_close=False):
        class Socket:
            connected = False
            closed = False

            def __init__(self, index):
                self.index = index

            async def connect(self, *, timeout):
                if timeout is not None:
                    raise AssertionError("Individual handshake must not cancel the application.")
                if self.index == 1:
                    if hanging:
                        await asyncio.Event().wait()
                    if failing_connect:
                        raise ValueError("admission failed")
                self.connected = True

            async def close(self):
                self.closed = True
                if failing_close and self.index == 0:
                    raise ValueError("cleanup failed")

        sockets = [Socket(i) for i in range(3)]

        async def run():
            async with connected_sockets(sockets, timeout=0.01 if hanging else 20):
                self.assertTrue(all(s.connected for s in sockets))
                if failing_body:
                    raise RuntimeError("transition failed")

        return sockets, run

    def test_all_sockets_are_ready_before_transition_and_closed_after(self):
        sockets, run = self.scenario()
        async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_partial_admission_failure_closes_every_socket(self):
        sockets, run = self.scenario(failing_connect=True)
        with self.assertRaisesMessage(ValueError, "admission failed"):
            async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_overall_setup_is_still_bounded(self):
        sockets, run = self.scenario(hanging=True)
        with self.assertRaises(TimeoutError):
            async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_transition_failure_still_closes_all_sockets(self):
        sockets, run = self.scenario(failing_body=True)
        with self.assertRaisesMessage(RuntimeError, "transition failed"):
            async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_cleanup_failure_is_not_hidden_on_success(self):
        sockets, run = self.scenario(failing_close=True)
        with self.assertRaisesMessage(ValueError, "cleanup failed"):
            async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_cleanup_does_not_mask_the_original_transition_failure(self):
        sockets, run = self.scenario(failing_body=True, failing_close=True)
        with self.assertRaisesMessage(RuntimeError, "transition failed"):
            async_to_sync(run)()
        self.assertTrue(all(s.closed for s in sockets))

    def test_reader_failure_still_disconnects_the_real_socket_wrapper(self):
        from .test_transition_scaling import _Socket

        async def run():
            class Communicator:
                disconnected = False
                future = asyncio.get_running_loop().create_future()

                async def disconnect(self):
                    self.disconnected = True
                    self.future.cancel()

            async def broken_reader():
                raise ValueError("reader failed")

            communicator = Communicator()
            socket = _Socket(communicator, reply_seen=False)
            socket.started = True
            socket.reader = asyncio.create_task(broken_reader())
            await asyncio.sleep(0)
            with self.assertRaisesMessage(ValueError, "reader failed"):
                await socket.close()
            self.assertTrue(communicator.disconnected)

        async_to_sync(run)()
