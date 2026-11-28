"""Exercise the production HTTP upload and real CPU batched Whisper worker."""
import argparse
import http.client
import json
import tempfile
import threading
import time
import uuid
from pathlib import Path

from local_server import Handler, LocalServer
from real_whisper_resource_smoke import long_audio, validate_timeline
from transcribe_local import MAX_AUDIO_SECONDS


def run(duration):
    with tempfile.TemporaryDirectory(prefix='adaptive-http-smoke-') as folder:
        source = Path(folder) / 'synthetic.m4a'
        long_audio(source, duration)
        with LocalServer(('127.0.0.1', 0), Handler, batched=True) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = f'http://127.0.0.1:{server.server_port}'
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=1850)
            start = time.monotonic()
            try:
                with source.open('rb') as stream:
                    connection.request('POST', '/api/transcribe', body=stream, headers={
                        'Origin': origin, 'X-Local-Token': server.token,
                        'X-Job-ID': str(uuid.uuid4()), 'X-Media-Extension': '.m4a',
                        'Content-Type': 'application/octet-stream',
                        'Content-Length': str(source.stat().st_size),
                    })
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                assert response.status == 200, (response.status, payload.get('error'))
                target = Path(folder) / 'output.srt'
                target.write_text(payload['srt'], encoding='utf-8')
                cues, end = validate_timeline(target, duration)
                deadline = time.monotonic() + 5
                while server.active is not None and time.monotonic() < deadline:
                    time.sleep(.02)
                assert server.active is None and not server.recovery_required
                print(json.dumps({
                    'result': 'PASS', 'duration_seconds': duration,
                    'source_bytes': source.stat().st_size, 'cues': cues,
                    'last_cue_seconds': end,
                    'wall_seconds': round(time.monotonic() - start, 2),
                }), flush=True)
            finally:
                connection.close()
                server.shutdown()
                thread.join(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-seconds', type=int, default=30,
                        choices=range(30, MAX_AUDIO_SECONDS + 1), metavar='30..3600')
    run(parser.parse_args().duration_seconds)
