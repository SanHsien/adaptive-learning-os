# Security review

2026-11-28: Reject the first audio stream if PyAV flags a corrupt packet or frame before model construction or SRT creation. A truncated synthetic PCM WAV regression and existing compressed audio, multiple audio track, and one-hour decode boundary tests passed. Windows Python 29 passed / 1 POSIX skip; Node 35 passed; JS syntax and diff checks passed. Silent truncation without decoder corruption flags and full-hour real-model inference remain unverified.

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. GitHub reports all six original alerts fixed on 2bc8199. Follow-up #11 flagged the subtitle regex; the revised parser splits and filters delimiters before joining, including removal of literal mathematical angle signs. Node 35 passed and Chromium browser smoke passed for the revised parser; GitHub CI and CodeQL succeeded on da692fb; all 11 historical alerts are fixed.

Fix commit: 190127601c137da02b0169a459f1e82a1ee3f7bd; date 2026-11-28. Follow-up #11 fix commit: a574d3e881f260f252b8b917fcfdd9698cf0bd1f; date 2026-11-28.
