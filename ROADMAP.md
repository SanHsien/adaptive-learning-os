# 自適應自修系統路線圖

2026-11-27：新增實際 60 分鐘解碼邊界回歸，以 16 kHz mono ALAC/M4A 合成靜音、檔案均低於 100 MiB；3600 秒精確取得 57600000 樣本，3601 秒遭拒。Windows Python 26 項通過、1 項 POSIX 跳過，Node 33 項通過，安裝、語法、編譯與 diff 檢查通過。前版 5feb04a CI 與 CodeQL 均成功。此為解碼驗收，完整一小時真 Whisper 推論、跨硬體效能及 POSIX 整組資源限制仍待驗收。


2026-11-27：以實際 PyAV 編解碼合成 MP4（MPEG-4/AAC）及 WebM（VP8/Opus），每檔含 20 個視訊畫面與兩條不同音軌，確認只解碼第一音軌及超限拒絕。無音軌 MP4、損壞容器及模擬解碼超限均未建立 SRT，亦未建立 Whisper 模型。Windows Python 25 項通過、1 項 POSIX 跳過，Node 33 項通過，安裝、語法、編譯與 diff 檢查通過。前版 f6d1d23 CI 與 CodeQL 均成功。完整 60 分鐘、截斷容器、真模型視訊推論及跨硬體仍待驗收。


2026-11-27：新增 MP3、M4A、MP4（AAC 音軌）與 WebM（Opus 音軌）實際 PyAV 編解碼回歸測試，使用 48 kHz 合成音訊驗證重取樣至 16 kHz、3 秒限額接受及 1 秒限額拒絕。Windows Python 23 項通過、1 項 POSIX 跳過，Node 33 項通過，語法與 diff 檢查通過。前版 bf7ee0a 的 Linux CI 與 CodeQL 已成功。短音訊測試尚未涵蓋完整 60 分鐘、視訊畫面、多音軌及跨硬體長期負載。

2026-11-26：POSIX 轉錄工作使用獨立 session/process group，取消、逾時、正常結束時以 SIGKILL 清理仍在群組內的程序；避免繼承 stderr pipe 阻塞根程序回收。新增根程序先退出後以檔案鎖驗證子程序清理的 POSIX 回歸測試。Windows Python 22 項通過、1 項 POSIX 跳過，Node 33 項通過，語法與 diff 檢查通過。Linux CI 尚待驗證；群組逃逸、宿主異常退出及 POSIX 整組 CPU／記憶體限制仍未涵蓋。

2026-11-26：Windows Job Object 新增整組累積 user-mode CPU 時間上限 14400 秒（初始政策），保留獨立 1800 秒 wall-clock 逾時、4 GiB committed memory 與 8 個同時程序上限。1 秒低限額測試確認 CPU-bound worker 非零退出；Python 22/22、Node 33/33、語法及 diff 檢查通過。30 秒合成中文真 Whisper small smoke PASS，退出碼 0，耗時 97.53 秒、取樣程序樹 CPU 201.64 秒、Working Set 峰值 1032.8 MiB、最多 2 程序、313 次取樣。取樣 CPU 含 kernel 與 user 時間，與 Job user-mode 預算不同；低限額測試尚未驗證多子程序累加，非 Windows 等效限制、長影音與跨硬體驗收仍待完成，P0 持續進行中。

2026-11-26：本機轉錄改以 PyAV 逐音訊 frame 重取樣為 16 kHz mono，累計實際 PCM 樣本限制 60 分鐘；SRT 逐段累計限制 100000 字元及 400000 bytes，超限 CLI exit 75、HTTP 413，拒絕輸出並清理暫存及任務槽。以實際合成 WAV 兩秒及一秒測試界線，SRT 生成器超限停止消費後續段落，HTTP 超限清理測試通過。Windows .venv Python 21/21、Node 33/33、語法與 diff 檢查通過；30 秒合成中文真 Whisper small smoke PASS，exit 0，40.27 秒，取樣 Working Set 1032.6 MiB。Windows Job 低程序限額測試改用 base interpreter，避免 venv launcher 本身佔用第二程序而提前失敗。60 分鐘為初始政策，未實測完整 60 分鐘或所有壓縮格式的極限；CPU 累積時間、非 Windows 等效程序資源限制及長期驗收仍待處理。

