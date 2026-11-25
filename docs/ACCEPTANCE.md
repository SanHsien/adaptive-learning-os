# 驗收清冊

## 本機自動化

2026-11-25：Windows `.\.venv\Scripts\python.exe -u tools/real_whisper_inference_cancel_smoke.py --cycles 1 --duration-seconds 20 --first-segment-timeout 100` 退出碼 0。修改前首次片段約 21.24 秒、程序樹取樣 Working Set 峰值 602.2 MiB；Windows worker 改採暫停建立、Job 指派後恢復執行後，再測首次片段 18.47 秒、Working Set 取樣峰值 651.3 MiB、取消至清理約 0.07 秒、子程序退出及暫存清除均通過。Python 17/17、Node 33/33 通過。45 秒合成音訊曾在 100 秒內未觀測到首段，仍需調查；跨 Windows 版本與持續負載尚未驗收。

2026-11-24：針對 GitHub Linux CI `dabccb5` 的工作槽釋放時間競爭，`tools/test_local_server.py` 在每次測試開始與連續取消後，最多等待 5 秒確認 `server.active` 已釋放，逾時仍判定失敗。這保留清理缺陷偵測，並避免將 HTTP 先回覆造成的短暫狀態誤報為資源洩漏。最終 CI 結果以新提交為準。

2026-11-24：Windows `.venv` 真實 faster-whisper small 合成語音，`python -u tools/real_whisper_inference_cancel_smoke.py --cycles 3` 三輪均 PASS，程序退出碼 0。首次解碼後至取消期間，三輪各取樣 5／5／6 次，程序樹 Working Set 峰值 589.0／582.4／589.8 MiB、程序樹累積 CPU 187.28／169.84／184.78 秒、最大程序數均 2；每輪 HTTP 取消與 POST 回覆、工作槽、子程序退出和暫存清理皆通過。CPU 是程序已累積的計數，取樣僅涵蓋首次解碼之後，不能推論完整執行期間記憶體峰值或長期穩定性。本機 Node 33/33、Python 16/16 通過。GitHub `bc57f58` CI、CodeQL 均成功，前版 `c04123a` CI 失敗的兩項 Linux 測試待追蹤偶發性。

2026-11-23：新增 OCR 連續兩次在辨識已開始後取消、第三次重新辨識成功的合成 Worker 測試，逐 Worker 檢查 `terminate()` 呼叫次數。這是 Node 模擬測試，不代表已量測瀏覽器內真實 Tesseract Worker 的取消時間或資源使用量。

瀏覽器測試新增對真實 Tesseract `createWorker`、`recognize`、`terminate` 的非替代式計數包裝；測試須在 `recognize()` 確實啟動後才切換科目或學習者，確認舊教材未跨 scope 出現且 Worker 各終止一次。此計數不等於 Worker 終止耗時測量。

2026-11-23：進一步觀測真實 `worker.terminate()` Promise 的完成與 `performance.now()` 毫秒耗時；跨科目、跨學習者兩次取消各檢查呼叫與完成數相同、沒有終止錯誤，且單次小於 15 秒。這是瀏覽器內終止方法的耗時，不等於 OS 層級記憶體已全數回收。

本次 Chromium 149 瀏覽器實測兩次終止耗時分別約 0.1 ms、0.2 ms，測試退出碼 0；此數值僅反映包裝的 Promise 完成時間，不能推論實際 OCR 資源回收速度或長時間穩定性。

2026-11-23：Chromium Headless Shell 149.0.7827.55 執行 `python -u tools/browser_smoke.py`，跨科及跨學習者兩輪取消均在真實 `recognize()` 進入後進行，均確認舊內容不越界且 `terminate()` 各一次；瀏覽器正常關閉、Python 退出碼 0。`npm ci`、`npm test`（31/31）、JS/Python 語法檢查與 `git diff --check` 通過。尚未量測實際資源釋放耗時與長時間反覆操作。

