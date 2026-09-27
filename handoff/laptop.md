# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-27 19:00｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

角色模式（Bot 自己扮演使用者寫的人設聊天）剛重做完，還沒在真的 Discord 上跑過。這次要：量這台筆電的速度、陪使用者做 10 分鐘語音測試、把結果交回開發機。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`，推到 `laptop-report` 分支（步驟 6）
- 不要讀 `silenttalk.log` 原文，數字一律用步驟 5 的腳本產生

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  模型已下載的會跳過。`.env` 裡沒有 `DISCORD_BOT_TOKEN` 或 `OWNER_USER_ID` 就停下來問使用者。

- [ ] **2. 硬體量測**（約 2 分鐘，先關掉吃 GPU 的程式）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\bench_hw.py
  ```
  留下最後「==== 貼這張表回來 ====」下面的表。問使用者平常會不會邊打遊戲邊用；會的話請他開著遊戲，你再跑一次，兩張都留。

- [ ] **3. 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  留下輸出（exit code 0＝通過）。

- [ ] **4. 陪使用者做語音測試（約 10 分鐘）**
  用 `啟動 SilentTalk.cmd` 開 App，請使用者：
  1. 人設頁選或新建一個人設；「人際關係」加一行：**他自己的 Discord 顯示名稱**＋從角色角度寫的關係，例如「阿明：我老公」「阿明：我爸」「阿明：我兄弟」。
  2. 打開上方「角色模式」；設定頁 → 聊天 →「開口時機」維持「被叫到才回」。
  3. 進語音頻道（最好有一兩個朋友），逐項試，每項問他感覺如何並記下他的話：

  | # | 請使用者做 | 應該要 |
  |---|---|---|
  | a | 叫角色的名字問一句 | 回話；問他停頓感覺多久 |
  | b | 跟朋友聊別的、不叫它 | 不插嘴 |
  | c | 「我剛剛跟○○講過」（講到它但不是對它說） | 不回 |
  | d | 它回完後直接接它的話，不叫名字 | 回話 |
  | e | 用同音字叫錯它的名字 | 最好要回 |
  | f | 問「你是不是 AI」 | 不承認、自然帶過 |
  | g | 叫它寫程式或查天氣 | 用角色的方式推掉 |
  | h | 用關係的稱呼叫它（老婆、爸、兄弟…） | 知道是在叫它，用那個關係回 |
  | i | 聽聲音 | 音色合不合角色、有沒有斷音或爆音 |

  選做：「開口時機」改成「會主動加入」再聊 3 分鐘，問他插話頻率自不自然。

- [ ] **5. 整理數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  只輸出數字和事件名稱，整份留下。

- [ ] **6. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md
  git commit -m "Laptop test report"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗才把報告整份貼給使用者。

## 回報格式（`handoff\reports\laptop.md`）

```markdown
# 筆電測試報告 <日期時間>
commit：<git rev-parse --short HEAD>

## 硬體量測
<bench_hw 的表；有邊打遊戲的第二張也放>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## 語音測試
| # | OK／不OK | 使用者怎麼說 |
|---|---|---|
| a | | |
（b～i，選做的主動模式也寫）

## log_summary
<整份輸出>

## 其他
<安裝、啟動、錯誤；沒有就寫「無」>
```
