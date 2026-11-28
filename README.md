# 家人自修室 · Adaptive Learning OS

影音轉錄遇到解碼器標記損毀的音訊封包或影格，或 RIFF/WAVE、MP4/M4A、WebM 容器或 MP3 Xing/Info、ID3 宣告長度超過實際檔案時會拒絕，未產生逐字稿；其他未被解碼器標記的截斷仍可能無法辨識。

本機轉錄逾時後若無法確認程序終止，服務會拒絕後續轉錄；請檢查殘留程序及暫存資料，再重新啟動服務。


POSIX 本機轉錄使用獨立程序群組，正常結束、取消及逾時會清理仍在該群組內的程序；尚無整組資源硬上限或程序群組逃逸防護。

多音軌影音目前只轉錄第一條音軌，請先確認所需語言位於第一音軌。

本機 Whisper 以最多 120 秒音訊分段推論並保留全域字幕時間軸；固定分段可能切斷語句，須人工校對。轉錄限制為每次最多 60 分鐘實際解碼音訊（16 kHz mono PCM 樣本累計）、SRT 最多 100000 字元及 400000 bytes；超限停止處理，網頁回傳 HTTP 413 並提示分段轉錄。

Windows 一鍵轉錄工作使用 Job Object 回收根程序與衍生程序，已以合成 Python 父子程序驗證根程序提前退出後的清理。真 Whisper 受控異常退出已驗收；Windows Job 限制整組 committed memory 4 GiB 、8 個同時存活程序與累計 14400 秒 user-mode CPU 時間，另有獨立 1800 秒 wall-clock 逾時；長期運作與跨硬體驗收仍列於 ROADMAP。

專案規劃與驗收：[ROADMAP](ROADMAP.md) · [架構](docs/ARCHITECTURE.md) · [驗收清冊](docs/ACCEPTANCE.md) · [安全界線](SECURITY.md) · [代理工作規則](AGENTS.md)

繁體中文、無需 AI API 的自適應自修原型。**每位家人及每個科目都有獨立教材、作答、掌握證據與複習日期**。

## 立即使用

在專案資料夾執行 `npx http-server . -p 4173 -c-1`，以瀏覽器開啟 `http://localhost:4173`。請勿用 `file://` 開啟（部分瀏覽器會限制 ES modules）。

1. 新增家人並選取。
2. 新增科目並選取。
3. 貼上該科教材，或選擇 TXT、Markdown、CSV、PDF、DOCX 預覽擷取文字後點「儲存教材」。檔案內容不會自動送至外部服務。
4. 點「複製專屬家教指令」，貼到 ChatGPT、Gemini 或 Claude。
5. 練習後，手動登錄題目、作答、提示次數、結果；系統記錄掌握證據及下次複習日期。
6. 定期「匯出此人的此科資料」為 JSON。匯入備份會另外建立家人與科目副本，絕不覆寫現有學習空間。

## 資料隔離與安全邊界

- `learners`、`subjects`、`attempts` 分開儲存；每筆科目隸屬唯一學習者，作答按 `learnerId:subjectId` 索引，寫入前驗證歸屬。
- 顯示與匯出只查目前的學習者及科目。切換選擇會清空目前作答清單。
- **目前是同瀏覽器下的邏輯隔離，並非帳號登入、權限隔離或加密**。共用同一台電腦的人仍可能切換查看其他家人的資料；不適合保存敏感紀錄。
- IndexedDB 儲存在該瀏覽器、該網站來源；清除網站資料、無痕瀏覽或換裝置可能遺失紀錄。請定期匯出備份。
- 教學提示詞只放目前學習空間的資料；複製後會送往你自行選擇的 AI 平台，請先檢查內容。
- 原型不連結 GitHub 帳號、不呼叫 AI API、不提供跨裝置自動同步。

## 功能邊界及後續教材

