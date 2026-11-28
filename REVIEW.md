# Security review

2026-11-28: CodeQL #2, #3, #10: request extensions select server-owned literal filenames in a temporary directory. #4, #5: preview uses validated MIME types and browser-generated blob URLs. #6: malformed subtitle markup cannot retain literal angle brackets. Regression: Node 35 passed; Python 29 passed, 1 POSIX skip; both Chromium synthetic browser suites passed. GitHub reports all six original alerts fixed on 2bc8199. Follow-up #11 flagged the subtitle regex; the revised parser splits and filters delimiters before joining, including removal of literal mathematical angle signs. Node 35 passed and Chromium browser smoke passed for the revised parser; remote confirmation of #11 pending.

Fix commit: 190127601c137da02b0169a459f1e82a1ee3f7bd; date 2026-11-28. Follow-up #11 fix commit: a574d3e881f260f252b8b917fcfdd9698cf0bd1f; date 2026-11-28.