2026-11-26：Windows 轉錄 Job Object 新增 4 GiB 整組 committed memory 與 8 個同時存活程序上限；保留 1800 秒 wall-clock 轉錄逾時。低限額負向測試確認 128 MiB Job 拒絕 256 MiB 配置、1 程序 Job 拒絕建立子程序，後續 worker 正常退出。Python 18/18、Node 33/33 通過。改由正式 launch_worker 啟動的 45 秒合成中文 Whisper small smoke PASS（exit 0），耗時 121.22 秒、取樣 Working Set 1036.1 MiB、累積 CPU 206.03 秒、最多 2 程序、383 次取樣。Working Set 與 committed memory 為不同指標；尚未設定 CPU 時間硬上限、解碼長度上限或非 Windows 等效限制，P0 持續進行中。

> 後續工作的單一待辦來源；完成任務時在同一個 commit 更新本檔。狀態以實際驗收為準，不將構想寫成已實作。

2026-11-25：Windows 真 Whisper small CPU int8 資源 smoke（--duration-seconds 180）使用約 180 秒合成中文語音，PASS、退出碼 0；轉錄耗時 74.69 秒，程序樹取樣 Working Set 峰值 1039.3 MiB、累積 CPU 250.50 秒、最多 2 程序、259 次取樣。此為單次本機量測，尚未證實硬性資源上限或跨環境長期穩定性，P0 持續進行中。

2026-11-25：真 Whisper small 45 秒合成中文音訊首段解碼後，新增 --action crash（強制終止 worker）及 --action shutdown（關閉 localhost 服務）驗收，各一輪均 PASS，整批退出碼 0。異常退出 HTTP 500、首段 54.08 秒、取樣 Working Set 峰值 1027.9 MiB、清理 0.06 秒；服務關閉 HTTP 409、首段 53.32 秒、峰值 1025.2 MiB、清理 0.22 秒。兩者均確認 worker 退出、暫存刪除及工作槽釋放。此為受控故障注入與正常服務關閉，不代表宿主突然斷電或所有異常皆可清理；長影音資源限制仍待驗收，P0 持續進行中。

2026-11-25：修正真 Whisper 取消 smoke 的 HTTP 等待設定，POST 採首段等待上限加 60 秒，DELETE 採獨立 30 秒上限，避免固定 180 秒提前中斷較長的首段等待。Python 17/17、Node 33/33、語法及差異檢查通過；尚未實測超過 180 秒的首段等待，P0 持續進行中。

2026-11-25：同一服務連續三輪 45 秒合成中文音訊真 Whisper small 取消驗收均 PASS（exit 0），首段耗時 44.18／34.84／31.62 秒，程序樹 Working Set 取樣峰值 1027.9／1027.6／1031.3 MiB，取消至清理 0.06／0.08／0.06 秒。每輪 HTTP DELETE 200、POST 409、子程序退出、暫存清除及工作槽釋放均通過。未重現先前逾時，原因仍未確認；長期負載、異常退出與硬性資源上限仍待驗收，P0 持續進行中。

2026-11-25：新版 Windows Job 啟動路徑再以 45 秒合成音訊、150 秒首次解碼上限驗收，77.25 秒取得首段，程序樹 Working Set 取樣峰值 1033.8 MiB，取消至清理 0.07 秒，程序退出與暫存清除通過。這是單次測試，先前相同音訊逾時的偶發性仍待多次受控量測。

2026-11-25：真模型取消測試新增合成音訊長度（20–90 秒）、首段解碼等待上限（30–300 秒）及逾時診斷。Windows Whisper worker 改採暫停建立程序、加入 Job Object 後才恢復執行，消除原本的指派前執行窗口；Windows 父程序先退出的孤兒子程序回歸與 Python 17 項測試通過。新版 Windows 啟動路徑真模型 20 秒合成音訊約 18.47 秒觀測首段，取消後子程序退出、暫存清除；先前 45 秒音訊在 100 秒內未觀測到首段，原因未定。使用 NtResumeProcess 的跨 Windows 版本相容性及長期壓力仍待驗收，P0 持續進行中。

2026-11-25：Windows 本機轉錄子程序改納入具 `KILL_ON_JOB_CLOSE` 的 Job Object，取消、服務關閉或轉錄工作結束時關閉 Job handle，涵蓋根程序已退出仍存活的衍生程序。新增 Windows 真實父子程序回歸測試。Job 加入程序存在極短啟動競爭窗口，且真 Whisper 的異常退出與長期壓力尚待驗收；P0 持續進行中。

## 現況（2026-11-22）

