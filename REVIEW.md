# Security review

2026-11-28：新增 MP3 首個 MPEG Layer III 音框 Xing/Info 宣告位元組數檢查及 ID3 長度檢查。合成 MP3 含 ID3 與無 ID3 的正常檔均可解碼，完整封包邊界截斷於模型建立前拒絕且無 SRT；無 Xing/Info 的正常檔仍可解碼。無宣告總長度或宣告不準確的 MP3 仍可能漏判，未宣稱完整性保證。Node 35 項通過、npm ci 與語法檢查通過；Python 轉錄 15 項通過，HTTP 套件首次全跑有 WinError 10053，獨立重跑 19 項通過、1 項 POSIX 跳過。

2026-11-28：新增 WebM EBML 頂層元素宣告長度檢查，保留合法未知長度 Segment。實測 PyAV 16.1.0 合成 Opus WebM 截半原可回傳 16536 樣本，修正後於模型建立前拒絕且無 SRT。正常 WebM 解碼及未知長度標頭測試通過。MP3 截半原可回傳 15760 樣本，尚待處理；未知長度 Segment 的內部截斷仍可能無法辨識。Python 33 項通過、1 項 POSIX 跳過，Node 35 項通過，npm ci、語法及 diff 檢查通過。前版 69e51bd CI/CodeQL 成功，未解決警示 0 項。

2026-11-28：新增 MP4/M4A ISO BMFF 頂層區塊長度檢查，支援 32-bit、64-bit 延伸及合法延伸至 EOF 的區塊。合成 faststart AAC 於完整封包邊界截斷時，拒絕於模型建立前且不產生 SRT；正常檔案可解碼。Windows Python 31 項通過、1 項 POSIX 跳過，Node 35 項通過，npm ci、語法及 diff 檢查通過。前版 6546794 CI/CodeQL 成功且未解決警示 0 項（前輪查證）。頂層長度一致或 EOF 區塊仍可能存在無法偵測的截斷；MP3/WebM 與完整一小時真模型推論待驗收。

2026-11-28：新增 RIFF/WAVE 宣告長度檢查。合成 PCM WAV 在完整封包邊界截斷時，PyAV 19.0.2 原先無損毀標記且仍回傳部分音訊；修正後於模型建立前拒絕，未產生 SRT。Windows PyAV 16.1.0（與 CI 固定版本相同）Python 29 項通過、1 項 POSIX 跳過；Node 35 項通過、語法檢查通過。前版 c876d59 CI 與 CodeQL 均成功、未解決警示 0 項。其他容器的無標記截斷及完整一小時真模型推論仍待驗收。

2026-11-28: Reject the first audio stream if PyAV flags a corrupt packet or frame before model construction or SRT creation. A truncated synthetic PCM WAV regression and existing compressed audio, multiple audio track, and one-hour decode boundary tests passed. Windows Python 29 passed / 1 POSIX skip; Node 35 passed; JS syntax and diff checks passed. Silent truncation without decoder corruption flags and full-hour real-model inference remain unverified.

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. GitHub reports all six original alerts fixed on 2bc8199. Follow-up #11 flagged the subtitle regex; the revised parser splits and filters delimiters before joining, including removal of literal mathematical angle signs. Node 35 passed and Chromium browser smoke passed for the revised parser; GitHub CI and CodeQL succeeded on da692fb; all 11 historical alerts are fixed.

Fix commit: 190127601c137da02b0169a459f1e82a1ee3f7bd; date 2026-11-28. Follow-up #11 fix commit: a574d3e881f260f252b8b917fcfdd9698cf0bd1f; date 2026-11-28.

Corrupt audio rejection fix commit: 332f2669f880b200f46ce299edb7409a8cc3805b; date 2026-11-28.

RIFF truncation fix commit: f7831bb0e9e9177151253669dab804ee4a68353f; date 2026-11-28.

ISO BMFF truncation fix commit: 7bc82b1f714028287a81f62d116e186d6b0b6d95; date 2026-11-28.

WebM truncation fix commit: 26991658df82edd8542a7cac3d8b06a54f17a041; date 2026-11-28.

MP3 truncation fix commit: e2cdbb2afea9558fc65c5d27861aa64811c13872; date 2026-11-28.
