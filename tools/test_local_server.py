"""Synthetic HTTP integration checks; no Whisper model or personal files."""

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from local_server import Handler, LocalServer, launch_worker, stop_process_tree


WAV = b'RIFF\x24\x00\x00\x00WAVEfmt '


class ServerTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows Job Objects')
    def test_orphan_descendant_is_killed_after_parent_exit(self):
        """Job lifetime includes children when their launching parent already exited."""
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'orphan.pid'
            program = (
                'import subprocess,sys,pathlib; '
                'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                'pathlib.Path(sys.argv[1]).write_text(str(child.pid))'
            )
            parent = launch_worker([sys.executable, '-c', program, str(marker)])
            child_pid = None
            try:
                parent.wait(timeout=10)
                self.assertTrue(marker.exists(), 'parent did not spawn a descendant')
                child_pid = int(marker.read_text())
                before = subprocess.run(['tasklist', '/FI', f'PID eq {child_pid}', '/FO', 'CSV', '/NH'],
                                        capture_output=True, text=True, timeout=10)
                self.assertIn(f'"{child_pid}"', before.stdout, 'descendant exited before cleanup')
                stop_process_tree(parent)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = subprocess.run(['tasklist', '/FI', f'PID eq {child_pid}', '/FO', 'CSV', '/NH'],
                                            capture_output=True, text=True, timeout=10)
                    if f'"{child_pid}"' not in result.stdout:
                        break
                    time.sleep(.05)
                self.assertNotIn(f'"{child_pid}"', result.stdout, 'orphan descendant survived cleanup')
            finally:
                stop_process_tree(parent)
                parent.stderr.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows process-tree termination')
    def test_cancel_terminates_descendant_process(self):
        """A real child that starts a grandchild must leave neither running."""
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'descendant.pid'
            program = (
                'import subprocess,sys,time,pathlib; '
                'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                'pathlib.Path(sys.argv[1]).write_text(str(child.pid)); '
                'time.sleep(60)'
            )
            parent = subprocess.Popen([sys.executable, '-c', program, str(marker)],
                                      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists(), 'descendant did not start')
                descendant_pid = int(marker.read_text())
                stop_process_tree(parent)
                parent.wait(timeout=10)
                inspected = subprocess.run(['tasklist', '/FI', f'PID eq {descendant_pid}', '/FO', 'CSV', '/NH'],
                                           capture_output=True, text=True, timeout=10)
                self.assertNotIn(f'"{descendant_pid}"', inspected.stdout,
                                 'descendant survived cancellation')
            finally:
                if parent.poll() is None:
                    stop_process_tree(parent)
                    parent.wait(timeout=10)

    @unittest.skipUnless(os.name == 'nt', 'Windows process-tree counters')
    def test_resource_sampler_includes_real_descendant(self):
        from real_whisper_resource_smoke import descendant_pids, sample_process_tree

        with __import__('tempfile').TemporaryDirectory() as directory:
            marker = Path(directory) / 'child.pid'
            program = (
                'import subprocess,sys,time,pathlib; '
                'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
                'pathlib.Path(sys.argv[1]).write_text(str(child.pid)); '
                'time.sleep(30)'
            )
            parent = subprocess.Popen([sys.executable, '-c', program, str(marker)],
                                      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists(), 'child did not start')
                descendant_pid = int(marker.read_text())
                self.assertIn(descendant_pid, descendant_pids(parent.pid))
                usage = {}
                memory, count = sample_process_tree(parent.pid, usage)
                self.assertGreaterEqual(count, 2)
                self.assertGreater(memory, 0)
                self.assertIn(descendant_pid, usage)
            finally:
                stop_process_tree(parent)
                parent.wait(timeout=10)

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

    def setUp(self):
        # The HTTP response can reach the client before the handler's finally
        # releases the shared server slot. Detect a leak after a bounded wait.
        self.wait_for_available_slot()

    def wait_for_available_slot(self):
        deadline = time.monotonic() + 5
        while self.server.active is not None and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertIsNone(self.server.active, 'job slot was not released')

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

    def test_real_child_cancel_cleanup_and_next_job(self):
        """Exercise a real OS child, not a mock Whisper process."""
        started = threading.Event()
        captured = {}
        result = {}
        job_id = str(uuid.uuid4())
        original_popen = subprocess.Popen

        def launch(command, **kwargs):
            captured['folder'] = Path(command[command.index('--output') + 1]).parent
            process = original_popen(
                [sys.executable, '-c', 'import time; time.sleep(60)'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            captured['process'] = process
            started.set()
            return process

        def upload():
            result['response'] = self.request('POST', '/api/transcribe', WAV, self.auth(job_id))

        with patch('local_server.subprocess.Popen', side_effect=launch):
            worker = threading.Thread(target=upload)
            worker.start()
            try:
                self.assertTrue(started.wait(20), 'real child did not start')
                self.assertEqual(self.request('POST', '/api/transcribe', WAV, self.auth())[0], 409)
                status, _ = self.request('DELETE', '/api/transcribe', headers=self.auth(job_id))
                self.assertEqual(status, 200)
                worker.join(8)
                self.assertFalse(worker.is_alive(), 'cancelled request did not finish')
                self.assertEqual(result['response'][0], 409)
                self.assertIsNotNone(captured['process'].poll(), 'cancelled child is still running')
                deadline = time.monotonic() + 5
                while captured['folder'].exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertFalse(captured['folder'].exists(), 'temporary media not cleaned')
            finally:
                if 'process' in captured and captured['process'].poll() is None:
                    captured['process'].kill()
                    captured['process'].wait(timeout=5)
                worker.join(8)
        self.wait_for_available_slot()
        class QuickProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return b'', b''

        def next_launch(command, **kwargs):
            Path(command[command.index('--output') + 1]).write_text(
                '1\n00:00:00,000 --> 00:00:01,000\n再次轉錄\n', encoding='utf-8')
            return QuickProcess()

        with patch('local_server.subprocess.Popen', side_effect=next_launch):
            status, body = self.request('POST', '/api/transcribe', WAV, self.auth())
        self.assertEqual(status, 200)
        self.assertIn('再次轉錄', json.loads(body)['srt'])

    def test_cancel_before_post_is_bounded_and_prevents_launch(self):
        job_id = str(uuid.uuid4())
        self.assertEqual(self.request('DELETE', '/api/transcribe', headers=self.auth(job_id))[0], 200)
        with patch('local_server.subprocess.Popen') as launch:
            status, _ = self.request('POST', '/api/transcribe', WAV, self.auth(job_id))
        self.assertEqual(status, 409)
        launch.assert_not_called()

    def test_repeated_real_child_cancel_and_recovery(self):
        """Repeated cancellation must free the same server's job slot every time."""
        original_popen = subprocess.Popen

        for cycle in range(3):
            with self.subTest(cycle=cycle):
                started = threading.Event()
                captured = {}
                result = {}
                job_id = str(uuid.uuid4())

                def launch(command, **kwargs):
                    captured['folder'] = Path(command[command.index('--output') + 1]).parent
                    process = original_popen(
                        [sys.executable, '-c', 'import time; time.sleep(60)'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    )
                    captured['process'] = process
                    started.set()
                    return process

                def upload():
                    result['response'] = self.request('POST', '/api/transcribe', WAV, self.auth(job_id))

                worker = threading.Thread(target=upload)
                with patch('local_server.subprocess.Popen', side_effect=launch):
                    worker.start()
                    try:
                        self.assertTrue(started.wait(10), 'child did not start')
                        self.assertEqual(self.request('POST', '/api/transcribe', WAV, self.auth())[0], 409)
                        self.assertEqual(self.request('DELETE', '/api/transcribe', headers=self.auth(job_id))[0], 200)
                        worker.join(8)
                        self.assertFalse(worker.is_alive(), 'cancelled request is still running')
                        self.assertEqual(result['response'][0], 409)
                        self.assertIsNotNone(captured['process'].poll(), 'child survived cancellation')
                        deadline = time.monotonic() + 5
                        while captured['folder'].exists() and time.monotonic() < deadline:
                            time.sleep(.02)
                        self.assertFalse(captured['folder'].exists(), 'temporary folder survived')
                        self.wait_for_available_slot()
                    finally:
                        if 'process' in captured and captured['process'].poll() is None:
                            captured['process'].kill()
                            captured['process'].wait(timeout=5)
                        worker.join(8)

        class QuickProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return b'', b''

        def recover(command, **kwargs):
            Path(command[command.index('--output') + 1]).write_text(
                '1\n00:00:00,000 --> 00:00:01,000\n恢復成功\n', encoding='utf-8')
            return QuickProcess()

        with patch('local_server.subprocess.Popen', side_effect=recover):
            status, body = self.request('POST', '/api/transcribe', WAV, self.auth())
        self.assertEqual(status, 200)
        self.assertIn('恢復成功', json.loads(body)['srt'])
        deadline = time.monotonic() + 5
        while self.server.active is not None and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertIsNone(self.server.active)

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
