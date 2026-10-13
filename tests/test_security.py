import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'SparkAgentServer'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security import authorized, validate_tokens, install_http_auth, authenticate_device


class SecurityTests(unittest.TestCase):
    def test_http_requests_require_the_correct_bearer_token(self):
        app=FastAPI();install_http_auth(app,'a'*32)
        @app.post('/api/move')
        def move(): return {'ok':True}
        with TestClient(app) as client:
            self.assertEqual(client.get('/docs').status_code,401)
            self.assertEqual(client.get('/openapi.json').status_code,401)
            self.assertEqual(client.post('/api/move').status_code,401)
            self.assertEqual(client.post('/api/move',headers={'Authorization':'Bearer '+'b'*32}).status_code,401)
            self.assertEqual(client.post('/api/move',headers={'Authorization':'Bearer '+'a'*32}).status_code,200)

    def test_missing_configuration_never_accepts_empty_credentials(self):
        self.assertFalse(authorized('Bearer ',''))
        for api,device in [('', ''), ('a'*32,'a'*32), ('a\n'*32,'b'*32)]:
            with self.assertRaises(ValueError): validate_tokens(api,device)
        validate_tokens('a'*32,'b'*32)
        with self.assertRaises(ValueError): validate_tokens('中'*32,'b'*32)

    def test_device_auth_rejects_before_using_connection(self):
        ws=types.SimpleNamespace(request=types.SimpleNamespace(headers={}),close=AsyncMock())
        self.assertFalse(asyncio.run(authenticate_device(ws,'b'*32)))
        ws.close.assert_awaited_once()
        ws.request.headers={'Authorization':'Bearer '+'b'*32};ws.close.reset_mock()
        self.assertTrue(asyncio.run(authenticate_device(ws,'b'*32)))
        ws.close.assert_not_awaited()

    def test_real_websocket_accepts_only_the_device_token(self):
        async def check():
            async def handler(ws):
                if await authenticate_device(ws,'d'*32):
                    await ws.send('authenticated')
            async with serve(handler,'127.0.0.1',0) as server:
                port=server.sockets[0].getsockname()[1]
                for token in [None,'a'*32,'d'*32]:
                    headers={} if token is None else {'Authorization':'Bearer '+token}
                    async with connect(f'ws://127.0.0.1:{port}',additional_headers=headers) as ws:
                        if token == 'd'*32:
                            self.assertEqual(await ws.recv(),'authenticated')
                        else:
                            with self.assertRaises(ConnectionClosedError) as error:
                                await ws.recv()
                            self.assertEqual(error.exception.rcvd.code,1008)
        asyncio.run(check())
