# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-28｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

上一輪使用者在「選項」模式就停了：選項換太快來不及看，內容敷衍、只會跟著最後一句。開發機這一輪改了三件事，都要在真的 Discord 上試：

- **選項不會在你看的時候被換掉**：選項出現後、或最後一次按鍵後 6 秒內，新的一組先等著（狀態列會說「新選項好了」），按 R 馬上換，停手幾秒會自己換。
- **選項改成「這個角色自己會說的四種說法」**：不再是同意／追問／反對／玩笑四個固定方向，卡片上只有按鍵和那句話。開發機盲評贏舊版（接得上對話 3.04 對 2.51）。
- **角色模式裝了第一版角色 LoRA**：只用在「這句是不是在叫你」的判斷，開發機上不該回卻回的比例從 9.6% 降到 1.0%，該回的比例不變。setup 會自動安裝，不用設定。

另外要量一個開發機量不到的數字：更大的模型 Gemma 4 E4B 在這台 3050 Ti 上跑不跑得動。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`＋截圖，推到 `laptop-report` 分支（步驟 8）
- 不要讀 `silenttalk.log` 原文，數字一律用步驟 7 的腳本產生

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  最後幾行要有 `[OK] Character LoRA v1 (q8_0)`。`.env` 裡沒有 `DISCORD_BOT_TOKEN` 或 `OWNER_USER_ID` 就停下來問使用者。

- [ ] **2. 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  留下輸出（exit code 0＝通過）。LLM 那段的秒數是四個選項全部寫完的時間，第一個選項會更早出現。

- [ ] **3. UI 截圖**（不用 Discord，約 1 分鐘）
  ```powershell
  .venv\Scripts\python.exe -m pip install pillow
  .venv\Scripts\python.exe scripts\dev\ui_preview.py
  ```
  最後一行要是 `UI flow OK`。PNG 在 `.runtime\dev\ui_preview\`，整個資料夾複製到 `handoff\reports\laptop-ui\`（步驟 8 一起推）。截圖裡都是假資料。打開 `3_choices.png`、`16_held.png`、`13_settings_chat.png` 看一眼：有沒有字被切掉、擠在一起或超出框，有的話寫在回報裡。

- [ ] **4. 量 E4B**（先關掉吃 GPU 的程式；下載約 4.2 GB，下載時可以先做步驟 5）
  ```powershell
  .venv\Scripts\python.exe scripts\setup_copilot.py gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf
  .venv\Scripts\python.exe scripts\dev\bench_hw.py --model gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf --skip-tts
  ```
  留下「==== 貼這張表回來 ====」下面的表。這一步不會改 App 的設定；App 仍然用 E2B。跑不起來（顯示記憶體不足之類）就照實記下錯誤最後幾行。

- [ ] **5. 陪使用者試「選項」模式（約 5 分鐘）**
  用 `啟動 SilentTalk.cmd` 開 App，F8 →「對話」→ 右上角「選項」，進語音頻道（最好有一兩個朋友在聊）。請使用者：

  | # | 請使用者做 | 應該要 |
  |---|---|---|
  | o1 | 朋友連續講好幾句時，看著選項 | 選項不會在看的時候被換掉；狀態列說「新選項好了」時按 R 會換過去 |
  | o2 | 讀四個選項 | 像這個角色會說的話、接得上剛剛那句；問他跟上一輪比如何 |
  | o3 | 被朋友叫名字或問問題時 | 選項有回到那句話 |
  | o4 | 挑一句說出口 | Bot 說出來；問他從對方講完到第一個選項出現大約幾秒 |

  每項記下 OK／不OK 和使用者的原話。

- [ ] **6. 陪使用者試「角色」模式（約 10 分鐘）**
  1. 人設頁選或新建一個人設；「人際關係」加一行：**他自己的 Discord 顯示名稱**＋從角色角度寫的關係，例如「阿明：我老公」「阿明：我爸」「阿明：我兄弟」。
  2. 「對話」→「角色」→ 按「開始」；「開口時機」維持「被叫到才回」。
  3. 逐項試，每項問他感覺如何並記下他的話：

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

- [ ] **7. 整理數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  只輸出數字和事件名稱，整份留下。警告現在會寫出是哪個元件發的（例如 `discord.ext.voice_recv.opus：N packets were lost…`，這個是收音時偶爾掉幾個封包，已知、不用處理）。

- [ ] **8. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md handoff\reports\laptop-ui
  git commit -m "Laptop test report"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗才把報告整份貼給使用者。

## 回報格式（`handoff\reports\laptop.md`）

```markdown
# 筆電測試報告 <日期時間>
commit：<git rev-parse --short HEAD>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## UI 截圖
Windows 顯示比例：<設定 → 顯示 → 縮放，例如 125%>
ui_preview：<UI flow OK 或錯誤>
<看到的切字、擠壓、超框；沒有就寫「無」>

## E4B
<bench_hw 的表，或錯誤最後幾行>

## 選項模式
| # | OK／不OK | 使用者怎麼說 |
|---|---|---|
| o1 | | |
（o2～o4）

## 角色模式
| # | OK／不OK | 使用者怎麼說 |
|---|---|---|
| a | | |
（b～i，選做的主動模式也寫）

## log_summary
<整份輸出>

## 其他
<安裝、啟動、錯誤；沒有就寫「無」>
```