執行 `npm ci`、`npm test` 及 `node --check` 檢查 `src/`、`tests/` 內 JavaScript。必測性質：不同 learner/subject 的教材與作答不可混查、不可跨 scope 修改、匯入建立新副本、無效備份拒絕、家教提示限單一 scope。

## 真實瀏覽器：已完成合成資料基本驗收（2026-11-22）

執行 `python tools/browser_smoke.py`，Playwright + Google Chrome Chromium 157.0.8103.80，結果 `PASS`，退出碼 0。覆蓋新增甲乙學習者、各科教材與作答、切換 UI、單科 JSON 匯出、隔離式匯入、重新整理保留、全新瀏覽器 context 無原資料。此結果僅證明基本功能流程，不代表帳號安全隔離、真實資料或所有瀏覽器可用。

在 localhost 啟動靜態伺服器，以乾淨的瀏覽器 profile 手動或自動執行：

1. 建立甲/乙兩位學習者，各建數學，甲另建英文；存入彼此不同的無敏感文字教材。
2. 每個 scope 各存一筆不同作答；切換後只顯示該 scope 的內容與正確複習日期。
3. 匯出甲數學，不包含甲英文、乙數學；匯入後新增獨立家人與科目，原資料不變。
4. 重新整理頁面後資料保留，使用全新瀏覽器 profile 則看不到舊 profile 的資料。
5. 只用合成資料；記錄測試日期、瀏覽器版本與結果。其他瀏覽器、人工可用性與各檔案格式匯入仍待驗證。

## 資料完整性回歸（2026-11-22）

`npm test` 共 13 項通過：拒絕偽造 learner/subject/scope/id 欄位、拒絕空白作答及超長教材、拒絕畸形匯入並確認沒有新增部分學習空間；另覆蓋同科並行儲存版本遞增與跨 scope 拒絕。Playwright 合成資料瀏覽器測試已覆蓋 Markdown 匯入預覽、確認儲存、匯出與隔離式匯入。PDF、Word、圖片及影音解析仍屬 ROADMAP P0 待辦。

## PDF 與 DOCX 匯入（2026-11-22）

已實作本機 PDF 與 DOCX 擷取器。PDF.js 關閉 eval、逐頁擷取並限制 100 頁；無文字層頁面可執行本機 OCR（最多 20 頁）。檔案限制 8 MB，內容限制十萬字元。擷取失敗不得寫入既有教材，預覽後仍需手動儲存。

2026-11-22：Chrome 157.0.8103.80 執行 `python -u tools/browser_smoke.py` 結果 PASS。使用程式生成的 PDF／DOCX 測試選檔、文字預覽、確認儲存與來源顯示；損壞 PDF／DOCX 測試確認解析錯誤不覆蓋已儲存教材。掃描 PDF 單頁合成測試見下方；尚未涵蓋真實世界複雜文件與所有格式邊界。

## 圖片教材預覽與人工輸入（2026-11-22）

PNG、JPEG、WebP 須驗證副檔名、檔頭及 8 MB 上限；圖片僅用本機 blob URL 暫時預覽，不保存原圖。可執行本機 OCR，也可人工輸入；確認後才可儲存並記錄圖片來源；切換學習空間即清除預覽。2026-11-22：Chrome 157 合成圖片端到端測試 PASS（選檔、預覽、OCR、人工修正、儲存、來源顯示與清除預覽）。真實圖片與所有格式邊界仍待驗證。

## 本機繁體中文 OCR 與掃描 PDF（2026-11-22）

OCR 接入 `AbortSignal`，切換家人／科目或改選檔案時中止舊辨識並清理 Worker。`tests/ocr.test.js` 以合成 Worker 確認取消後不交付結果且只清理一次，並驗證初始化期間取消後仍可清理 Worker；PDF 渲染可取消。2026-11-22：27 項 Node 測試通過，Chrome 157 合成資料 E2E 通過；大型真實掃描的中止速度仍須壓力測試。

