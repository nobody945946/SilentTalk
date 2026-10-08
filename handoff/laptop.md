# Windows 工作檔：待命（第 9 回合已完成）

更新：2026-10-09 凌晨｜SilentTalk `copilot-story-mode`｜回報 `laptop-report`｜上一版：開發機 `archive/laptop-2026-10-08-round8.md`（不必讀）

## 現在

第 9 回合（雙管路實機量測）已完成，你的量測修正（`feabd5e`，PR #1）已由開發機審過、併入 `spec-v2`。結論：角色要在 Agent 工作時開口，兩邊必須共用一個 adapter；開發機正在錄資料、訓練這個共用 adapter，過了關卡才有下一回合（v2 出貨：部署、PowerShell 7、介面）。

**這段時間沒有筆電的工作。** 使用者說「開工」時：

1. 在 SilentTalk 執行 `git pull --ff-only`；拉不下來就停下回報。
2. 重讀 `AGENTS.md` 和這份。這份還是「待命」就告訴使用者：開發機還在訓練，筆電目前沒有工作；不要自己找事做，不要動部署、模型或使用者的檔案。
3. 不用推回報（沒有新回合就沒有新回報）。

使用者在對話中另外交代的事照做，並在下一次回報寫一行。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄。
- 不動 `.env`、`settings.json`、`personas.json`、`character_state.json`；EdgeAgent 的 `config.json` 只讀。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事。
- 關程式只用核對過的 PID。
- 推 commit 到 EdgeAgent 或 SilentTalk 之後，等那次 push 的 GitHub 檢查跑完（`gh run list --limit 3`，或到 repo 的 Actions 頁）；失敗就修好再結束回合，修不了寫進回報。
