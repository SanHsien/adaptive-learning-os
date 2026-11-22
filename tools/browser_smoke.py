"""Non-destructive local browser smoke using synthetic learners only.

Requires: pip install playwright; an installed Chrome browser.
Run: python tools/browser_smoke.py
"""

import json
import base64
import io
import zipfile
from PIL import Image, ImageDraw, ImageFont
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def sample_scanned_pdf():
    """Synthetic one-page image-only PDF: no selectable text layer."""
    image = Image.new('RGB', (1000, 260), 'white')
    drawer = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msjh.ttc', 115)
    drawer.text((40, 50), '學習中文', font=font, fill='black')
    result = io.BytesIO()
    image.save(result, format='PDF', resolution=150)
    return result.getvalue()


def sample_pdf():
    objects = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        '<< /Length 50 >>\nstream\nBT /F1 12 Tf 72 720 Td (PDF chapter basics) Tj ET\nendstream',
    ]
    output = b'%PDF-1.4\n'
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{number} 0 obj\n{obj}\nendobj\n'.encode('ascii')
    start = len(output)
    output += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode('ascii')
    for offset in offsets[1:]:
        output += f'{offset:010d} 00000 n \n'.encode('ascii')
    return output + f'trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{start}\n%%EOF\n'.encode('ascii')


def sample_mixed_pdf():
    """Three pages: selectable text, raster-only Chinese, selectable text."""
    picture = Image.new('RGB', (1000, 260), 'white')
    drawer = ImageDraw.Draw(picture)
    font = ImageFont.truetype('C:/Windows/Fonts/msjh.ttc', 115)
    drawer.text((40, 50), '學習中文', font=font, fill='black')
    raster = io.BytesIO()
    picture.save(raster, format='JPEG', quality=90)
    image_bytes = raster.getvalue()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 6 0 R >> >> /Contents 7 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 9 0 R >> >> /Contents 8 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 6 0 R >> >> /Contents 10 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    def stream(data, metadata=b''):
        return b'<< /Length ' + str(len(data)).encode() + metadata + b' >>\nstream\n' + data + b'\nendstream'
    objects.extend([
        stream(b'BT /F1 18 Tf 72 720 Td (First text page) Tj ET'),
        stream(b'q 550 0 0 143 31 580 cm /Im1 Do Q'),
        stream(image_bytes, b' /Type /XObject /Subtype /Image /Width 1000 /Height 260 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode'),
        stream(b'BT /F1 18 Tf 72 720 Td (Third text page) Tj ET'),
    ])
    output = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(output)
    output += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:
        output += f'{offset:010d} 00000 n \n'.encode()
    return output + f'trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{start}\n%%EOF\n'.encode()


def sample_docx():
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX chapter basics</w:t></w:r></w:p></w:body></w:document>')
    return result.getvalue()


@contextmanager
def local_server():
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    # Browser OCR workers may keep HTTP requests alive during shutdown.
    server.daemon_threads = True
    server.block_on_close = False
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def create_learner(page, name):
    page.locator("#learnerName").fill(name)
    page.locator("#addLearner button").click()
    page.locator("#learner").select_option(label=name)


def create_subject(page, name, material, question):
    page.locator("#subjectName").fill(name)
    page.locator("#addSubject button").click()
    page.locator("#subject").select_option(label=name)
    page.locator("#material").fill(material)
    page.locator("#materialForm button").click()
    page.locator("#question").fill(question)
    page.locator("#answer").fill("合成答案")
    page.locator('button[name="result"][value="correct"]').click()
    page.get_by_text(question, exact=False).wait_for()


