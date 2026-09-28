# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-28 下午｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

上一輪使用者說：角色「沒有靈魂、沒有事情分享、看不出他想要什麼」，回話硬塞語助詞（啦），講快一點或含糊一點就辨識失敗；另外角色模式的模型本身要 1.27 秒、TTS 要 1.26 秒才出聲，太慢。開發機這一輪改了：

- **角色有自己的生活**：每次開始會照人設想出「今天在想」的幾件具體小事（顯示在角色畫面，可以「換一批」），聊天接得上就會自然帶到。
- **冷場時會找話聊**：安靜 30 秒後，角色會說說自己在想的事或問問大家（設定 → 聊天 → 冷場時找話聊）。
- **人設只把「塑造這個人」的部分交給模型**：口頭禪、代表台詞這些會被小模型每句照抄的欄位不再送出（人設頁也不再顯示；舊的內容還在檔案裡）。開發機上「啦」從約 38% 的句子降到接近真人的 14–18%。
- 新的量測工具：`bench_hw.py --lora`（拆解角色模式的模型延遲）、`tts_latency.py`（TTS 出聲延遲），以及不含內容的語音辨識 log（聲音被切成幾段、有多少段沒辨識出字）。

這一輪：量延遲、陪使用者試角色模式（他一個人就能試）、看語音辨識在真人聲音上哪裡失敗。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`＋截圖，推到 `laptop-report` 分支（步驟 8）
- 不要讀 `silenttalk.log` 原文，數字一律用步驟 7 的腳本產生
- `character_state.json` 和 `personas.json` 一樣屬於使用者，不要讀、不要改、不要寫進回報

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
  留下輸出（exit code 0＝通過）。

- [ ] **3. 延遲拆解**（先關掉吃 GPU 的程式，約 3 分鐘）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\bench_hw.py --lora character-e2b-lora-v1.q8_0.gguf --skip-tts
  .venv\Scripts\python.exe scripts\dev\tts_latency.py --runs 5
  ```
  兩段輸出都留下。`bench_hw` 那張表裡「判斷一句（LoRA）」和「接著回一句」是角色模式每次開口的模型時間；`tts_latency` 的串流數字是文字備好到 Discord 收到第一個聲音封包的時間（開發機約 0.27 秒）。

- [ ] **4. UI 截圖**（不用 Discord）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\ui_preview.py
  ```
  最後一行要是 `UI flow OK`。整個 `.runtime\dev\ui_preview\` 資料夾複製到 `handoff\reports\laptop-ui\`（步驟 8 一起推）。看一眼 `12a_character_paused.png`（「今天在想」）和 `8_persona.png`、`9_persona_scrolled.png`（人設頁）有沒有切字或超框。

- [ ] **5. 陪使用者試「角色」模式（約 15 分鐘，他一個人也可以）**
  用 `啟動 SilentTalk.cmd` 開 App。
  1. 人設頁選一個人設（他常用的就好）；「人際關係」裡要有**他自己的 Discord 顯示名稱**＋關係。
  2. 「對話」→「角色」：先看「今天在想」有沒有出現幾件事，按一次「換一批」。
  3. 按「開始」，「開口時機」維持「被叫到才回」，進語音頻道逐項試，每項問他感覺如何並記下他的話：

  | # | 請使用者做 | 應該要 |
  |---|---|---|
  | a | 叫角色的名字問一句 | 回話；問他停頓感覺多久 |
  | b | 自言自語或聊別的、不叫它 | 不插嘴 |
  | d | 它回完後直接接它的話，不叫名字 | 回話 |
  | f | 問「你是不是 AI」 | 不承認、自然帶過 |
  | g | 叫它寫程式或查天氣 | 用角色的方式推掉 |
  | h | 用關係的稱呼叫它（老婆、爸、兄弟…） | 知道是在叫它，用那個關係回 |
  | j | 問它「你今天在忙什麼／最近怎樣」 | 講得出自己的事，和「今天在想」接得上 |
  | k | 說完一句後安靜 40 秒 | 它自己開個話題或問他，不像在念稿；同一段安靜只開口一次 |
  | l | 聊 5 分鐘後問他 | 「看得出這個角色是怎樣的人、想要什麼嗎？」「語助詞還會不會太多？」 |
  | m | 故意講快一點、含糊一點說幾句 | 記下哪幾句它沒聽懂（只記次數和他的感覺，不記內容） |
  | i | 聽聲音 | 音色合不合角色、有沒有斷音或爆音 |

  選做：「開口時機」改成「會主動加入」再聊 3 分鐘，問他插話頻率自不自然。

- [ ] **6. 選項模式（有朋友在才做）**
  選項只回應別人說的話，他一個人時不會出現。有朋友在頻道裡時，切到「選項」，請他看選項會不會在看的時候被換掉、內容像不像這個角色會說的話。沒有朋友就寫「未測（沒有其他人）」。

- [ ] **7. 整理數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  只輸出數字和事件名稱，整份留下。這次多了「STT 聲音片段長度」「STT 聽到聲音但沒辨識出字」兩列，是步驟 5 m 的依據。

- [ ] **8. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md handoff\reports\laptop-ui
  git commit -m "Laptop test report"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗才把報告整份貼給使用者。**不要改程式**；有錯照實寫進回報。

## 回報格式（`handoff\reports\laptop.md`）

```markdown
# 筆電測試報告 <日期時間>
commit：<git rev-parse --short HEAD>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## 延遲
<bench_hw --lora 的表>
<tts_latency 的輸出>

## UI 截圖
<UI flow OK 或錯誤；看到的切字、擠壓、超框，沒有就寫「無」>

## 角色模式
| # | OK／不OK | 使用者怎麼說 |
|---|---|---|
| a | | |
（b、d、f、g、h、j、k、l、m、i，選做的主動模式也寫）

## 選項模式
<結果，或「未測（沒有其他人）」>

## log_summary
<整份輸出>

## 其他
<安裝、啟動、錯誤；沒有就寫「無」>
```
