# AGENTS.md — 所有 agent 的唯一入口

> Codex 會自動讀這份；Claude Code 經由 `CLAUDE.md` 讀到同一份。
> **這份只做兩件事：告訴你該讀哪一份工作檔，以及到哪都適用的規則。**

## 1. 你在哪台機器？只讀對應的那一份

| 你在 | 讀這份（只讀這份） | 回報寫到 | 回報推到的分支 |
|---|---|---|---|
| **Windows**（使用者的 RTX 3050 Ti 筆電，`C:\Users\...\SilentTalk`） | `handoff/laptop.md` | `handoff/reports/laptop.md` | `laptop-report` |
| **Linux** 開發機（`/home/clawd/SilentTalk`，RTX 3090） | `handoff/dev-box.md` | 直接改 `handoff/dev-box.md` | `copilot-story-mode` |

- 工作檔是自足的：**不要另外讀** README、ARCHITECTURE、程式碼或另一台機器的工作檔，除非你的工作檔叫你去讀某個段落。
- 使用者只說「開工」「照做」「繼續」時，就是照上表那份工作檔做。
- 工作檔和使用者的話衝突時，照使用者說的做，並在回報裡寫一行。

## 2. 到哪都適用的規則

1. **對話內容不能寫進硬碟，也不能寫進回報。** 轉錄文字、錄音、打字內容、prompt 只在記憶體；回報只寫數字、事件名稱，以及使用者自己說的感想。
2. **使用者不做雜事。** 安裝、執行、整理、除錯是 agent 的事；只有「講話、聽、做決定」需要他。不要叫他標註資料或評判樣本。
3. **不要在 `main` 上 commit。** 開發分支是 `copilot-story-mode`。
4. **關程式用 PID**（`pgrep -x` 或 `Get-Process`），不要 `pkill -f <字串>`，會連自己的 shell 一起殺掉。
5. **不要動使用者的 `.env`、`settings.json`、`personas.json`。**
6. **跑測試看 pytest 自己的 exit code**，不要 `pytest | tail` 後面接 `&&`。
7. 程式出錯時，不在你工作檔範圍內的就不要改，照實寫進回報。

## 3. 給寫交接的人

這個 repo 的交接配置：根目錄只有這份給 agent 讀；每台機器一份自足的工作檔，放在 `handoff/`，並在 §1 的表裡登記；回報寫在 `handoff/reports/<角色>.md`，推到 `<角色>-report` 分支。工作檔的狀況變了（例如一個階段結束、計畫改了）時，把舊版複製到 `archive/`（只存在開發機），再從頭重寫一份新的；不要在舊版上修補。不要在根目錄另外新增給 agent 讀的檔案。