目前支援**貼上純文字或從本機匯入 TXT、Markdown、CSV（1 MB 內）、PDF、DOCX（8 MB 內）**，擷取結果以十萬字元為上限。PNG、JPEG、WebP（8 MB 內）可暫時預覽、按「本機 OCR 辨識繁體中文」及人工校對；原圖不會保存或備份。PDF 文字頁直接解析，無文字層的掃描頁以本機 OCR 擷取（每份 PDF 至多 20 頁需 OCR，總頁數最多 100 頁）。首次辨識可能需要額外載入本機語言模型；辨識結果可能出錯，必須校對後明確按「儲存教材」。MP3、WAV、M4A、MP4、WebM（100 MB 內）可暫時播放並**人工輸入逐字稿**；啟動下述本機 Python 服務後，也可用測試版「本機一鍵轉錄」產生草稿。原始影音不會永久保存。PDF、Word、OCR 引擎與繁體中文模型均隨專案提供，不需要外部 OCR API。舊式 `.doc` 請先轉存 `.docx`；**影音轉錄仍為 [ROADMAP](ROADMAP.md) P0 驗收中功能**。每次儲存會產生新教材版本，保留舊版全文、來源、SHA-256 與確認狀態；單科 JSON 備份包含版本歷程，舊備份亦可匯入。

目前的「答對／需補強」是使用者自評，不是 AI 自動批改。掌握層級是簡單證據標示，不是經校準的能力百分比。複習間隔 1、3、7、14 天是待驗證的預設，不是個人化最優排程。

## 測試

### 網頁內一鍵轉錄（本機測試版）

Windows 轉錄工作以暫停狀態建立子程序，將其加入 Job Object 後才恢復執行，以確保從開始執行起即受程序生命週期管理。真模型取消驗收可用 `--duration-seconds 20`（20–90 秒）縮短合成音訊，並用 `--first-segment-timeout 100`（30–300 秒）設定首次解碼等待上限。該啟動流程採用 Windows `NtResumeProcess`，跨版本相容性與長期壓力仍待驗證。

在專案根目錄的獨立 Python 環境安裝 `faster-whisper==1.2.1` 及 `av==16.1.0`，執行 `python tools/local_server.py`，再開啟 `http://127.0.0.1:4173`（**不要**使用 `localhost` 或另開 `npx http-server`）。選擇家人及科目、匯入 100 MB 以內的 MP3/WAV/M4A/MP4/WebM，點「本機一鍵轉錄」。產生文字預覽後請人工校對，再明確按「儲存教材」。切換人、科目或檔案會取消舊任務；原始影音只寫入系統暫存資料夾，工作結束會清理。此流程需要本機 Python 程序保持執行，不會自動安裝模型；第一次載入模型可能連線下載權重。請不要用真實敏感教材測試。

這是單機測試功能，不提供公開服務或帳號安全隔離。CLI 仍可獨立使用；既有靜態網站模式只能人工輸入或匯入字幕。可執行 `python -m unittest discover -s tools -p 'test_*.py'` 檢查本機 HTTP 介面，或 `python tools/browser_transcription_smoke.py` 使用 Playwright 與合成影音驗證按鈕流程；兩者均不需要載入模型。

本機服務會在上傳連線閒置 15 秒後結束該請求，服務關閉時嘗試中止當前轉錄。Windows 已以合成語音通過真正 Whisper Small 的網頁轉錄、人工校對儲存、跨學習者隔離 E2E（`python tools/browser_real_transcription_smoke.py`，需獨立 `.venv` 和 Windows SAPI）。另可選用 `python -u tools/real_whisper_inference_cancel_smoke.py --cycles 3` 連續三輪驗證真模型首次解碼後取消、暫存清理及任務槽恢復；預設 `--cycles 1`。工具自 Whisper 子程序啟動後開始每 0.1 秒取樣，輸出取消前及全窗程序樹 Working Set 取樣峰值、累積 CPU、程序數、啟動至首次解碼及解碼至清理的耗時。取樣值可能遺漏瞬間峰值，孤兒程序及長期運行穩定性仍待驗收。