新增文字檔讀取及 DOCX 解碼完成前取消的負向測試；掃描 PDF 頁面轉為 PNG 後再次檢查取消，PDF 文字層擷取後也會檢查取消。仍未證實長檔與混合型 PDF 在真實瀏覽器中的中斷性能。

後續增補 `tools/browser_smoke.py` 合成三頁 PDF（文字層→影像掃描→文字層），驗證頁碼、順序、掃描頁非空文字及人工確認保存來源 `mixed.pdf`。曾以八頁掃描 PDF 測試匯入時切換至另一科；UI 檢查雖未出現跨科覆蓋，Chrome `browser.close()` 階段卻持續阻塞，整體無法視為驗收成功。長檔取消須另行定位資源清理問題並復測，不能僅憑 UI 顯示 PASS 判定完成。

2026-11-22 追加：`src/ocr.js` 清理改為共用同一個終止 Promise，測試以延後完成的 `terminate()` 驗證取消後不會提早返回。`npm ci` 成功、`npm test` 30/30 通過、JavaScript `node --check` 與 `git diff --check` 通過。執行 `python -u tools/browser_smoke.py` 時混合型 PDF 與隔離／匯入操作均輸出 PASS，但執行程序未自行退出，最終以 Ctrl-C 中斷（exit 1）；**完整 Chrome E2E 仍未通過**。已新增 browser 關閉前後階段記錄，下一輪應以獨立程序對照無 OCR／圖片 OCR／掃描 PDF／混合 PDF 的退出行為。

獨立最小基準再現：使用 Playwright 同步 API 啟動 Chrome，僅呼叫 `new_context()`、`context.close()` 與 `browser.close()`，不載入專案、不執行 OCR/PDF，輸出 `start`、`launched`、`closing` 後仍卡住，需中斷。另一個基準在 `page.goto('about:blank')` 發生 30 秒 timeout。這些結果顯示本機 Playwright／Chrome 環境自身也有問題，不能將瀏覽器阻塞直接歸咎於 OCR Worker；後續應先檢查瀏覽器版本與 Playwright 相容性及乾淨瀏覽器程序的退出情況。

2026-11-23：使用 Python Playwright 1.65.2 與本機已安裝的 Chromium Headless Shell 149.0.7827.55，指定環境變數 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向其 `chrome-headless-shell.exe` 後，完整 `python -u tools/browser_smoke.py` 退出碼為 **0**，含圖片 OCR、掃描與混合 PDF、八頁掃描 PDF 選檔後切換科目的合成驗收。該取消案例檢查新科目始終空白、切回數學原教材及來源仍存在；不代表已量測長時間運作中的 Worker 實際終止延遲。無須修改生產 OCR 演算法來規避系統 Chrome 的阻塞。預設仍使用系統 Chrome；可透過此環境變數選擇獨立瀏覽器作診斷，且需自行確認執行檔來源與版本。Playwright 預設預期的 Chromium 1255 尚未安裝，故該版本尚未驗證。

Chrome 157 曾執行 `python -u tools/browser_smoke.py` 退出碼 0：利用合成圖片執行繁體中文 OCR，確認非空辨識結果、人工校正後保存圖片來源；另以 Pillow 生成單頁**沒有文字層**的掃描 PDF，經 PDF.js 渲染 + Tesseract.js 辨識，確認逐頁文字預覽、人工儲存及來源保留。混合頁測試新增後亦曾完整退出碼 0，但後續重跑觀察到偶發瀏覽器關閉阻塞，需獨立調查。OCR 必須使用 `vendor/ocr` 的 Worker、WASM 與 `chi_tra.traineddata.gz`，不依賴外部辨識服務。限制：OCR 結果須人工校對；仍未涵蓋複雜掃描、批次大型 PDF、長時間 OCR 真正中止與跨 scope 非同步操作的完整壓力驗收。舊備份允許引用已遺失全文的歷史版本，但不會憑空重建其內容。