- v0.1：瀏覽器單機原型；家人 × 科目分別儲存文字教材、練習與複習資料；可複製 AI 家教提示、匯出與隔離式匯入 JSON。TXT/Markdown/CSV、PDF、DOCX 本機解析；PNG/JPEG/WebP 圖片本機繁體中文 OCR 與人工校對；掃描 PDF 逐頁 OCR（最多 20 個影像頁）；影音可暫時播放並人工輸入逐字稿。尚無影音自動轉錄。
- 已有 Node 單元及 IndexedDB 模擬測試；2026-11-22 已完成 Chrome 157 本機合成資料瀏覽器端到端驗收（`python tools/browser_smoke.py`）。
- 已增加真實 IndexedDB v1→v2 升級回歸測試，保留舊科目教材、作答版本及首次更新前的最新教材快照；影音人工逐字稿保留來源資訊。
- 圖片／掃描 PDF 辨識已接入取消訊號；切換學習空間或改選教材會通知 OCR Worker 結束；初始化期間取消可於 Worker 建立後清理，PDF 渲染階段可取消；文字及 DOCX 解碼途中取消也有負向測試。已加入三頁文字／掃描／文字混合 PDF 的 Chrome E2E。八頁掃描 PDF 跨科取消情境雖未出現教材覆蓋，但測試程序在 Chrome 關閉階段未正常退出，尚不得列為通過；Worker 終止時延及資源釋放仍待調查；影音轉錄待辦。
- 已讓 OCR 的多次清理呼叫共用同一個 `terminationPromise`，確保取消後等待 Worker 真正終止；新增延後終止回歸測試（Node 30/30 通過）。但 2026-11-22 再跑混合 PDF Chrome E2E 時，雖輸出 PASS，程序仍未退出而需中斷；此修正不等於解決瀏覽器關閉阻塞，後續須隔離 Chrome／Playwright 關閉階段與 PDF.js 資源的影響。
- 2026-11-23：透過指定已安裝的 Chromium Headless Shell 149，混合 PDF 與八頁掃描 PDF 中途跨科切換的合成 E2E 均通過，且 `browser.close()` 與 Python 程序退出碼 0；系統 Chrome 157 在不執行 OCR 時仍曾卡住，現階段列為瀏覽器環境相容性待追蹤，不再直接歸因 OCR。八頁案例驗證舊教材不覆寫其他科目；仍需量測 Worker 終止耗時、跨學習者取消與連續壓力循環。
- 2026-11-23：遠端新增模組架構文件；使用者確認主動將 GitHub Repository 設為 public，允許公開原始碼及合成測試資料。不得提交真實家庭資料，未取得另外授權及完成安全控管前仍禁止公開部署服務。
- 2026-11-23：增加 Node 可決定性測試，確認兩次在 `recognize()` 已開始後取消，隨後第三次 OCR 可成功、各 Worker 只終止一次；真實瀏覽器中 Worker 進入辨識階段的訊號與終止耗時仍待量測。
- 2026-11-23：瀏覽器合成測試改以真實 Tesseract `recognize()` 進入訊號啟動取消，覆蓋跨科目及跨學習者；監測 `terminate()` 呼叫次數。實際延遲與資源使用量仍待量測。
- 2026-11-23：瀏覽器端增加真實 Tesseract Worker `terminate()` 完成及耗時（毫秒）觀測，跨科目／跨學習者兩次取消均須在 15 秒內完成且無終止錯誤；長時間循環與記憶體資源使用仍待驗收。
- IndexedDB 只提供**邏輯分隔**；沒有使用者登入、伺服器權限、加密或跨裝置同步，**不可**當作家人間的隱私邊界。

- 2026-11-24：新增分組 Dependabot（Actions／npm）、JavaScript／Python CodeQL，以及每月依賴 freshness 檢查與離線契約測試；僅檢查版本宣告，不自動更新或部署。

## 近期：可直接開始

2026-11-25：CI `45505627385` 顯示 `test_real_child_cancel_cleanup_and_next_job` 偶發在 HTTP 409 回應後立刻檢查工作槽。改為沿用現有 `wait_for_available_slot()` 五秒有界等待，確保 Handler `finally` 完成後才檢查下一任務。待後續 CI 複核。

2026-11-25：Whisper 真模型取消 smoke 的程序樹資源監控已提前至子程序啟動後，新增取消前記憶體取樣峰值、取消前樣本數，以及啟動至首次解碼與解碼至清理的耗時。約 0.1 秒間隔取樣可能漏掉瞬間峰值，根程序提前退出後的孤兒程序與長期壓力仍待驗收；P0 持續進行中。

