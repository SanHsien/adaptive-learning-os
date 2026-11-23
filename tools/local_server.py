"""Opt-in, loopback-only static site and cancellable Whisper transcription server."""

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 100 * 1024 * 1024
EXTENSIONS = {'.mp3', '.wav', '.m4a', '.mp4', '.webm'}


def valid_media(ext, header):
    if ext == '.mp3':
        return header.startswith(b'ID3') or (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224)
    if ext == '.wav':
        return header.startswith(b'RIFF') and header[8:12] == b'WAVE'
    if ext in {'.m4a', '.mp4'}:
        return header[4:8] == b'ftyp'
    return header.startswith(b'\x1a\x45\xdf\xa3') if ext == '.webm' else False


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, model='small'):
        super().__init__(address, handler)
        self.token = secrets.token_urlsafe(32)
        self.model = model
        self.lock = threading.Lock()
        self.active = None
        self.early_cancellations = {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # Avoid logging URLs, filenames or material contents.
        pass

    def _authorized(self):
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin', '')
        expected = f'http://127.0.0.1:{self.server.server_port}'
        referer = self.headers.get('Referer', '')
        same_site = origin == expected or (not origin and referer.startswith(expected + '/'))
        return (host == f'127.0.0.1:{self.server.server_port}' and same_site
                and secrets.compare_digest(self.headers.get('X-Local-Token', ''), self.server.token))

    def _json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionError, OSError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            return self.send_error(403)
        if path == '/api/session':
            expected = f'http://127.0.0.1:{self.server.server_port}'
            if (self.headers.get('Referer', '').split('?', 1)[0].split('#', 1)[0].startswith(expected + '/') is False
                    or self.headers.get('Sec-Fetch-Site', 'same-origin') != 'same-origin'):
                return self._json(403, {'error': '僅限本站取得工作階段'})
            return self._json(200, {'token': self.server.token})
        # Do not serve repo internals, .git, documents, or local attachments.
        if path not in {'/', '/index.html', '/styles.css'} and not path.startswith(('/src/', '/vendor/')):
            return self.send_error(404)
        decoded = unquote(path)
        if decoded != path or '\\' in decoded or any(part in {'.', '..'} for part in decoded.split('/')):
            return self.send_error(404)
        candidate = (ROOT / path.lstrip('/')).resolve()
        if not candidate.is_file() and path != '/':
            return self.send_error(404)
        if path != '/' and (ROOT not in candidate.parents or any(part.startswith('.') for part in candidate.relative_to(ROOT).parts)):
            return self.send_error(404)
        if path.startswith(('/src/', '/vendor/')) and (candidate.relative_to(ROOT).parts[0] != path.split('/')[1]
                or candidate.suffix.lower() not in {'.js', '.mjs', '.wasm', '.gz', '.json'}):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/transcribe' or not self._authorized():
            return self._json(403, {'error': '來源或授權不符'})
        job_id = self.headers.get('X-Job-ID', '')
        try:
            uuid.UUID(job_id)
            size = int(self.headers.get('Content-Length', '0'))
        except (ValueError, TypeError):
            return self._json(400, {'error': '任務或大小無效'})
        ext = self.headers.get('X-Media-Extension', '').lower()
        if ext not in EXTENSIONS or not 0 < size <= MAX_BYTES:
            return self._json(413, {'error': '影音格式或大小無效'})
        with self.server.lock:
            now = time.monotonic()
            self.server.early_cancellations = {key: expiry for key, expiry in self.server.early_cancellations.items() if expiry > now}
            if self.server.active is not None:
                return self._json(409, {'error': '已有轉錄進行中'})
            job = {'id': job_id, 'cancel': threading.Event(), 'process': None}
            if self.server.early_cancellations.pop(job_id, 0) > now:
                job['cancel'].set()
            self.server.active = job
        try:
            with tempfile.TemporaryDirectory(prefix='adaptive-transcribe-') as folder:
                source = Path(folder) / ('input' + ext)
                with source.open('xb') as stream:
                    remaining = size
                    while remaining:
                        if job['cancel'].is_set():
                            return self._json(409, {'error': '轉錄已取消'})
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            return self._json(400, {'error': '影音內容不完整'})
                        stream.write(chunk)
                        remaining -= len(chunk)
                with source.open('rb') as stream:
                    header = stream.read(16)
                if not valid_media(ext, header):
                    return self._json(415, {'error': '影音檔頭不符'})
                if job['cancel'].is_set():
                    return self._json(409, {'error': '轉錄已取消'})
                target = Path(folder) / 'output.srt'
                command = [sys.executable, str(ROOT / 'tools' / 'transcribe_local.py'), str(source), '--output', str(target), '--model', self.server.model]
                with self.server.lock:
                    if job['cancel'].is_set():
                        return self._json(409, {'error': '轉錄已取消'})
                    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    job['process'] = process
                try:
                    _, errors = process.communicate(timeout=1800)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    return self._json(504, {'error': '轉錄逾時，已終止'})
                if job['cancel'].is_set():
                    return self._json(409, {'error': '轉錄已取消'})
                if process.returncode != 0:
                    return self._json(500, {'error': '本機轉錄失敗，請檢查 Whisper 安裝及模型相容性'})
                if target.stat().st_size > 400000:
                    return self._json(413, {'error': '逐字稿過長，請分段轉錄'})
                content = target.read_text(encoding='utf-8')
                if len(content) > 100000:
                    return self._json(413, {'error': '逐字稿過長，請分段轉錄'})
                return self._json(200, {'srt': content})
        except (OSError, ValueError):
            return self._json(500, {'error': '本機轉錄處理失敗'})
        finally:
            with self.server.lock:
                if self.server.active is job:
                    self.server.active = None

    def do_DELETE(self):
        if urlsplit(self.path).path != '/api/transcribe' or not self._authorized():
            return self._json(403, {'error': '來源或授權不符'})
        job_id = self.headers.get('X-Job-ID', '')
        try:
            uuid.UUID(job_id)
        except ValueError:
            return self._json(400, {'error': '任務識別無效'})
        with self.server.lock:
            job = self.server.active
            if job and job['id'] == job_id:
                job['cancel'].set()
                if job['process'] and job['process'].poll() is None:
                    job['process'].terminate()
            else:
                now = time.monotonic()
                self.server.early_cancellations = {key: expiry for key, expiry in self.server.early_cancellations.items() if expiry > now}
                if len(self.server.early_cancellations) >= 64:
                    return self._json(429, {'error': '取消請求過多'})
                self.server.early_cancellations[job_id] = now + 60
        return self._json(200, {'cancelled': True})


def main():
    parser = argparse.ArgumentParser(description='本機限定的一鍵 Whisper 自修網站，僅綁定 127.0.0.1')
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--model', default='small')
    options = parser.parse_args()
    with LocalServer(('127.0.0.1', options.port), Handler, options.model) as server:
        print(f'本機自修網站：http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
