# 架構與資料歸屬

本機 Whisper 轉錄限制為每次最多 60 分鐘實際解碼音訊（16 kHz mono PCM 樣本累計）、SRT 最多 100000 字元及 400000 bytes；超限停止處理，網頁回傳 HTTP 413 並提示分段轉錄。

## 系統總覽

純前端靜態網站：沒有後端、沒有 AI API、沒有遙測。所有解析、OCR、儲存都在使用者的瀏覽器內完成；唯一會離開裝置的是使用者自己按「複製」後貼到外部 AI 平台的提示詞，以及自己按「匯出」的 JSON 檔。

```text
┌──────────────────────────── 瀏覽器（同一個網站來源）────────────────────────────┐
│                                                                                │
│  index.html + styles.css                                                       │
│        │                                                                       │
│        ▼                                                                       │
│  src/app.js ── 畫面、事件、目前選取的 learner/subject、blob URL 生命週期        │
│     │            │                    │                       │                │
│     ▼            ▼                    ▼                       ▼                │
│  core.js     storage.js        material-import.js          ocr.js              │
│  規則與驗證   IndexedDB v2      檔案驗證與文字擷取          本機 OCR             │
│  （純函式）   讀寫前查歸屬       TXT/MD/CSV、PDF、DOCX       Tesseract.js 7       │
│     ▲            │               圖片／影音檔頭檢查          chi_tra 模型         │
│     └────────────┴──── 驗證規則與上限常數來自 core.js ───────┘                  │
│                  │                    │                       │                │
│                  ▼                    ▼                       ▼                │
│            IndexedDB            vendor/pdf.min.mjs       vendor/ocr/           │
│      learners / subjects /      （動態 import）          worker + wasm core    │
│      attempts / materials       vendor/mammoth…（<script>）+ 語言資料（本機載入）│
└────────────────────────────────────────────────────────────────────────────────┘
        │ 使用者手動                         │ 使用者手動
        ▼                                    ▼
  複製家教提示詞 → 自選的 ChatGPT／Gemini／Claude     匯出單一 scope JSON 備份
```

## 模組職責

可選用的本機轉錄資料流（未經人工儲存不進 IndexedDB）：

```text
Browser (learnerId + subjectId) -> 127.0.0.1:4173 (session token)
  -> POST media + job UUID -> temporary media -> Whisper subprocess
  -> SRT response -> subtitle parser -> editable preview
  -> user confirmation -> scoped IndexedDB material/version
  \-> scope switch -> DELETE job -> terminate subprocess + cleanup
```

`tools/local_server.py` 同時提供白名單靜態資源及短暫轉錄 API；每個任務只能有一個子程序，取消與錯誤會清理暫存，並以取消旗標防止舊資料交付。來源／權杖防護不是帳號級授權，不可公開部署。

影音增量（2026-11-23）：`tools/transcribe_local.py` 是獨立的本機 CLI，可選用 `faster-whisper` 轉錄為 SRT；不連接瀏覽器，也不保存或上傳影音。`material-import.js` 解析 SRT／WebVTT 並將文字、來源送回現有的 `app.js` 校對流程，由 `storage.js` 依當前 `learnerId/subjectId` 驗證歸屬與版本化。原始媒體不進 IndexedDB；若使用 CLI 產生的 SRT，該字幕檔由使用者在自己的裝置保管。

| 模組 | 職責 | 不做的事 |
|---|---|---|
| `src/core.js` | 純函式：名稱正規化、ID、`scopedKey`、`ensureOwner` 歸屬檢查、教材／作答／備份驗證、掌握證據等級、複習日期（1/3/7/14 天）、家教提示詞組裝 | 不碰 DOM、不碰 IndexedDB，方便在 Node 直接測 |
| `src/storage.js` | IndexedDB（`DB_VERSION = 2`）四個 store；每個寫入／讀取 scope 資料前先 `ensureOwner`；教材版本化（全文＋來源＋SHA-256）；單 scope 匯出、匯入時建立新 learner/subject ID | 不信任 UI 傳來的選取值；匯入不覆寫既有資料 |
| `src/material-import.js` | 依副檔名與檔頭驗證檔案與大小上限；TXT/MD/CSV 直接讀、PDF 動態載入 PDF.js（無文字層的頁交給 `ocr.js`）、DOCX 用 `index.html` 以 `<script>` 載入的 Mammoth（`globalThis.mammoth`）；圖片與影音只驗證不保存 | 不把「已選檔案」當成「已理解教材」；失敗不留部分資料 |
| `src/ocr.js` | 像素上限檢查（2000 萬、最長邊縮到 2200 px）；用本機 `vendor/ocr/` 的 worker、wasm core、`chi_tra` 模型辨識 | 不連第三方 OCR 服務 |
| `src/app.js` | 介面狀態、事件綁定、預覽與人工校對流程、切換人或科目時撤銷 blob URL | 介面層另有幾項早期攔截（作答提示次數 0–99 與類型、備份檔 4 MB 上限、選取科目歸屬），歸屬與作答欄位在 `storage.js`／`core.js` 會再驗一次，不靠介面這層 |

相依方向（無循環）：`app.js → {storage, material-import, ocr}`、`material-import → ocr`，三者再 `→ core.js`。`core.js` 不依賴任何模組。

## 測試與 CI