2026-11-24：`dabccb5` 的 Linux CI 於 `test_repeated_real_child_cancel_and_recovery` 偶發失敗，HTTP 回應完成時 `Handler.do_POST()` 的 `finally` 尚可能未釋放 `server.active`。Python 整合測試改以有界等待確認前一次工作槽釋放，避免跨測試污染；後續依新提交的 CI 實測確認。

2026-11-24：GitHub Actions 最新 `bc57f58` 的 CI 與 CodeQL 均成功。前版 `c04123a` 的 Linux CI 曾在不完整上傳預期 400 卻收到 409、子程序啟動等待逾時兩項測試失敗；目前新版成功，仍需觀察是否為偶發競爭條件。新增真實 Whisper 推論取消後資源取樣，Windows 同一服務連續三輪 `--cycles 3` 成功，程序退出碼 0。三輪首次解碼至取消短窗內取樣 Working Set 峰值依序 589.0／582.4／589.8 MiB、累積 CPU 時間 187.28／169.84／184.78 秒（含取樣時已累積時間）、最大程序數均 2，取樣 5／5／6 次。每輪子程序退出、暫存清除、任務槽釋放。短窗取樣不代表整次轉錄的真實峰值或無孤兒孫程序，P0 持續進行中。

2026-11-24：資源量測工具新增 `--duration-seconds 30..180`（預設 45 秒）。使用本機合成約 90 秒中文語音及 Whisper small CPU int8 真模型測試，退出碼 0；轉錄 94.6 秒、取樣程序樹 CPU 累積 212.56 秒、Working Set 峰值 1029.1 MiB、最多 2 程序、324 次取樣。此為同一台 Windows 電腦的單次負載量測，長時間持續運作、跨硬體與資源政策上限尚待驗收，P0 持續進行中。

2026-11-24：`tools/real_whisper_inference_cancel_smoke.py` 新增 `--cycles {1,2,3}`（預設 1），可在同一 localhost 服務中重複執行真實 Whisper small 模型首次解碼段落後的取消。以本機合成中文音訊執行 `--cycles 2`，兩輪皆通過且程序退出碼 0，每輪確認 HTTP DELETE 200、原上傳請求 409、Whisper 子程序結束、暫存目錄刪除、任務槽釋放；單次資源峰值與較長影音仍需另測，P0 持續進行中。

2026-11-24：新增同一 localhost 服務連續三次真實 OS 子程序取消整合測試，每次驗證 HTTP 409／DELETE 200、程序退出、暫存目錄清理與任務槽釋放，再驗證後續合成轉錄成功。Python 16/16 通過。此項為不載入模型的短循環測試；長影音與真正 Whisper 多次取消壓力仍待完成，P0 持續進行中。

2026-11-24：新增可選用 `tools/real_whisper_resource_smoke.py`，以 Windows API 取樣 Python 啟動程序及其子程序樹的 Working Set 與 CPU 時間，避免只量到啟動器。使用本機 Whisper small、約 45 秒合成中文語音，實測轉錄 44.32 秒、程序樹 Working Set 取樣峰值 1025.4 MiB、取樣累計 CPU 165.41 秒、最多 2 個程序（154 次取樣）。數據僅適用本次 Windows 測試環境，不代表硬性資源限制；長於此工作負載的影音、連續取消壓力與跨硬體驗收仍待完成，P0 持續進行。

2026-11-24：本機轉錄的取消、逾時及伺服器關閉改用 Windows `taskkill /T /F` 終止仍在執行的 Whisper 子程序樹；新增真實 Python 父子程序的 Windows 回歸測試，驗證取消後父程序及衍生子程序皆退出。這涵蓋已存活的程序樹，不涵蓋根程序提前退出後孤兒程序、長影音 CPU／記憶體峰值或長期重複循環；P0 仍進行中。

2026-11-23：新增網站「本機一鍵轉錄」與 localhost Python 服務之初版串接，支援影音暫存、SRT 預覽、人工確認、取消與單一任務上限。已新增合成 HTTP 負向測試及 Chromium 一鍵轉錄→人工校對→指定科目儲存、跨學習者切換取消 E2E（mock Whisper）；**真實長影音、Windows 真實子程序取消及資源上限仍需驗收**，故 P0 未結案。不得公開部署。

2026-11-23：補強 localhost 服務關閉時通知取消並終止當前子程序、上傳連線 15 秒無進展時逾時；新增不完整 HTTP Body 釋放任務槽及伺服器關閉通知的合成負向測試。Python 12/12、Node 33/33 通過。這不等於 Windows 真實 Whisper 長任務關閉、上傳逾時端到端或模型資源釋放已驗收；P0 持續進行中。