## 正式家庭使用：阻擋條件

## 影音暫時播放與人工逐字稿（2026-11-22）

MP3/WAV/M4A/MP4/WebM 限制 100 MB 並驗證檔案簽章，播放以本機 blob URL 進行；未填逐字稿不得將影音來源存成已解析教材，切換 scope 清除暫存媒體。`npm test` 涵蓋格式與拒絕案例；自動語音轉錄尚未提供。瀏覽器端影音播放及切換流程須另行驗證。

## 教材版本模型（2026-11-22）

IndexedDB v2 新增 `materials` store，版本寫入同一交易；版本完整內容、來源、SHA-256、確認狀態及時間戳記可由同科查閱，作答保留教材版本。JSON 備份包含版本歷程並可相容舊 v1 備份。`npm test` 包含版本歷程、跨學習者拒絕、備份還原及舊格式相容測試。舊資料歷史上被覆寫的內容無法恢復。

`tests/migration.test.js` 直接建立 v1 IndexedDB，測試升級後原本的科目、舊作答與版本 3 均保留，首次儲存新版後版本歷程為 3、4；跨學習者讀取仍遭拒。影音人工輸入逐字稿時應繼續保留原始影音來源，不可因文字輸入事件清除來源標記。

必須完成身份驗證、後端逐請求授權、負向跨帳號測試、備份/刪除機制，以及隱私和第三方 AI 資料傳送檢視，才能宣稱具備家人間的安全隔離。

# 影音本機轉錄增量驗收（2026-11-23）

2026-11-24：`python -u tools/real_whisper_resource_smoke.py --duration-seconds 90` 於 Windows 真實 Whisper small CPU int8 以 SAPI 本機合成約 90 秒中文 WAV 測試；完整 Python 退出碼 0，輸出 `PASS`，wall 94.6 秒、取樣程序樹 CPU 212.56 秒、峰值 Working Set 1029.1 MiB、最多 2 程序、324 次取樣。工具提供 30 至 180 秒可選長度。取樣與測試期間限定於單一機器，仍須驗收跨硬體、長期穩定性與資源上限。

2026-11-24：擴充 `tools/real_whisper_inference_cancel_smoke.py`，可使用 `--cycles 2` 在同一 LocalServer 執行兩輪真實 Whisper small 推論取消，使用 Windows SAPI 合成語音。兩輪皆於第一個已解碼 segment 產生後觸發取消、HTTP DELETE 回傳 200、上傳原請求回傳 409、子程序退出、暫存目錄清除、任務槽釋放。實測印出 `PASS` 兩次且 Python 退出碼 0。測試仍不涵蓋多小時影音、跨硬體資源上限或真實家人教材。

2026-11-24：`tools/test_local_server.py` 增加同一 HTTP 服務連續三輪真實 Python 子程序取消與恢復測試。每輪檢查併行請求 409、DELETE 200、取消請求 409、子程序結束、暫存資料夾消失及任務槽釋放，最後以 mock 成功轉錄確認服務恢復。Python unittest 16/16 通過。這不涵蓋真實 Whisper 模型多次長影音取消，仍須獨立驗收。

2026-11-24：新增 `python -u tools/real_whisper_resource_smoke.py` 可選用 Windows 真模型資源量測。先前僅量啟動程序取得 4.8 MiB 等異常數字，已改為 Toolhelp32 追蹤整個程序樹，並用 Windows Process API 分別量測 Working Set 與 CPU 時間。約 45 秒 SAPI 合成中文語音以 faster-whisper small CPU int8 轉錄，退出碼 0，耗時 44.32 秒、154 次取樣、CPU 累積 165.41 秒、取樣記憶體峰值 1025.4 MiB、最多同時 2 個程序。CPU 是每程序觀測到的最高累積值合計，Working Set 是瞬時樹狀合計取最大值，不包含其他系統程序及模型快取；需另測多次取消、較長影音、跨硬體與資源上限。

