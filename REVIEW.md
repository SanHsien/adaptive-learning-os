# Security review

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. Remote CodeQL confirmation pending.

Fix commit: 190127601c137da02b0169a459f1e82a1ee3f7bd; date 2026-11-28.
