"""End-to-end synthetic transcription flow using a mocked Whisper process."""

import os
import threading
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from local_server import Handler, LocalServer


class FakeProcess:
    returncode = 0

    def communicate(self, timeout=None):
        return b'', b''


class BlockingProcess:
    def __init__(self):
        self.returncode = None
        self.stopped = threading.Event()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15
        self.stopped.set()

    def kill(self):
        self.terminate()

    def communicate(self, timeout=None):
        if not self.stopped.wait(min(timeout or 5, 5)):
            raise AssertionError('cancel did not reach subprocess')
        return b'', b''


def fake_launch(command, **_kwargs):
    output = command[command.index('--output') + 1]
    Path(output).write_text('1\n00:00:00,000 --> 00:00:01,000\n合成教材\n', encoding='utf-8')
    return FakeProcess()


def run():
    server = LocalServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    blocking = {'enabled': False, 'process': None}

    def launch(command, **kwargs):
        if blocking['enabled']:
            blocking['process'] = BlockingProcess()
            return blocking['process']
        return fake_launch(command, **kwargs)

    try:
        with patch('local_server.subprocess.Popen', side_effect=launch):
            with sync_playwright() as playwright:
                executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
                options = {'executable_path': executable} if executable else {'channel': 'chrome'}
                browser = playwright.chromium.launch(**options, headless=True, timeout=20000)
                try:
                    page = browser.new_page()
                    page.set_default_timeout(10000)
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(origin, wait_until='domcontentloaded')
                    page.locator('#learnerName').fill('合成甲')
                    page.locator('#addLearner button').click()
                    page.locator('#learner').select_option(label='合成甲')
                    page.locator('#subjectName').fill('數學')
                    page.locator('#addSubject button').click()
                    page.locator('#subject').select_option(label='數學')
                    page.locator('#materialFile').set_input_files({
                        'name': 'synthetic.wav', 'mimeType': 'audio/wav',
                        'buffer': b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 32})
                    page.locator('#runTranscription').click()
                    page.get_by_text('本機轉錄完成', exact=False).wait_for()
                    assert page.locator('#material').input_value() == '合成教材'
                    page.locator('#material').fill('合成教材，已人工校對')
                    page.locator('#materialForm button').click()
                    page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
                    assert page.locator('#material').input_value() == '合成教材，已人工校對'
                    blocking['enabled'] = True
                    page.locator('#materialFile').set_input_files({
                        'name': 'cancel.wav', 'mimeType': 'audio/wav',
                        'buffer': b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 32})
                    page.locator('#runTranscription').click()
                    page.get_by_text('正在本機轉錄', exact=False).wait_for()
                    page.wait_for_function('() => document.querySelector("#runTranscription").disabled')
                    from time import monotonic, sleep
                    started = monotonic()
                    while blocking['process'] is None and monotonic() - started < 5:
                        sleep(.02)
                    assert blocking['process'] is not None, 'mock transcription did not start'
                    page.locator('#learnerName').fill('合成乙')
                    page.locator('#addLearner button').click()
                    page.locator('#learner').select_option(label='合成乙')
                    assert blocking['process'].stopped.wait(5), 'cancel failed to terminate child'
                    page.locator('#subjectName').fill('數學')
                    page.locator('#addSubject button').click()
                    page.locator('#subject').select_option(label='數學')
                    assert page.locator('#material').input_value() == ''
                    page.locator('#learner').select_option(label='合成甲')
                    page.locator('#subject').select_option(label='數學')
                    assert page.locator('#material').input_value() == '合成教材，已人工校對'
                    assert not errors, errors
                    print('PASS: browser synthetic transcription, scoped save, cross-learner cancellation', flush=True)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


if __name__ == '__main__':
    run()
