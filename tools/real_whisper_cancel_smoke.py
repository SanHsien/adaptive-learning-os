"""Opt-in Windows integration smoke for cancelling an actual Whisper child.

Uses synthetic audio only. Run with the project's .venv and cached small model.
"""

import http.client
import io
import json
import subprocess
import sys
import threading
import time
import uuid
import wave
from pathlib import Path
from unittest.mock import patch

from local_server import Handler, LocalServer, ROOT


def synthetic_wav(seconds=30):
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b'\0' * (seconds * 16000 * 2))
    return output.getvalue()


def main():
    interpreter = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not interpreter.exists():
        raise RuntimeError('Expected project .venv Python on Windows')
    server = LocalServer(('127.0.0.1', 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_port
    origin = f'http://127.0.0.1:{port}'
    original_popen = subprocess.Popen
    launched = threading.Event()
    captured = {}
    response = {}
    wav = synthetic_wav()
    job_id = str(uuid.uuid4())

    def headers(identifier):
        return {'Host': f'127.0.0.1:{port}', 'Origin': origin,
                'X-Local-Token': server.token, 'X-Job-ID': identifier,
                'X-Media-Extension': '.wav'}

    def request(method, identifier, data=None):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=90)
        try:
            conn.request(method, '/api/transcribe', body=data, headers=headers(identifier))
            result = conn.getresponse()
            return result.status, result.read()
        finally:
            conn.close()

    def launch(command, **kwargs):
        command = [str(interpreter), *command[1:]]
        captured['folder'] = Path(command[command.index('--output') + 1]).parent
        process = original_popen(command, **kwargs)
        captured['process'] = process
        launched.set()
        return process

    def upload():
        try:
            response['result'] = request('POST', job_id, wav)
        except Exception as exc:
            response['error'] = exc

    worker = threading.Thread(target=upload)
    try:
        with patch('local_server.subprocess.Popen', side_effect=launch):
            worker.start()
            assert launched.wait(15), 'Whisper process did not start'
            process = captured['process']
            time.sleep(0.3)
            assert process.poll() is None, 'Whisper process ended before cancellation'
            assert request('POST', str(uuid.uuid4()), b'RIFF' + b'\0' * 8 + b'WAVE')[0] == 409
            assert request('DELETE', job_id)[0] == 200
            worker.join(45)
            assert not worker.is_alive(), 'Cancelled HTTP request stayed active'
            assert 'error' not in response, repr(response.get('error'))
            assert response['result'][0] == 409, response['result'][0]
            assert process.poll() is not None, 'Whisper child survived cancellation'
            deadline = time.monotonic() + 10
            while captured['folder'].exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not captured['folder'].exists(), 'Temporary audio was retained'
            assert server.active is None, 'Task slot was not released'

        class CompletedProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return b'', b''

        def next_launch(command, **kwargs):
            Path(command[command.index('--output') + 1]).write_text(
                '1\n00:00:00,000 --> 00:00:01,000\n恢復成功\n', encoding='utf-8')
            return CompletedProcess()

        with patch('local_server.subprocess.Popen', side_effect=next_launch):
            status, body = request('POST', str(uuid.uuid4()), wav)
        assert status == 200 and '恢復成功' in json.loads(body)['srt']
        print('PASS: real Whisper child cancelled, temp cleaned, next job recovered')
    finally:
        if 'process' in captured and captured['process'].poll() is None:
            captured['process'].kill()
            captured['process'].wait(timeout=15)
        worker.join(15) if worker.ident else None
        server.shutdown()
        server.server_close()
        server_thread.join(10)


if __name__ == '__main__':
    main()
