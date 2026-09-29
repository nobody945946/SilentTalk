# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-29 傍晚｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

預設模型換成 **Gemma 4 E4B＋第三版角色 LoRA**（LoRA 用在「要不要開口」和「角色說的話」）。開發機的盲評：台詞 59% 對 40% 贏沒有 LoRA 的 E4B、比較認識這個人 27 對 15；不該開口卻開口從 9.1% 降到 0.5%。

這一輪：
1. 先量 3050 Ti 上套 LoRA 的延遲（不需要使用者）。**超過步驟 4 的門檻就停，不要找使用者做語音測試**，直接回報。
2. 延遲可以接受，才請使用者做一次語音測試（約 15 分鐘）。這是 E4B 的第一次也是唯一一次語音測試。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`，推到 `laptop-report` 分支（步驟 7）
- 不要讀 `silenttalk.log` 原文；`character_state.json`、`personas.json`、`settings.json` 屬於使用者，不要打開看、不要改（步驟 2 是用 App 自己的讀取程式，只印模型名稱）
- **不要改程式**；有錯照實寫進回報
- 回報只寫數字、事件名稱、使用者自己說的感想；**不寫任何人說過的話、角色說過的話**

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  最後幾行要有 `[OK] Gemma 4 E4B QAT Q4_K_XL` 和 `[OK] Character LoRA v3 for E4B (q8_0)`。

- [ ] **2. 確認 App 實際會用什麼**
  ```powershell
  .venv\Scripts\python.exe -c "from pathlib import Path; from silenttalk.config import load_effective_tables as t, _adapter_for as a, _lora_uses as u; c=t(Path('.'))['copilot']; m=c['llm_model']; print(m, a(m, c.get('character_lora',''), u(c.get('character_lora_uses'))))"
  ```
  應該印出 `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf ('character-e4b-lora-v3.q8_0.gguf', ('called', 'active', 'line'))`。不是的話，是使用者在設定頁選過別的模型：步驟 3、4 照做，到步驟 5 前問他一句「要不要在 設定 → 本機模型 換成 Gemma 4 E4B？」（他不換就不做語音測試）。

- [ ] **3. 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  留下輸出（exit code 0＝通過）。

- [ ] **4. 延遲**（先關掉吃 GPU 的程式，約 5 分鐘）
  ```powershell
  .venv\Scripts\python.exe scripts\dev\bench_hw.py --model gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf --skip-tts
  .venv\Scripts\python.exe scripts\dev\bench_hw.py --model gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf --lora character-e4b-lora-v3.q8_0.gguf --lora-uses called,active,line --skip-tts
  ```
  兩張表都留下。**門檻**（第二張表）：「判斷一句」中位數 ≤ 600 ms，而且「生成速度（LoRA）」≥ 15 token/s。沒過 → 跳到步驟 7 回報，不做步驟 5、6。

- [ ] **5. 語音測試（需要使用者，約 15 分鐘）**：用 `啟動 SilentTalk.cmd` 開 App，請使用者：
  1. 選一個他自己的人設，開**角色模式**，進語音頻道，和朋友（或自己）正常聊 10 分鐘左右：有時叫角色、問它事情；有時大家自己聊、不理它；中間安靜 30 秒以上一次（角色應該自己開個話題）。
  2. 有一兩句講快一點、含糊一點（看語音辨識）。
  3. 最後切到**選項模式**聊 2–3 分鐘，用 WASD 選幾次。
  4. 關掉 App 後，問他三個問題，**照他的話記下來**（他不想說就寫「沒說」）：
     - 角色開口的時機對不對？（該回沒回、不該插嘴卻插嘴、慢到不自然）
     - 聊完覺得認識這個角色嗎？像個人嗎？有沒有哪裡怪（例如語尾「啦」太多）？
     - 選項好不好用？

- [ ] **6. log 數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  整份輸出留下（只有數字和事件名稱）。

- [ ] **7. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md
  git commit -m "Laptop report: E4B with the v3 adapter"
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

## App 實際用的模型
<步驟 2 印出的那一行；使用者有沒有換>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## 延遲
<E4B 沒有 LoRA 的表>
<E4B＋v3 LoRA 的表>
<門檻：過／沒過（哪一項）>

## 語音測試
<做了／沒做（原因）；大約幾分鐘、角色模式幾分鐘、選項模式幾分鐘>
<三個問題，使用者自己的話>

## log 數字
<log_summary 整份輸出>

## 其他
<錯誤或狀況；沒有就寫「無」>
```