```text
tests/core.test.js            隔離鍵、跨人拒絕、掌握證據、備份驗證、提示詞只含指定科目、複習日期
tests/storage.test.js         fake-indexeddb：跨人跨科隔離、匯入獨立副本、owner/scope 不可偽造、失敗不留部分資料
tests/migration.test.js       IndexedDB v1 → v2 升級保留舊教材與作答
tests/material-import.test.js 文字／DOCX 擷取、取消中止、圖片與影音檔頭、DOC 與空檔拒絕
tests/ocr.test.js             影像大小上限、取消時終止 Worker
tools/browser_smoke.py        真實 Chrome + Playwright，合成圖片與掃描 PDF 驗收 OCR（本機手動跑）
```

CI（`.github/workflows/ci.yml`）在 push／PR 到 `main` 或手動觸發（`workflow_dispatch`）時跑 `npm ci`、`npm test`（`node --test`）與所有 `src/*.js`、`tests/*.js` 的 `node --check`。瀏覽器煙霧測試不在 CI 內，結果要另外回報。

## 第三方元件

`vendor/` 內的 PDF.js、Mammoth、Tesseract.js（含 wasm core 與 `chi_tra` 語言資料）隨專案附帶，授權檔放在同目錄（`pdfjs-LICENSE.txt`、`mammoth-LICENSE.txt`、`ocr/core/LICENSE`、`*.LICENSE.txt`）。`package.json` 的 devDependencies 只用來取得與更新這些檔案，執行期不經過 npm 或 CDN。

## 資料模型

```text
使用者 / 瀏覽器
       |
       v
 index.html + styles.css + src/app.js (操作與畫面)
       |                         |
       v                         v
 src/core.js (規則、提示詞)   src/storage.js (IndexedDB)
                                     |
                        +------------+------------+
                        |            |            |
                     learners      subjects     attempts
                       id        id,learnerId  learnerId,subjectId,scope
```

`learnerId` 指定學習者；每個 subject 僅屬於一個 learner；`scope = learnerId:subjectId` 用於查詢作答。讀寫教材、作答及匯出前仍需檢查 subject 歸屬，不能只信任 UI 目前選取的值。匯入備份建立新 learner 與 subject ID，避免覆蓋既有 scope。

## 目前資料流

```text
選擇家人 -> 選擇科目 -> 儲存純文字教材
                         |-> 複製限定 scope 的 AI 家教提示
                         |-> 登錄作答 -> 計算掌握證據與複習日期
                         +-> 匯出單一 scope JSON
匯入單一 scope JSON -> 格式檢查 -> 建立新家人/科目與作答副本
```

目前沒有後端與自動 AI API；subject 的 `material`、`materialVersion`、`materialSource` 保留目前最新版供舊程式使用。IndexedDB v2 新增 `materials` store，以 `learnerId:subjectId` scope 索引保存每版全文、來源、SHA-256、確認狀態、建立時間；作答紀錄保留當時 `materialVersion`。升級舊資料庫後，第一次更新舊科目會保留既有最新版；無法憑空還原升級前已被覆蓋的更早版本。JSON 備份沿用 v1 schema，新增選用 `materialVersions` 欄位並相容舊備份。固定複習間隔不代表已校準的個人化模型。

## 後續資料模型設計限制

### P0：檔案教材匯入設計

圖片 PNG/JPEG/WebP 透過檔頭驗證後以暫時性 blob URL 在當前科目預覽；`src/ocr.js` 使用本機 Tesseract.js 7 + `chi_tra` 語言資料進行 OCR，最多 2000 萬像素並縮至最長邊 2200 px；辨識後須人工校對才可寫入 IndexedDB，來源記錄圖片檔名與格式，不保存圖片二進位內容。PDF.js 對有文字層的頁面直接擷取，沒有文字層的頁面繪製為 Canvas 交由相同 OCR 辨識；PDF 最多 100 頁，其中需 OCR 的頁面不超過 20 頁。OCR 資源由 `vendor/ocr/` 本機載入，不透過第三方服務。影音 MP3/WAV/M4A/MP4/WebM 驗證檔頭及 100 MB 上限，以暫時性 blob URL 播放，人工輸入逐字稿確認後保存文字；切換家人或科目撤銷圖片及影音暫存 URL。已提供選用的 localhost Whisper 自動轉錄，結果須人工校對；Windows Job 整組 committed memory 上限為 4 GiB、同時程序數上限為 8，整組累計 user-mode CPU 時間上限為 14400 秒，另有獨立 1800 秒 wall-clock 轉錄逾時。

已完成 TXT/Markdown/CSV、PDF（PDF.js + 掃描頁 OCR）、DOCX（Mammoth）、圖片（Tesseract.js）的純瀏覽器擷取、預覽與確認儲存。程式碼及模型隨專案附帶，辨識不連接第三方服務。待辦：自動影音轉錄與正式家用帳號授權。Word `.doc` 二進位格式須轉檔為 DOCX。不得以「檔案已選取」等同「已成功理解教材」。

所有來源先在使用者裝置內解析；若日後需要雲端辨識或 AI，必須明確揭露資料去向並取得同意。每次匯入產生獨立教材版本與解析狀態（待處理/成功/需人工確認/失敗），記錄原始檔名、媒體類型、內容摘要、學習者與科目；不可默默覆蓋既有教材。大型與不支援檔案應拒絕並保留先前資料。圖片沒有可用 OCR 或影音沒有逐字稿時，顯示「尚未擷取內容」，不得把空白當作已學習。

- 教材檔案需保留 `learnerId`、`subjectId`、source、version、hash 與 parser 狀態；相同科目也不得跨 learner 共用內容，除非使用者明確選擇複製。
- 任務與評量須以 scope + material version 關聯來源，避免新版教材覆蓋舊證據的語境。
- 引入同步服務前先定義帳號身分、權限、衝突解決、刪除/復原及備份版本規範；瀏覽器端檢查不得替代後端授權。
