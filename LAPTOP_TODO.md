# 筆電實機測試（給筆電上的 agent）

> **這是你唯一要讀的檔案。** 不要讀 HANDOFF.md、ARCHITECTURE.md 或程式碼，這裡寫的就夠了。
> 環境：Windows 11、RTX 3050 Ti Laptop 4 GB、專案在 `C:\Users\A8fm0\Downloads\SilentTalk`。
> 結果寫進 `LAPTOP_REPORT.md`（格式在最後），推到 `laptop-report` 分支，開發機那邊會自己去拿。

## 規則

- 不改 repo 裡任何已追蹤的檔案；唯一會新增的是 `LAPTOP_REPORT.md`。
- 不動 `.env`、`settings.json`、`personas.json`（人設由使用者在 App 裡自己設）。
- 不要讀 `silenttalk.log` 原文，只用 `scripts\dev\log_summary.py` 的輸出（log 裡的東西可能跟對話有關，報告只放數字）。
- 報告裡**不要寫任何對話內容**，只寫數字和使用者自己說的感想。
- 關程式用 `Get-Process <名稱>` 找 PID 再 `Stop-Process -Id`，不要依名稱整批砍。
- 程式出錯不要改程式碼，照實寫進報告（錯誤訊息的最後幾行即可）。
- 使用者不想做雜事：安裝、執行、整理都是你的事，只有「講話和聽」需要他。

## TODO

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  `setup_copilot.py` 已下載的模型會跳過。`.env` 裡沒有 `DISCORD_BOT_TOKEN` 或 `OWNER_USER_ID` 就停下來問使用者，不要自己填。

- [ ] **2. 硬體量測**（約 2 分鐘，GPU 別開其他東西）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\bench_hw.py
  ```
  把最後「==== 貼這張表回來 ====」下面整張表放進報告。問使用者平常會不會邊打遊戲邊用；會的話請他開著遊戲，你再跑一次，兩張都放。

- [ ] **3. Copilot 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  把輸出放進報告（exit code 0＝通過）。

- [ ] **4. 開 App，陪使用者做 10 分鐘語音測試**
  用 `啟動 SilentTalk.cmd` 開 App。請使用者：
  1. 人設頁選一個人設（或新建），「人際關係」加一行：**他自己的 Discord 顯示名稱**＋從角色角度的關係，例如「阿明：我老公」「阿明：我爸」「阿明：我兄弟」。
  2. 打開上方的「角色模式」，設定頁 → 聊天 →「開口時機」維持「被叫到才回」。
  3. 進語音頻道（最好有一兩個朋友），逐項試，每項試完問他感覺怎樣，記下他的話：

  | # | 請使用者做 | 應該要 |
  |---|---|---|
  | a | 叫角色的名字問一句 | 回話；感覺停頓多久 |
  | b | 跟朋友聊別的、不叫它 | 不插嘴 |
  | c | 「我剛剛跟○○講過」（講到它但不是對它說） | 不回 |
  | d | 它回完之後直接接它的話，不叫名字 | 回話 |
  | e | 故意用同音字叫錯它的名字 | 最好要回 |
  | f | 問「你是不是 AI」 | 不承認、自然帶過 |
  | g | 叫它寫程式或查天氣 | 用角色的方式推掉，不答應 |
  | h | 用人際關係的稱呼叫它（老婆、爸、兄弟…） | 知道是在叫它、用那個關係回你 |
  | i | 聽聲音 | 音色合不合角色、有沒有斷音或爆音 |

  （選做）設定頁 → 聊天 →「開口時機」改「會主動加入」再聊 3 分鐘：它插話的頻率自不自然。

- [ ] **5. 整理數字**（使用者測完、App 還開著或關掉都可以）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  整份輸出放進報告。

- [ ] **6. 交回報告**
  ```powershell
  git switch -C laptop-report
  git add LAPTOP_REPORT.md
  git commit -m "Laptop test report"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗（沒有權限之類）就把 `LAPTOP_REPORT.md` 整份貼給使用者，請他轉給開發機。

## LAPTOP_REPORT.md 格式

```markdown
# 筆電測試報告 <日期時間>
commit：<git rev-parse --short HEAD 的結果>

## 硬體量測
<bench_hw 的表；有邊打遊戲的第二張也放>

## Copilot smoke
<輸出，或錯誤最後幾行>

## 語音測試
| # | 結果（OK／不OK） | 使用者怎麼說 |
|---|---|---|
| a | | |
…（b 到 i，選做的主動模式也寫）

## log_summary
<整份輸出>

## 其他問題
<安裝、啟動、錯誤；沒有就寫「無」>
```
