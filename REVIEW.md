# Security review

2026-11-28：新增 RIFF/WAVE 宣告長度檢查。合成 PCM WAV 在完整封包邊界截斷時，PyAV 19.0.2 原先無損毀標記且仍回傳部分音訊；修正後於模型建立前拒絕，未產生 SRT。Windows PyAV 16.1.0（與 CI 固定版本相同）Python 29 項通過、1 項 POSIX 跳過；Node 35 項通過、語法檢查通過。前版 c876d59 CI 與 CodeQL 均成功、未解決警示 0 項。其他容器的無標記截斷及完整一小時真模型推論仍待驗收。

2026-11-28: Reject the first audio stream if PyAV flags a corrupt packet or frame before model construction or SRT creation. A truncated synthetic PCM WAV regression and existing compressed audio, multiple audio track, and one-hour decode boundary tests passed. Windows Python 29 passed / 1 POSIX skip; Node 35 passed; JS syntax and diff checks passed. Silent truncation without decoder corruption flags and full-hour real-model inference remain unverified.

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. GitHub reports all six original alerts fixed on 2bc8199. Follow-up #11 flagged the subtitle regex; the revised parser splits and filters delimiters before joining, including removal of literal mathematical angle signs. Node 35 passed and Chromium browser smoke passed for the revised parser; GitHub CI and CodeQL succeeded on da692fb; all 11 historical alerts are fixed.

Fix commit: 190127601c137da02b0169a459f1e82a1ee3f7bd; date 2026-11-28. Follow-up #11 fix commit: a574d3e881f260f252b8b917fcfdd9698cf0bd1f; date 2026-11-28.

Corrupt audio rejection fix commit: 332f2669f880b200f46ce299edb7409a8cc3805b; date 2026-11-28.

RIFF truncation fix commit: f7831bb0e9e9177151253669dab804ee4a68353f; date 2026-11-28.
