# 架構與資料歸屬

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

目前沒有後端與自動 AI API；教材為 subject 的 `material` 字串，沒有檔案版本歷程。固定複習間隔不代表已校準的個人化模型。

## 後續資料模型設計限制

- 教材檔案需保留 `learnerId`、`subjectId`、source、version、hash 與 parser 狀態；相同科目也不得跨 learner 共用內容，除非使用者明確選擇複製。
- 任務與評量須以 scope + material version 關聯來源，避免新版教材覆蓋舊證據的語境。
- 引入同步服務前先定義帳號身分、權限、衝突解決、刪除/復原及備份版本規範；瀏覽器端檢查不得替代後端授權。