def run():
    with local_server() as origin, sync_playwright() as playwright:
        print('SMOKE: launching Chrome', flush=True)
        browser = playwright.chromium.launch(channel="chrome", headless=True, timeout=20000)
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            ocr_errors = []
            external_requests = []
            page.on('request', lambda request: external_requests.append(request.url) if not request.url.startswith((origin, 'blob:', 'data:')) else None)
            page.on('pageerror', lambda error: ocr_errors.append(f'pageerror: {error}'))
            page.on('console', lambda message: ocr_errors.append(f'console: {message.text}') if message.type == 'error' else None)
            page.on('requestfailed', lambda request: ocr_errors.append(f'failed: {request.url}: {request.failure}'))
            page.on('response', lambda response: ocr_errors.append(f'http {response.status}: {response.url}') if response.status >= 400 else None)
            page.goto(origin, wait_until="domcontentloaded")
            print('SMOKE: page ready', flush=True)
            create_learner(page, "測試甲")
            create_subject(page, "數學", "甲數教材", "甲數問題")
            page.locator("#materialFile").set_input_files({
                "name": "chapter.md", "mimeType": "text/markdown", "buffer": "章節題目：分數加法".encode("utf-8")
            })
            page.get_by_text("檔案內容已載入預覽", exact=False).wait_for()
            assert page.locator("#material").input_value() == "章節題目：分數加法"
            page.locator("#materialForm button").click()
            page.get_by_text("這個科目的教材已儲存", exact=False).wait_for()
            assert "chapter.md" in page.locator("#materialOrigin").inner_text()
            for name, mime, payload, expected in [
                ('chapter.pdf', 'application/pdf', sample_pdf(), 'PDF chapter basics'),
                ('chapter.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', sample_docx(), 'DOCX chapter basics'),
            ]:
                print(f'SMOKE: parse {name}', flush=True)
                page.locator('#materialFile').set_input_files({'name': name, 'mimeType': mime, 'buffer': payload})
                try:
                    page.get_by_text('檔案內容已載入預覽', exact=False).wait_for(timeout=8000)
                except Exception:
                    raise AssertionError(f'{name} parser: {page.locator("#message").inner_text()}') from None
                assert expected in page.locator('#material').input_value()
                page.locator('#materialForm button').click()
                page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
                assert name in page.locator('#materialOrigin').inner_text()
            print('SMOKE: OCR scanned.pdf', flush=True)
            page.locator('#materialFile').set_input_files({'name': 'scanned.pdf', 'mimeType': 'application/pdf', 'buffer': sample_scanned_pdf()})
            try:
                page.get_by_text('檔案內容已載入預覽', exact=False).wait_for(timeout=60000)
            except Exception:
                raise AssertionError(f'scanned PDF failure: {page.locator("#message").inner_text()!r}; {ocr_errors[-10:]}') from None
            assert '【第 1 頁】' in page.locator('#material').input_value()
            assert len(page.locator('#material').input_value().replace('【第 1 頁】', '').strip()) >= 2
            page.locator('#materialForm button').click()
            page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
            assert 'scanned.pdf' in page.locator('#materialOrigin').inner_text()
            print('SMOKE: mixed text/scanned/text PDF', flush=True)
            page.locator('#materialFile').set_input_files({'name': 'mixed.pdf', 'mimeType': 'application/pdf', 'buffer': sample_mixed_pdf()})
            try:
                page.get_by_text('檔案內容已載入預覽', exact=False).wait_for(timeout=60000)
            except Exception:
                raise AssertionError(f'mixed PDF failure: {page.locator("#message").inner_text()!r}; {ocr_errors[-10:]}') from None
            mixed = page.locator('#material').input_value()
            assert mixed.index('【第 1 頁】') < mixed.index('First text page') < mixed.index('【第 2 頁】')
            assert mixed.index('【第 2 頁】') < mixed.index('【第 3 頁】') < mixed.index('Third text page')
            assert len(mixed.split('【第 2 頁】')[1].split('【第 3 頁】')[0].strip()) >= 2
            page.locator('#materialForm button').click()
            page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
            assert 'mixed.pdf' in page.locator('#materialOrigin').inner_text()
            # Image preview requires manual text; raw image is not stored in the backup.
            tiny_png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==')
            page.locator('#materialFile').set_input_files({'name': 'diagram.png', 'mimeType': 'image/png', 'buffer': tiny_png})
            page.get_by_text('圖片可按', exact=False).wait_for()
            assert page.locator('#imagePanel').is_visible()
            assert page.locator('#material').input_value() == ''
            # Run the bundled OCR engine in Chrome with synthetic local image data.
            ocr_png = page.evaluate('''() => {
                const canvas = document.createElement('canvas');
                canvas.width = 850; canvas.height = 170;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 850, 170);
                ctx.fillStyle = 'black'; ctx.font = 'bold 90px sans-serif';
                ctx.fillText('學習中文', 30, 115);
                return canvas.toDataURL('image/png').split(',')[1];
            }''')
            page.locator('#materialFile').set_input_files({'name': 'ocr.png', 'mimeType': 'image/png', 'buffer': base64.b64decode(ocr_png)})
            page.get_by_text('圖片可按', exact=False).wait_for()
            page.locator('#runOcr').click()
            try:
                page.get_by_text('OCR 完成', exact=False).wait_for(timeout=45000)
            except Exception:
                raise AssertionError(f'OCR browser failure: {page.locator("#message").inner_text()!r}; errors: {ocr_errors[-12:]}') from None
            assert page.locator('#material').input_value().strip()
            assert 'ocr.png' in page.locator('#materialOrigin').inner_text()
            page.locator('#material').fill('人工辨識：三角形')
            page.locator('#materialForm button').click()
            page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
            assert 'ocr.png' in page.locator('#materialOrigin').inner_text()
            assert page.locator('#imagePanel').is_hidden()
            assert not external_requests, f'Unexpected external network request: {external_requests[:5]}'
            # Restore DOCX to test that invalid files do not replace existing content.
            page.locator('#materialFile').set_input_files({'name': 'chapter.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': sample_docx()})
            page.get_by_text('檔案內容已載入預覽', exact=False).wait_for()
            page.locator('#materialForm button').click()
            page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
            # Invalid files must not change the saved lesson or its source.
            original = page.locator('#material').input_value()
            for name, mime, payload in [
                ('broken.pdf', 'application/pdf', b'not a PDF'),
                ('broken.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', b'not a ZIP'),
            ]:
                before = page.locator('#message').inner_text()
                page.locator('#materialFile').set_input_files({'name': name, 'mimeType': mime, 'buffer': payload})
                page.wait_for_function("previous => document.querySelector('#message').textContent !== previous", arg=before, timeout=8000)
                assert '檔案內容已載入預覽' not in page.locator('#message').inner_text()
                assert page.locator('#material').input_value() == original
                assert 'chapter.docx' in page.locator('#materialOrigin').inner_text()
            # Preserve the original Markdown for the isolation/export assertions below.
            page.locator('#materialFile').set_input_files({'name': 'chapter.md', 'mimeType': 'text/markdown', 'buffer': '章節題目：分數加法'.encode('utf-8')})
            page.get_by_text('檔案內容已載入預覽', exact=False).wait_for()
            page.locator('#materialForm button').click()
            page.get_by_text('這個科目的教材已儲存', exact=False).wait_for()
            create_subject(page, "英文", "甲英教材", "甲英問題")
            create_learner(page, "測試乙")
            create_subject(page, "數學", "乙數教材", "乙數問題")

            page.locator("#learner").select_option(label="測試甲")
            page.locator("#subject").select_option(label="數學")
            page.get_by_text("甲數問題", exact=False).wait_for()
            assert page.locator("#material").input_value() == "章節題目：分數加法"
            assert "乙數問題" not in page.locator("#history").inner_text()
            assert "甲英問題" not in page.locator("#history").inner_text()
            with page.expect_download() as download_info:
                page.locator("#export").click()
            download = download_info.value
            backup = json.loads(download.path().read_text(encoding="utf-8"))
            assert backup["subject"]["material"] == "章節題目：分數加法"
            assert backup["subject"]["materialSource"]["name"] == "chapter.md"
            assert len(backup["attempts"]) == 1
            assert backup["attempts"][0]["question"] == "甲數問題"

            page.locator("#importFile").set_input_files({
                "name": "synthetic-backup.json",
                "mimeType": "application/json",
                "buffer": json.dumps(backup, ensure_ascii=False).encode("utf-8"),
            })
            page.get_by_text("匯入成功", exact=False).wait_for()
            assert page.locator("#contextTitle").inner_text() == "測試甲（匯入） / 數學"
            assert page.locator("#material").input_value() == "章節題目：分數加法"
            page.reload()
            page.locator("#learner").select_option(label="測試乙")
            page.locator("#subject").select_option(label="數學")
            page.get_by_text("乙數問題", exact=False).wait_for()
            assert page.locator("#material").input_value() == "乙數教材"
            assert "甲數問題" not in page.locator("#history").inner_text()
            context.close()

            other = browser.new_context()
            other_page = other.new_page()
            other_page.goto(origin)
            assert other_page.locator("#learner option").count() == 1
            other.close()
            print(f"PASS: browser E2E, Chromium {browser.version}, synthetic scope separation/export/import")
        finally:
            print('SMOKE: closing browser', flush=True)
            browser.close()
            print('SMOKE: browser closed', flush=True)


if __name__ == "__main__":
    run()