2026-11-24：Windows localhost Whisper 子程序取消、逾時及關閉路徑使用 `taskkill /T /F` 對仍存活的根程序執行樹狀終止。新增真實 Python 父程序衍生睡眠子程序測試，取消後檢查兩者退出；`python -m unittest discover -s tools -p 'test_*.py'` 14/14、`npm test` 33/33 通過。仍待更長影音的 CPU／記憶體峰值及多次取消壓力測量。

2026-11-24：`python -u tools/real_whisper_inference_cancel_smoke.py`（Windows，需 `.venv` faster-whisper small 模型）使用約 45 秒 SAPI 合成中文語音，測試用 wrapper 在 Whisper 真實生成第一個 segment 時觸發 marker，確認子程序仍執行後立即 DELETE 取消。最終結果 PASS、exit 0，回傳 HTTP 409、Whisper 子程序退出、暫存資料夾移除、單一任務槽釋放。曾因測試 wrapper 的 marker 路徑錯誤無法觀測，修正後重跑才通過。此驗收覆蓋首段推論後取消，仍未測量連續長影音的記憶體／CPU 峰值、所有子孫程序與長時間重複執行穩定性。

2026-11-24：執行 `python -u tools/real_whisper_cancel_smoke.py`，以 `.venv` 真正啟動 Whisper 子程序、30 秒合成靜音 WAV 測試取消。結果 `PASS`、exit 0，驗證啟動後取消、HTTP 409、子程序退出、暫存資料夾清除、下一次合成工作可成功；另執行 `npm test` 33/33、`python -m unittest discover -s tools -p 'test_*.py'` 13/13、`py_compile` 及 `git diff --check` 通過。子程序在啟動後約 0.3 秒被取消，尚未觀測確切 Whisper 推論起點；仍須建立推論階段可觀測的長影音取消、子孫程序及資源峰值驗收。

