# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-28 傍晚｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

開發機正在把模型從 Gemma 4 E2B 換成 **E4B**（講話明顯比較好，正在替它訓練判斷用的 LoRA），完成後才請使用者做語音測試，免得同一輪測試做兩次。**這一輪不需要使用者，不要找他做語音測試。**

這一輪只做換模型之後也不用重做的事：
1. 更新並確認 App 能正常啟動（上一輪曾經啟動失敗）。
2. 先把 E4B 模型下載好，下一輪直接用。
3. 拆解延遲：上一輪角色開口時模型本身 1.27 秒、TTS 1.26 秒才出聲（開發機 TTS 只要 0.27 秒），要知道慢在哪。
4. UI 截圖（角色畫面多了「今天在想」，人設頁精簡了）。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`＋截圖，推到 `laptop-report` 分支（步驟 6）
- 不要讀 `silenttalk.log` 原文；`character_state.json`、`personas.json` 屬於使用者，不要讀、不要改
- **不要改程式**；有錯照實寫進回報

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf
  ```
  會順便下載 E4B（約 4.2 GB）。最後幾行要有 `[OK] Gemma 4 E4B QAT Q4_K_XL` 和 `[OK] Character LoRA v1 (q8_0)`。

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
  兩段輸出都留下。`tts_latency` 需要網路和 ffmpeg；失敗就留下錯誤最後幾行。

- [ ] **4. UI 截圖**（不用 Discord）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\ui_preview.py
  ```
  最後一行要是 `UI flow OK`。整個 `.runtime\dev\ui_preview\` 資料夾複製到 `handoff\reports\laptop-ui\`。看一眼 `12a_character_paused.png`、`8_persona.png`、`9_persona_scrolled.png` 有沒有切字或超框。

- [ ] **5. 確認 App 會啟動**：用 `啟動 SilentTalk.cmd` 開 App，等 30 秒後關掉，然後
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  只要看「警告／錯誤」裡有沒有 `copilot_startup_failed`，整份輸出留下。不用進語音頻道。

- [ ] **6. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md handoff\reports\laptop-ui
  git commit -m "Laptop report: latency and setup"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗才把報告整份貼給使用者。

## 回報格式（`handoff\reports\laptop.md`）

```markdown
# 筆電報告 <日期時間>
commit：<git rev-parse --short HEAD>

## 更新
<setup 最後幾行>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## 延遲
<bench_hw --lora 的表>
<tts_latency 的輸出>

## UI 截圖
<UI flow OK 或錯誤；看到的切字、擠壓、超框，沒有就寫「無」>

## App 啟動
<log_summary 整份輸出>

## 其他
<錯誤或狀況；沒有就寫「無」>
```
