"""Connecting to a multiworld server over ``ws://`` and ``wss://``.

The client rides on Archipelago's ``CommonClient.server_loop`` (the BizHawk client context is built on it), which
decides the transport from the address. These tests connect the very context class this world's client uses to local
servers, so a change in Archipelago that breaks either transport is noticed here. Certificates are generated on the
fly with the ``openssl`` command line tool (the TLS tests are skipped where it is unavailable).
"""
import asyncio
import contextlib
import os
import shutil
import ssl
import subprocess
import tempfile
import unittest
from unittest import mock

import CommonClient
import websockets
from worlds._bizhawk.context import BizHawkClientContext

HAVE_OPENSSL = shutil.which("openssl") is not None


@contextlib.asynccontextmanager
async def serve(tls: ssl.SSLContext | None = None):
    """A local server that accepts one connection, notes it, and hangs up. Yields (port, connected_event)."""
    connected = asyncio.Event()

    async def handler(websocket):
        connected.set()
        await asyncio.sleep(0.05)  # give the client time to register the connection before it is closed

    async with websockets.serve(handler, "127.0.0.1", 0, ssl=tls) as server:
        yield server.sockets[0].getsockname()[1], connected


async def connect(address: str, trusted: ssl.SSLContext | None = None) -> BizHawkClientContext:
    """Run the client's connection logic against ``address`` until the server hangs up."""
    context = BizHawkClientContext(None, None)
    trust = trusted or ssl.create_default_context()
    with mock.patch.object(CommonClient, "get_ssl_context", return_value=trust):
        await asyncio.wait_for(CommonClient.server_loop(context, address), 15)
    return context


class TestPlainConnections(unittest.IsolatedAsyncioTestCase):
    async def test_a_bare_host_and_port_connects_over_ws(self):
        async with serve() as (port, connected):
            context = await connect(f"127.0.0.1:{port}")
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"ws://127.0.0.1:{port}")

    async def test_an_explicit_ws_address_connects(self):
        async with serve() as (port, connected):
            context = await connect(f"ws://127.0.0.1:{port}")
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"ws://127.0.0.1:{port}")

    async def test_archipelago_links_are_plain_ws(self):
        async with serve() as (port, connected):
            context = await connect(f"archipelago://127.0.0.1:{port}")
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"ws://127.0.0.1:{port}")

    async def test_credentials_in_the_address_are_used(self):
        async with serve() as (port, _):
            context = await connect(f"ws://Ash:secret@127.0.0.1:{port}")
        self.assertEqual((context.username, context.password), ("Ash", "secret"))

    async def test_wss_against_a_plain_server_fails_cleanly(self):
        async with serve() as (port, connected):
            context = await connect(f"wss://127.0.0.1:{port}")
            self.assertFalse(connected.is_set())
        self.assertIsNone(context.server_address)

    async def test_an_unreachable_server_fails_cleanly(self):
        async with serve() as (port, _):
            pass  # the port is now closed again
        context = await connect(f"ws://127.0.0.1:{port}")
        self.assertIsNone(context.server_address)


@unittest.skipUnless(HAVE_OPENSSL, "the openssl command line tool is needed to create a test certificate")
class TestSecureConnections(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        key, cert = os.path.join(cls.folder.name, "key.pem"), os.path.join(cls.folder.name, "cert.pem")
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert, "-days", "1",
             "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
            check=True, capture_output=True,
        )
        cls.server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server_tls.load_cert_chain(cert, key)
        cls.client_trusts_cert = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cert)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    async def test_an_explicit_wss_address_connects(self):
        async with serve(self.server_tls) as (port, connected):
            context = await connect(f"wss://127.0.0.1:{port}", self.client_trusts_cert)
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"wss://127.0.0.1:{port}")

    async def test_a_bare_address_falls_back_to_wss_when_the_server_speaks_tls(self):
        async with serve(self.server_tls) as (port, connected):
            context = await connect(f"127.0.0.1:{port}", self.client_trusts_cert)
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"wss://127.0.0.1:{port}")

    async def test_an_explicit_ws_address_to_a_tls_server_also_falls_back(self):
        async with serve(self.server_tls) as (port, connected):
            context = await connect(f"ws://127.0.0.1:{port}", self.client_trusts_cert)
            self.assertTrue(connected.is_set())
        self.assertEqual(context.server_address, f"wss://127.0.0.1:{port}")

    async def test_certificates_are_verified_not_ignored(self):
        """An untrusted (here: self-signed) certificate must be rejected rather than silently accepted."""
        async with serve(self.server_tls) as (port, connected):
            context = await connect(f"wss://127.0.0.1:{port}")  # default trust store does not know the test cert
            self.assertFalse(connected.is_set())
        self.assertIsNone(context.server_address)
