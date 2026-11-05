# SYS2 文件釋出追蹤 Dashboard

網址(部署後):https://marzlo.github.io/SYS2/

資料來源是 Jira filter 11923,只保留「底下有名稱含 `BL` 的 sub-task」的 Story,
用來看哪些 Story 最近出了新的 BL 文件或新附件。

## 運作方式

```
.github/workflows/refresh-dashboard.yml  # 平日台北 09:00 / 14:00 / 17:00 自動跑,也可手動 Run workflow
scripts/fetch_jira.py                    # filter -> Story;再用 parent in (...) 撈 sub-task(含建立日期、附件)
scripts/build_dashboard.py               # 套用 BL 條件、整理資料,把資料嵌進 template.html -> site/index.html
scripts/template.html                    # 頁面版型(要改外觀改這支)
```

`raw_*.json` 與 `site/` 只在 Actions 執行時產生,不進 git。

## 第一次設定(只要做一次)

1. **Secrets**:repo → Settings → Secrets and variables → Actions,新增
   `JIRA_EMAIL`、`JIRA_API_TOKEN`(可以沿用 CPAA_Dash 那組;secrets 是各 repo 獨立的,要再建一次)。
2. **Pages**:Settings → Pages → Build and deployment → Source 選 **GitHub Actions**。
3. **跑一次**:Actions → Refresh SYS2 Docs Dashboard → Run workflow。

## 可調參數(在 workflow 的 env)

| 變數 | 預設 | 說明 |
|---|---|---|
| `JIRA_JQL` | `filter=11923` | Story 來源 |
| `SUBTASK_KEYWORD` | `BL` | sub-task 名稱需包含的字(區分大小寫) |

完成狀態的判定在 `build_dashboard.py` 的 `DONE_STATUSES` / `DROP_STATUSES`。

## 注意:資料公開性

GitHub Free 的 Pages 只能從 public repo 發布,網址公開可見。頁面上會有 Story / sub-task 名稱、
負責人姓名與附件檔名(不含附件內容,Jira 連結需登入才能開)。
