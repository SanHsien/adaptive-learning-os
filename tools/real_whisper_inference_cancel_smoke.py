"""Opt-in Windows Whisper cancellation after a real decoded segment.

The test wraps the child entrypoint to signal the first decoded Whisper segment.
All audio is synthesized locally and kept in temporary directories.
"""

import argparse
import http.client
import os
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from unittest.mock import patch

from local_server import Handler, LocalServer, ROOT


WRAPPER = '''import runpy
import sys
from pathlib import Path
from faster_whisper import WhisperModel

original = WhisperModel.transcribe
marker, entry, *arguments = sys.argv[1:]

def instrument(self, *args, **kwargs):
    segments, info = original(self, *args, **kwargs)
    def observed():
        first = True
        for segment in segments:
            if first:
                Path(marker).touch()
                first = False
            yield segment
    return observed(), info

WhisperModel.transcribe = instrument
sys.argv = [entry, *arguments]
runpy.run_path(entry, run_name='__main__')
'''


def synthetic_audio(target):
    with tempfile.TemporaryDirectory(prefix='adaptive-speech-') as folder:
        short = Path(folder) / 'speech.wav'
        script = (
            'Add-Type -AssemblyName System.Speech; '
            '$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
            f'$voice.SetOutputToWaveFile(\'{short}\'); '
            '$voice.Speak(\'今天我們練習數學。二加三等於五。\'); '
            '$voice.Dispose()'
        )
        subprocess.run(['powershell', '-NoProfile', '-Command', script],
                       check=True, capture_output=True, timeout=40)
        with wave.open(str(short), 'rb') as reader:
            params = reader.getparams()
            frames = reader.readframes(reader.getnframes())
        repetitions = max(2, int(45 * params.framerate / (len(frames) / (params.sampwidth * params.nchannels))))
        with wave.open(str(target), 'wb') as writer:
            writer.setparams(params)
            writer.writeframes(frames * repetitions)


def main():
    parser = argparse.ArgumentParser(description='Real Whisper cancellation and recovery smoke')
    parser.add_argument('--cycles', type=int, default=1, choices=range(1, 4), metavar='{1,2,3}')
    options = parser.parse_args()
    interpreter = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if os.name != 'nt' or not interpreter.is_file():
        raise RuntimeError('Windows and project .venv Whisper installation required')

    with tempfile.TemporaryDirectory(prefix='adaptive-inference-smoke-') as folder:
        directory = Path(folder)
        wrapper = directory / 'instrumented_whisper.py'
        wrapper.write_text(WRAPPER, encoding='utf-8')
        audio = directory / 'synthetic.wav'
        synthetic_audio(audio)

        server = LocalServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original_popen = subprocess.Popen
        def request(method, identifier, body=None):
            port = server.server_port
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=180)
            try:
                conn.request(method, '/api/transcribe', body=body, headers={
                    'Host': f'127.0.0.1:{port}',
                    'Origin': f'http://127.0.0.1:{port}',
                    'X-Local-Token': server.token,
                    'X-Job-ID': identifier,
                    'X-Media-Extension': '.wav',
                })
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        try:
            for cycle in range(options.cycles):
                job_id = str(uuid.uuid4())
                marker = directory / f'first_segment_{cycle}'
                results = {}
                process_holder = {}

                def launch(command, **kwargs):
                    instrumented = [str(interpreter), str(wrapper), str(marker), *command[1:]]
                    process = original_popen(instrumented, **kwargs)
                    process_holder['process'] = process
                    process_holder['temp'] = Path(command[command.index('--output') + 1]).parent
                    return process

                def upload():
                    try:
                        results['response'] = request('POST', job_id, audio.read_bytes())
                    except Exception as exc:
                        results['error'] = exc

                worker = threading.Thread(target=upload)
                try:
                    with patch('local_server.subprocess.Popen', side_effect=launch):
                        worker.start()
                        deadline = time.monotonic() + 100
                        while not marker.exists() and time.monotonic() < deadline:
                            process = process_holder.get('process')
                            if process and process.poll() is not None:
                                raise AssertionError('Whisper finished or failed before first-segment signal')
                            time.sleep(0.1)
                        assert marker.exists(), 'No decoded segment observed within 100 seconds'
                        process = process_holder['process']
                        assert process.poll() is None, 'Whisper exited before inference cancellation'
                        assert request('DELETE', job_id)[0] == 200
                        worker.join(30)
                        assert not worker.is_alive(), 'Cancelled HTTP request did not return'
                        assert 'error' not in results, repr(results.get('error'))
                        assert results['response'][0] == 409, results['response'][0]
                        assert process.poll() is not None, 'Whisper child survived cancellation'
                        deadline = time.monotonic() + 10
                        while (process_holder['temp'].exists() or server.active is not None) and time.monotonic() < deadline:
                            time.sleep(0.05)
                        assert not process_holder['temp'].exists(), 'Temporary media folder retained'
                        assert server.active is None, 'Active task slot retained'
                        print(f'PASS: real Whisper inference cancellation cycle {cycle + 1}/{options.cycles}', flush=True)
                finally:
                    process = process_holder.get('process')
                    if process and process.poll() is None:
                        process.kill()
                        process.wait(timeout=15)
                    if worker.ident:
                        worker.join(15)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(10)


if __name__ == '__main__':
    main()
