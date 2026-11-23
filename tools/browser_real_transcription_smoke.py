"""Opt-in real Whisper browser smoke; Windows synthetic voice only.

Run with system Python (Playwright installed) and .venv Python (Whisper installed).
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from local_server import Handler, LocalServer


ROOT = Path(__file__).resolve().parents[1]
WHISPER_PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'


def make_synthetic_audio(target):
    # Script contains only a fixed public test sentence and a temporary file path.
    script = (
        'Add-Type -AssemblyName System.Speech; '
        '$v = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        f'$v.SetOutputToWaveFile(\'{target}\'); '
        '$v.Speak(\'今天我們學習數學，二加三等於五。\'); '
        '$v.Dispose()'
    )
    subprocess.run(['powershell', '-NoProfile', '-Command', script], check=True,
                   capture_output=True, timeout=40)
    assert target.is_file() and target.stat().st_size > 44, 'no synthesized WAV'


def run():
    if os.name != 'nt' or not WHISPER_PYTHON.is_file():
        raise RuntimeError('Windows and project .venv Whisper Python are required')
    with tempfile.TemporaryDirectory(prefix='adaptive-real-smoke-') as folder:
        audio = Path(folder) / 'synthetic.wav'
        make_synthetic_audio(audio)
        server = LocalServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # The HTTP server runs in this test process; only its child uses .venv.
            with patch('local_server.sys.executable', str(WHISPER_PYTHON)):
                with sync_playwright() as playwright:
                    executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
                    opts = {'executable_path': executable} if executable else {'channel': 'chrome'}
                    browser = playwright.chromium.launch(**opts, headless=True, timeout=20000)
                    try:
                        page = browser.new_page()
                        page.set_default_timeout(180000)
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('#learnerName').fill('合成甲')
                        page.locator('#addLearner button').click()
                        page.locator('#learner').select_option(label='合成甲')
                        page.locator('#subjectName').fill('數學')
                        page.locator('#addSubject button').click()
                        page.locator('#subject').select_option(label='數學')
                        page.locator('#materialFile').set_input_files(str(audio))
                        page.locator('#runTranscription').click()
                        page.get_by_text('本機轉錄完成', exact=False).wait_for()
                        recognized = page.locator('#material').input_value()
                        assert recognized.strip(), 'empty Whisper transcript'
                        page.locator('#material').fill('已校對：二加三等於五')
                        page.locator('#materialForm button').click()
                        page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
                        page.locator('#learnerName').fill('合成乙')
                        page.locator('#addLearner button').click()
                        page.locator('#learner').select_option(label='合成乙')
                        page.locator('#subjectName').fill('數學')
                        page.locator('#addSubject button').click()
                        page.locator('#subject').select_option(label='數學')
                        assert not page.locator('#material').input_value(), 'cross-learner data leak'
                        page.locator('#learner').select_option(label='合成甲')
                        page.locator('#subject').select_option(label='數學')
                        page.wait_for_function("() => document.querySelector('#material').value === '已校對：二加三等於五'")
                        assert not errors, errors
                        assert server.active is None, 'transcription task not released'
                        print('PASS: real Whisper browser flow, corrected material, learner isolation', flush=True)
                        print(f'Recognized characters: {len(recognized)}', flush=True)
                    finally:
                        browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == '__main__':
    run()