2026-11-23：新增真正作業系統 Python 子程序（不載入 Whisper）的 HTTP 取消整合測試，覆蓋進行中第二個請求遭拒、DELETE 取消、子程序退出、暫存資料夾移除、任務槽釋放及下一次轉錄成功。這驗證 Windows 子程序層級的基本取消行為，但尚未測到真正 Whisper 模型載入期間、子孫程序、長影音資源與完整真模型瀏覽器流程。P0 未結案。

2026-11-23：以獨立 `.venv`（faster-whisper 1.2.1／PyAV 16.1.0）及本機快取 small 模型執行合成中文 WAV 的真正 Whisper 網頁 E2E：成功轉錄、人工校對儲存至指定學習者／科目、切換學習者不洩漏教材、切回保留原內容，測試 Python 退出碼 0。此為短合成音訊驗收；真正模型載入／推論期間取消、長影音資源與衍生程序清理仍待測，P0 未結案。

2026-11-23：新增可選用 `tools/transcribe_local.py`，以本機 `faster-whisper` 將影音轉錄為 SRT；網站可匯入 SRT／WebVTT 並校對後儲存到當前學習者／科目。尚未完成網站一鍵轉錄、真實影音辨識品質驗收，也未安裝／封裝模型；P0 保持進行中。

2026-11-23：以本機快取 `faster-whisper-small`、隔離 PyAV 16.1.0 和 Windows SAPI 合成中文 WAV 完成真實推論，產生兩段語意相符的 SRT；模型輸出簡體字，仍須校對。排除與 PyAV 19.0.2 的相容問題；新增 SRT/VTT 解析、校對後保留來源、無效字幕拒絕、備份來源與跨學習者預覽隔離的 Chromium E2E，修復字幕 MIME 驗證和來源遺失。尚未完成長影音、真實教材品質、網站一鍵轉錄，P0 持續進行中。

| 工作 | 原因 | 驗收方式 | 執行者 | 證據 |
| --- | --- | --- | --- | --- |
| **P0：多格式教材匯入（影音自動轉錄進行中）** | PDF、DOCX、圖片／掃描 PDF OCR 已完成；影音暫播、SRT/VTT 匯入、本機 Whisper CLI 與網頁一鍵轉錄初版已實作 | 合成 HTTP、瀏覽器 mock、Windows 真 Python 子程序取消及短合成 WAV 真 Whisper 網頁 E2E 已通過；後續驗證真模型取消、長影音資源、衍生程序與隱私，禁止跨人跨科混用 | Codex | `docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md` |
| **教材來源與版本模型（已完成本機版）** | 已保留完整版本內容、SHA-256、解析確認狀態及作答當時版本；舊版備份可匯入 | Node 測試涵蓋跨 scope、版本歷程、備份還原；仍需更多瀏覽器格式測試 | Codex | `docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md` |

## 中期：條件成立再做

| 工作 | 觸發條件 | 驗收方式 | 執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 真正的多帳號與授權 | 家人開始共用服務或各自裝置操作 | 後端逐筆驗證登入身分、學習者與科目權限；交叉存取均拒絕 | Codex | `SECURITY.md` |
| 雲端同步與復原 | 完成後端授權、備份與資料生命週期決策 | 跨裝置一致性、復原及刪除測試成功 | Codex | 待建立的部署文件 |
| AI 自適應診斷與回饋 | 蒐集非敏感匿名測試教材及評量規準 | 對比人工標準答案，測量提示品質、幻覺與錯誤回饋率 | Codex | `docs/ACCEPTANCE.md` |

## 刻意不做

| 項目 | 理由 | 重新考慮條件 |
| --- | --- | --- |
| 公開部署或啟用 GitHub Pages | 無登入與隱私邊界 | 完成伺服器端授權與隱私審核 |
| 將家人真實教材與作答加入 Git | 避免私密資料進入版本歷史 | 不考慮，僅允許合成測試資料 |
| 宣稱現有複習間隔為科學最佳 | 目前只有固定 1/3/7/14 天規則 | 有測量與實驗證據 |

## 維護規則

修改行為時同步更新測試、`docs/ACCEPTANCE.md`；改動資料模型同步更新 `docs/ARCHITECTURE.md`；每次交付前更新本檔並檢查 `npm test` 與 CI。
