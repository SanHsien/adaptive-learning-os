"""Non-destructive local browser smoke using synthetic learners only.

Requires: pip install playwright; an installed Chrome browser.
Run: python tools/browser_smoke.py
"""

import json
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def local_server():
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
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
        browser = playwright.chromium.launch(channel="chrome", headless=True, timeout=20000)
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(origin, wait_until="domcontentloaded")
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
            browser.close()


if __name__ == "__main__":
    run()