2026-11-23：`python -u tools/browser_real_transcription_smoke.py`（Windows，`PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向已安裝 Headless Shell）以 SAPI 產生短合成中文 WAV，使用專案 `.venv` 的 faster-whisper 1.2.1／PyAV 16.1.0 及本機快取 small 模型，網頁實際觸發轉錄並產出非空辨識文字（20 字元）；人工校對後儲存，切換至另一位學習者的同名科目不顯示前者教材，切回前者恢復校對內容。輸出 `PASS`，程序退出碼 0。首輪測試在切換後立即斷言遇到非同步載入時序，改成等待指定教材內容出現後重跑通過。**未涵蓋**模型載入／推論取消、衍生程序與長影音資源上限，P0 維持未完成。

2026-11-23：`tools/test_local_server.py` 新增真正 Python 子程序的取消整合案例（非 mock），包含第二次同時請求回應 409、DELETE 回應 200、原請求回應 409、子程序退出、暫存目錄清理、任務槽釋放及下一次合成轉錄回應 200；只使用合成 WAV，不載入 Whisper 或私人教材。該案例不代表真正 Whisper 模型在 Windows 載入及推論時的取消與記憶體資源已通過。

2026-11-23：本機 HTTP 服務新增上傳 socket 15 秒閒置逾時及 `server_close()` 取消當前子程序。`python -m unittest discover -s tools -p 'test_*.py'` 12/12 通過，包含不完整上傳 Body 不佔用工作槽、關閉服務時發出取消與子程序終止通知；`npm test` 33/33 通過。這些是合成資料／mock 子程序驗證，尚未驗證 Windows 真 Whisper 子程序完全退出及長檔資源釋放。

新增 `tools/test_local_server.py`：採合成 WAV、mock Whisper 子程序，測 localhost API 的工作階段來源、Host/Origin/Token、非法格式、取消先於上傳、靜態檔白名單及完成後工作狀態；不下載模型，也不包含真實家人資料。`python -u tools/browser_transcription_smoke.py` 使用 Chromium Headless Shell 與 mock Whisper，實際點按影音上傳、一鍵轉錄、校對、指定科目儲存及轉錄中切換另一位學習者取消舊任務：`PASS`，Python 退出碼 0。**尚未證實**長影音效能、取消時所有 Windows 真實子程序退出及真實教材轉錄品質；完成前 P0 保持未結案。

2026-11-23：Windows SAPI（Microsoft Hanhan Desktop）產生短篇中文合成 WAV，以本機快取 `faster-whisper-small` 與隔離 `av 16.1.0` 執行 `python tools/transcribe_local.py`，退出碼 0，產生兩段有時間碼的 SRT：「今天我们学习中文。」及「这是人工合成的测试语音。」。原始合成語音為繁體中文，轉錄成簡體字；仍需人工校對。直接使用共用 Python 環境的 `av 19.0.2` 則遇 `av.open(metadata_errors=...)` 相容性錯誤；沒有更動共用 Python 套件。這是**真模型＋合成語音**驗收，不代表真實教材或長影音辨識品質已驗收。

Chromium 148 Headless Shell E2E 退出碼 0，新增驗證 SRT 解析、人工校對後來源保留、儲存與 JSON 備份來源、非法 SRT 拒絕、WebVTT 解析、跨學習者切換清除未儲存字幕及切回原教材。修復 `src/storage.js`、`src/core.js` 漏列字幕 MIME 類型與 `src/app.js` 校對字幕時意外清除來源。全部使用合成資料。

`python -m unittest discover -s tools -p 'test_*.py'`：SRT 產生器測試，含時間碼、空字幕、輸出既存拒絕。`npm test`：SRT/VTT 檔案驗證、字幕時間碼與來源保留。這些合成測試**不代表**真實 Whisper 模型語音辨識或瀏覽器端一鍵轉錄已通過；自動轉錄需另行安裝 `faster-whisper` 並使用真實影音人工校對驗收。

## 2026-11-25 Whisper 取消資源觀測

CI `45505627385` 揭露單次真 OS 子程序取消整合測試的 Handler `finally` 工作槽釋放競爭，單次測試改用既有五秒有界等待；等待超時仍失敗，需由更新後 CI 複核。

`tools/real_whisper_inference_cancel_smoke.py --cycles 3` 從子程序啟動後每 0.1 秒取樣程序樹，量測首次解碼前及取消清理階段的時間、取消前與全窗 Working Set 取樣峰值。每輪仍核對 HTTP DELETE 200／POST 409、子程序退出、暫存目錄刪除及工作槽釋放。CPU 為累積程序時間，無法代表分階段 CPU 成本。孤兒程序及長期負載仍待驗收。

2026-11-25 Windows 真實 faster-whisper small 三輪合成音訊驗證退出碼 0，三輪均 PASS。全窗 Working Set 取樣峰值依序為 1029.4／1027.2／1028.5 MiB，首次解碼前取樣數 312／288／266，啟動至首次解碼觀察約 43.77／41.61／37.45 秒，首次解碼觀察至清理約 0.91／1.11／1.05 秒；每輪子程序均退出、暫存目錄均清除。同期 Python unittest 16/16、Node 33/33 通過。

2026-11-25：Windows `test_orphan_descendant_is_killed_after_parent_exit` 使用真實 Python 父程序產生持續執行的子程序，父程序正常退出後關閉 Job handle，驗證子程序在五秒內消失。此為不載入 Whisper 的回歸測試，並未消除程序建立與 Job 指派之間的競爭窗口。

本次更新 Node 33/33、Python 17/17 與工具編譯檢查通過。另執行一次 `real_whisper_inference_cancel_smoke.py --cycles 1`，因 100 秒內未收到首次解碼訊號而失敗；尚無法確認是模型執行時間變異或 Job Object 整合造成。必須待真模型複測通過才可將此版列為完整的 Whisper 取消驗收。
