# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-29 晚上（第二版）｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

上一輪真人語音的辨識結果「部分對，但意思跑掉」（使用者的話），合成語音卻幾乎全對。Discord 語音有第二層端對端加密（DAVE），舊的收音套件有一部分幀沒解開就當聲音解碼；開發機的離線測試（真的 DAVE 加密＋Discord 的封包格式）重現了這種結果，新版在同一個測試裡每一幀都正確還原。也可能辨識器本身對真人聲音就不夠準，所以這一輪的辨識測試**同時量兩條路**：經過 Discord 的，和筆電麥克風直接收的（不經過 Discord）。使用者照著念 8 句，程式自己算錯字率，**不需要任何人判斷辨識結果對不對**。

1. 先做辨識測試（約 3 分鐘，需要使用者念句子）。
2. **平均錯字率 ≤ 15% 才做**角色模式的語音測試（約 10 分鐘）；沒過就停，直接回報（不要再占用使用者時間）。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`，推到 `laptop-report` 分支（步驟 6）
- 不要讀 `silenttalk.log` 原文；`character_state.json`、`personas.json`、`settings.json` 屬於使用者，不要打開看、不要改
- **不要改程式**；有錯照實寫進回報
- 回報只寫數字、事件名稱、使用者自己說的感想；**不寫任何人說過的話、角色說過的話、辨識出來的字**。不要請使用者判斷辨識結果或角色的句子對不對

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  `pip` 那行要看到 `discord-ext-voice-recv` 被重新安裝（來源換成 `LeadFreeCandy/...bec0481...`），並裝上 `sounddevice`。setup 最後幾行要有 `[OK] Gemma 4 E4B QAT Q4_K_XL` 和 `[OK] Character LoRA v3 for E4B (q8_0)`。

- [ ] **2. 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  留下輸出（exit code 0＝通過；選項延遲門檻已改成 4 秒）。

- [ ] **3. 真人辨識測試（需要使用者，約 3 分鐘）**：請使用者進 Discord 語音頻道（頻道裡只有他自己最好），然後執行
  ```powershell
  .venv\Scripts\python.exe app.py --stt-check
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  Bot 會跟著進頻道；終端機一次顯示一句，請使用者用平常的速度念出來。每句印兩個錯字率：經過 Discord 的、筆電預設麥克風直接收的（開不起來會印「只量 Discord 這條路」）。結束時印出兩個平均和 PASS／FAIL（看 Discord 那條）。兩段輸出都留下（只有數字），並記下使用者在 Discord 用的是不是 Windows 預設的麥克風（問他一句就好）。**經過 Discord 的平均錯字率 > 15%（FAIL）就跳到步驟 6**，其餘不做。

- [ ] **4. 角色模式語音測試（需要使用者，約 10 分鐘）**：用 `啟動 SilentTalk.cmd` 開 App，請使用者：
  1. 選一個他自己的人設，開**角色模式**，在語音頻道正常聊：有時叫角色、問它事情；有時自己聊、不理它；中間安靜 30 秒以上一次（角色應該自己開個話題）。
  2. 最後切到**選項模式**聊 2–3 分鐘，用 WASD 選幾次（E4B 產生四個選項約 3 秒，比以前的 E2B 慢約 1 秒）。
  3. 關掉 App 後，問他三個問題，**照他的話記下來**（不想說就寫「沒說」）：
     - 角色開口的時機對不對？（該回沒回、不該插嘴卻插嘴、慢到不自然）
     - 聊完覺得認識這個角色嗎？像個人嗎？有沒有哪裡怪？
     - 選項好不好用？

- [ ] **5. log 數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  整份輸出留下。

- [ ] **6. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md
  git commit -m "Laptop report: real-voice STT check"
  git push -f origin laptop-report
  git switch copilot-story-mode
  ```
  push 失敗才把報告整份貼給使用者。

## 回報格式（`handoff\reports\laptop.md`）

```markdown
# 筆電報告 <日期時間>
commit：<git rev-parse --short HEAD>

## 更新
<pip 裡 voice-recv 那幾行；setup 最後幾行>

## 一鍵驗收
<--copilot-smoke 的輸出，或錯誤最後幾行>

## 真人辨識測試
<--stt-check 的輸出（每句錯字率、平均、PASS/FAIL）>
<log_summary 的整份輸出>

## 角色模式語音測試
<做了／沒做（原因）；三個問題，使用者自己的話>
<log_summary 的整份輸出>

## 其他
<錯誤或狀況；沒有就寫「無」>
```
