# 安全與隱私界線

2026-11-28：新增 WebM EBML 頂層元素宣告長度檢查，保留合法未知長度 Segment。實測 PyAV 16.1.0 合成 Opus WebM 截半原可回傳 16536 樣本，修正後於模型建立前拒絕且無 SRT。正常 WebM 解碼及未知長度標頭測試通過。MP3 截半原可回傳 15760 樣本，尚待處理；未知長度 Segment 的內部截斷仍可能無法辨識。Python 33 項通過、1 項 POSIX 跳過，Node 35 項通過，npm ci、語法及 diff 檢查通過。前版 69e51bd CI/CodeQL 成功，未解決警示 0 項。

2026-11-28：新增 MP4/M4A ISO BMFF 頂層區塊長度檢查，支援 32-bit、64-bit 延伸及合法延伸至 EOF 的區塊。合成 faststart AAC 於完整封包邊界截斷時，拒絕於模型建立前且不產生 SRT；正常檔案可解碼。Windows Python 31 項通過、1 項 POSIX 跳過，Node 35 項通過，npm ci、語法及 diff 檢查通過。前版 6546794 CI/CodeQL 成功且未解決警示 0 項（前輪查證）。頂層長度一致或 EOF 區塊仍可能存在無法偵測的截斷；MP3/WebM 與完整一小時真模型推論待驗收。

2026-11-28：新增 RIFF/WAVE 宣告長度檢查。合成 PCM WAV 在完整封包邊界截斷時，PyAV 19.0.2 原先無損毀標記且仍回傳部分音訊；修正後於模型建立前拒絕，未產生 SRT。Windows PyAV 16.1.0（與 CI 固定版本相同）Python 29 項通過、1 項 POSIX 跳過；Node 35 項通過、語法檢查通過。前版 c876d59 CI 與 CodeQL 均成功、未解決警示 0 項。其他容器的無標記截斷及完整一小時真模型推論仍待驗收。

2026-11-28: Reject the first audio stream if PyAV flags a corrupt packet or frame before model construction or SRT creation. A truncated synthetic PCM WAV regression and existing compressed audio, multiple audio track, and one-hour decode boundary tests passed. Windows Python 29 passed / 1 POSIX skip; Node 35 passed; JS syntax and diff checks passed. Silent truncation without decoder corruption flags and full-hour real-model inference remain unverified.

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. GitHub reports all six original alerts fixed on 2bc8199. Follow-up #11 flagged the subtitle regex; the revised parser splits and filters delimiters before joining, including removal of literal mathematical angle signs. Node 35 passed and Chromium browser smoke passed for the revised parser; GitHub CI and CodeQL succeeded on da692fb; all 11 historical alerts are fixed.

本機轉錄逾時後若無法確認程序終止，服務會拒絕後續轉錄；請檢查殘留程序及暫存資料，再重新啟動服務。


POSIX 本機轉錄使用獨立程序群組，正常結束、取消及逾時會清理仍在該群組內的程序；尚無整組資源硬上限或程序群組逃逸防護。

本機 Whisper 轉錄限制為每次最多 60 分鐘實際解碼音訊（16 kHz mono PCM 樣本累計）、SRT 最多 100000 字元及 400000 bytes；超限停止處理，網頁回傳 HTTP 413 並提示分段轉錄。

這是單機展示原型，不是多帳號家教服務。資料保存在同一瀏覽器來源的 IndexedDB；目前的 `learnerId` / `subjectId` 檢查只用來避免程式誤混資料，**不能阻止同一瀏覽器的其他使用者存取資料**。沒有登入、伺服器授權、資料靜態加密或跨裝置備份。

## 使用限制

本機一鍵影音轉錄服務 `tools/local_server.py` 僅監聽 `127.0.0.1`，限制 Host、來源與隨機工作階段權杖，允許固定路徑提供靜態資源，禁止讀取 repo 文件與隱藏檔案；單次 100 MB、一次只執行一個任務，暫存檔在完成、失敗或取消後清理。這些保護**不構成完整的本機程序隔離**：同一裝置的不可信程序可能存取 loopback，瀏覽器擴充功能及惡意本機軟體亦在威脅模型之外；勿用於多使用者共享主機或敏感教材。模型首次取得權重可能連網，請核對下載來源；轉錄內容不會自動傳給雲端 AI。

上傳連線設有 15 秒閒置逾時，服務關閉時會嘗試取消正在執行的工作並通知子程序結束；這不保證外部模型程序及其衍生程序均已回收，正式使用前仍須在 Windows 真實模型環境驗收。

Windows 工作程序採 Job Object 限制同一批衍生程序的存活期，Job handle 關閉時終止已加入的程序。程序以暫停狀態建立，加入 Job 後才恢復。每組 Job 限制 committed memory 為 4 GiB、同時存活程序數為 8；另保留 1800 秒轉錄逾時。另限制整組累計 user-mode CPU 時間為 14400 秒（非 CPU 使用率限制）；尚無非 Windows 等效 Job 限制；此機制不能保證處理所有外部程序逃逸或異常關閉情境。

- GitHub 原始碼 Repository 已由使用者於 2026-11-23 主動設為 public；允許將經檢查、未含敏感資料的程式與合成測試推送至 `SanHsien/adaptive-learning-os`。這不代表授權啟用 GitHub Pages 或公開部署服務。不得提交真實家人資料、教材、作答或憑證；Repository 可見性不是部署後的使用者存取管制。
- 不儲存真實敏感家人資料、身分證件、健康資訊、帳密、API key；開發與測試使用虛構資料。
- JSON 匯出檔包含教材與學習紀錄，應在自己的受保護裝置保存；清除網站資料將可能失去原資料。
- 複製 AI 家教提示詞後，資料可能傳給所使用的第三方 AI；送出前自行檢視並去識別。

## 未來正式版的必要控管

使用者登入、後端逐請求授權與資料庫列級隔離、資料最小化、傳輸加密、備份加密、刪除與匯出權限、可稽核的家長/監護人管理。這些尚未實作，不可因 UI 選單隔開就視為完成。

## 漏洞回報

以私人途徑聯絡 repo 擁有者；避免在公開 issue 發布資料、權杖或可利用細節。修補時加入能重現漏洞的合成資料測試。
