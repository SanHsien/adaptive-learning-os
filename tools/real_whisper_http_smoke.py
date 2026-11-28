"""Exercise the production HTTP upload and real CPU batched Whisper worker."""
import argparse
import http.client
import json
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from local_server import Handler, LocalServer
from real_whisper_resource_smoke import long_audio, validate_timeline
from transcribe_local import MAX_AUDIO_SECONDS, MAX_BYTES, SAMPLE_RATE, decode_bounded


def make_media(folder, duration, media_format):
    source = Path(folder) / 'synthetic.m4a'
    long_audio(source, duration)
    if media_format != 'm4a':
        video = source.with_suffix('.' + media_format)
        video_codec, audio_codec = ('mpeg4', 'copy') if media_format == 'mp4' else ('libvpx', 'libopus')
        frame_rate = 1 if media_format == 'mp4' else 10
        # Lossless MP4 avoids AAC encoder padding at the exact duration limit.
        subprocess.run([
            'ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            f'color=c=blue:s=64x64:r={frame_rate}:d={duration}', '-i', str(source),
            '-c:v', video_codec, '-c:a', audio_codec,
            *(['-b:a', '48k'] if media_format == 'webm' else []),
            '-shortest', str(video),
        ], check=True, timeout=300, capture_output=True)
        source = video
        assert 0 < source.stat().st_size <= MAX_BYTES
        assert len(decode_bounded(source)) == duration * SAMPLE_RATE
    return source


def run(duration, media_format='m4a'):
    with tempfile.TemporaryDirectory(prefix='adaptive-http-smoke-') as folder:
        source = make_media(folder, duration, media_format)
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
                        'X-Job-ID': str(uuid.uuid4()), 'X-Media-Extension': source.suffix,
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
                    'result': 'PASS', 'format': media_format, 'duration_seconds': duration,
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
    parser.add_argument('--format', choices=('m4a', 'mp4', 'webm'), default='m4a')
    args = parser.parse_args()
    run(args.duration_seconds, args.format)