Windows 可額外執行 `.venv/Scripts/python.exe -u tools/real_whisper_resource_smoke.py --duration-seconds 90`，以指定長度的本機合成中文語音量測實際 Whisper CPU 時間及整個 Python 程序樹的記憶體峰值。可選擇 30 至 3600 秒，預設為 45 秒，轉錄 wall-clock 上限為 1800 秒。CPU 完整一小時真模型測試曾因記憶體配置失敗，分段後仍逾 1800 秒；RTX 3060 的 30 秒 GPU 工作程序測試已通過，首次完整一小時 GPU 推論產出 SRT，但時間軸驗證失敗；時間碼修正後一小時 GPU 複測通過（535.77 秒、979 段字幕）。可使用 `--device cuda` 選擇測試裝置，需自行在專案虛擬環境準備 CUDA 12 cuBLAS 與 cuDNN 9；HTTP 服務仍預設 CPU。需有專案 `.venv` 的 faster-whisper small 模型與 Windows SAPI；輸出是單次測試數據，其中 Working Set 取樣值與 Job 的 committed memory 硬上限不同。原始合成音訊及字幕於測試結束後刪除。

### 本機影音自動轉錄（選用）

已有 **SRT／WebVTT 逐字稿匯入**。想把 MP3、WAV、M4A、MP4、WebM 轉成逐字稿，可在個人電腦（不是網頁伺服器）以獨立 Python 環境安裝 `python -m pip install "faster-whisper==1.2.1" "av==16.1.0"`，然後執行：

```powershell
python tools/transcribe_local.py "C:\path\lesson.mp3" --model small --language zh
```

此指令在影音旁建立 `lesson.srt`，已存在則拒絕覆寫。回到網站，先選擇**正確學習者與科目**，再把 SRT 當教材匯入、校對文字並按「儲存教材」。原始影音不會儲存進網站；每科保留逐字稿來源和版本。可選 `--device cuda` 使用受支援的 NVIDIA CUDA 環境；CPU 使用預設 `int8`。首次安裝／使用指定模型可能從網路**下載模型權重**，不會上傳音訊；如需完全離線，先在可信環境下載模型，再以 `--model` 指向本機模型資料夾。轉錄中文不保證都是繁體字，需人工校對。這是可選用的 **CLI 工具**；網站的一鍵轉錄則須另外啟動本機 Python 服務。

測試轉錄工具自身：`python -m unittest discover -s tools -p 'test_*.py'`（使用合成時間碼、不下載模型）。

`npm test`：檢查跨人跨科隔離鍵、歸屬拒絕、學習證據、匯入驗證及教學提示詞。`python tools/browser_smoke.py`：使用 Playwright、Chrome、Python Pillow 在本機以合成圖片與掃描 PDF 驗收 OCR；不含家人真實資料。

如果系統 Chrome 的 Playwright 關閉流程阻塞，可設定 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 為已安裝且可信任的 Chromium 執行檔絕對路徑再執行相同測試。測試的完整成功條件是 Python 退出碼 0；輸出 `PASS` 但程序未結束不算通過。

## 部署

靜態網站可部署到 GitHub Pages，但 GitHub Pages 是公開入口，並不提供家人的私人登入權限。若要實際讓多位家人各自在不同裝置操作、彼此不可查看學習資料，需要下一版導入帳號登入、伺服器端權限驗證、雲端資料庫與備份加密；**不得將本機 IndexedDB 的邏輯隔離誤認為安全隔離**。

OCR 資源診斷：`python -u tools/browser_ocr_resource_smoke.py --cycles 100`，沿用上述 Playwright 瀏覽器設定；驗證 Worker 建立與銷毀、取消結果及本機請求，Windows 另取樣 CDP 回報程序的記憶體。此為合成圖片診斷，不代表長期記憶體驗收。

短視訊真模型驗收可執行 `.venv/Scripts/python.exe -u tools/real_whisper_video_smoke.py`（Windows SAPI、專案 Whisper small 與本機 FFmpeg，需支援 MPEG4/AAC、VP8/Opus 編碼）。以合成中文語音和畫面測試 MP4/WebM，檢查解碼樣本與字幕時間軸。

CPU 批次轉錄目前為選用功能：啟動服務時加上 `--batched`（`python tools/local_server.py --batched`）。短合成語音已通過真實瀏覽器流程驗收；長影音 HTTP 與多樣教材辨識品質仍在驗收中。一般推論維持預設。
長音訊 HTTP 驗收可執行 `.venv/Scripts/python.exe -u tools/real_whisper_http_smoke.py --duration-seconds 3600`（Windows 合成語音）；檢查正式服務回傳的字幕時間軸及工作槽釋放。
