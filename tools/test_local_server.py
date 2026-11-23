"""Synthetic HTTP integration checks; no Whisper model or personal files."""

import http.client
import json
import socket
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from local_server import Handler, LocalServer


WAV = b'RIFF\x24\x00\x00\x00WAVEfmt '


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, body=body, headers={'Host': f'127.0.0.1:{self.server.server_port}', **(headers or {})})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def auth(self, job_id=None):
        return {'X-Local-Token': self.server.token, 'Origin': self.origin,
                'X-Job-ID': job_id or str(uuid.uuid4()),
                'X-Media-Extension': '.wav', 'Content-Type': 'application/octet-stream'}

    def test_session_requires_same_origin_navigation(self):
        self.assertEqual(self.request('GET', '/api/session')[0], 403)
        self.assertEqual(self.request('GET', '/api/session', headers={'Referer': self.origin + '/index.html'})[0], 200)
        self.assertEqual(self.request('GET', '/api/session', headers={'Referer': self.origin + '/', 'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_rejects_foreign_host_origin_and_token(self):
        self.assertEqual(self.request('POST', '/api/transcribe', WAV, {**self.auth(), 'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/transcribe', WAV, {**self.auth(), 'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/transcribe', WAV, {**self.auth(), 'X-Local-Token': 'no'})[0], 403)

    def test_static_paths_are_allowlisted(self):
        self.assertEqual(self.request('GET', '/index.html')[0], 200)
        for path in ('/.git/config', '/README.md', '/tools/local_server.py', '/src/../README.md',
                     '/src/%2e%2e/README.md', '/src/%252e%252e/README.md', '/src/app.js/../../README.md'):
            with self.subTest(path=path):
                self.assertNotEqual(self.request('GET', path)[0], 200)

    def test_invalid_media_and_uuid(self):
        self.assertEqual(self.request('POST', '/api/transcribe', WAV, {**self.auth(), 'X-Job-ID': 'bad'})[0], 400)
        self.assertEqual(self.request('POST', '/api/transcribe', WAV, {**self.auth(), 'X-Media-Extension': '.exe'})[0], 413)
        self.assertEqual(self.request('POST', '/api/transcribe', b'not wave', self.auth())[0], 415)

    def test_incomplete_body_releases_slot(self):
        headers = self.auth()
        conn = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=5)
        try:
            payload = (f'POST /api/transcribe HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\n'
                       f'Origin: {self.origin}\r\nX-Local-Token: {headers["X-Local-Token"]}\r\n'
                       f'X-Job-ID: {headers["X-Job-ID"]}\r\nX-Media-Extension: .wav\r\n'
                       'Content-Length: 100\r\nConnection: close\r\n\r\n').encode() + WAV
            conn.sendall(payload)
            conn.shutdown(socket.SHUT_WR)
            response = conn.recv(4096)
            self.assertIn(b'400', response.split(b'\r\n', 1)[0])
        finally:
            conn.close()
        for _ in range(100):
            if self.server.active is None:
                break
            time.sleep(.01)
        self.assertIsNone(self.server.active)

    def test_server_close_signals_active_job(self):
        class FakeProcess:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        isolated = LocalServer(('127.0.0.1', 0), Handler)
        process = FakeProcess()
        cancel = threading.Event()
        isolated.active = {'cancel': cancel, 'process': process}
        isolated.server_close()
        self.assertTrue(cancel.is_set())
        self.assertTrue(process.terminated)

    def test_cancel_before_post_is_bounded_and_prevents_launch(self):
        job_id = str(uuid.uuid4())
        self.assertEqual(self.request('DELETE', '/api/transcribe', headers=self.auth(job_id))[0], 200)
        with patch('local_server.subprocess.Popen') as launch:
            status, _ = self.request('POST', '/api/transcribe', WAV, self.auth(job_id))
        self.assertEqual(status, 409)
        launch.assert_not_called()

    def test_success_mock_transcription_and_cleanup(self):
        class FakeProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return b'', b''

        def fake_launch(command, **_kwargs):
            output = command[command.index('--output') + 1]
            from pathlib import Path
            Path(output).write_text('1\n00:00:00,000 --> 00:00:01,000\n合成教材\n', encoding='utf-8')
            return FakeProcess()

        with patch('local_server.subprocess.Popen', side_effect=fake_launch):
            status, body = self.request('POST', '/api/transcribe', WAV, self.auth())
        self.assertEqual(status, 200)
        self.assertIn('合成教材', json.loads(body)['srt'])
        for _ in range(50):
            if self.server.active is None:
                break
            time.sleep(.01)
        self.assertIsNone(self.server.active)


if __name__ == '__main__':
    unittest.main()
