# 筆電工作檔（Windows、RTX 3050 Ti）

更新：2026-09-29 晚上｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫這台機器要做的事。

## 目的

上一輪確認了真人語音經過 Discord 的辨識修好了：DAVE 解密 963 幀成功 961、沒有解碼錯誤；照字念完的六句錯字率 0%、0%、0%、7.7%、0%、10.0%（程式算的 18.9% 是因為有一句沒念、一句結巴）。**這一輪不用再做念句子的測試**（使用者說他好幾天沒說話、念不順，不要再請他念）。

這一輪終於要看**角色本身**：E4B＋第三版 LoRA 在真的聊天裡表現怎樣。

- 專案：`C:\Users\A8fm0\Downloads\SilentTalk`
- 回報：寫 `handoff\reports\laptop.md`，推到 `laptop-report` 分支（步驟 5）
- 不要讀 `silenttalk.log` 原文；`character_state.json`、`personas.json`、`settings.json` 屬於使用者，不要打開看、不要改
- **不要改程式**；有錯照實寫進回報
- 回報只寫數字、事件名稱、使用者自己說的感想；**不寫任何人說過的話、角色說過的話、辨識出來的字**。不要請使用者判斷辨識結果或角色的句子對不對
- 終端機要開在使用者看得到的地方（上一輪第一次開在看不到的終端機，白等了一次）

## 步驟

- [ ] **1. 更新**
  ```powershell
  git fetch origin
  git switch copilot-story-mode
  git pull
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_copilot.py
  ```
  setup 最後幾行要有 `[OK] Gemma 4 E4B QAT Q4_K_XL` 和 `[OK] Character LoRA v3 for E4B (q8_0)`。

- [ ] **2. 一鍵驗收**
  ```powershell
  .venv\Scripts\python.exe app.py --copilot-smoke
  ```
  留下輸出（exit code 0＝通過）。

- [ ] **3. 角色模式語音測試（需要使用者，約 10–15 分鐘，找他方便、有朋友在語音的時候）**：用 `啟動 SilentTalk.cmd` 開 App，請使用者：
  1. 選一個他自己的人設，開**角色模式**，進語音頻道和朋友正常聊（他自己不想講話的話，打字或只聽都可以；主要是朋友在講）：有時叫角色、問它事情；有時大家自己聊、不理它；中間安靜 30 秒以上一次（角色應該自己開個話題）。
  2. 最後切到**選項模式**聊幾分鐘，用 WASD 選幾次（E4B 產生四個選項約 2.5–3 秒）。
  3. 關掉 App 後，問他三個問題，**照他的話記下來**（不想說就寫「沒說」）：
     - 角色開口的時機對不對？（該回沒回、不該插嘴卻插嘴、慢到不自然）
     - 聊完覺得認識這個角色嗎？像個人嗎？有沒有哪裡怪？
     - 選項好不好用？

- [ ] **4. log 數字**
  ```powershell
  .venv\Scripts\python.exe scripts\dev\log_summary.py
  ```
  整份輸出留下。

- [ ] **5. 回報**：照下面格式寫 `handoff\reports\laptop.md`，然後
  ```powershell
  git switch -C laptop-report
  git add handoff\reports\laptop.md
  git commit -m "Laptop report: character mode with E4B"
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

## 角色模式語音測試
<做了／沒做（原因）；大約幾分鐘、角色模式幾分鐘、選項模式幾分鐘、頻道裡大約幾個人>
<三個問題，使用者自己的話>

## log 數字
<log_summary 整份輸出>

## 其他
<錯誤或狀況；沒有就寫「無」>
```

## 附：念句子的辨識測試（這一輪不做）

以後要重新確認語音辨識時用 `app.py --stt-check`：主人照著念 8 句，念完按 Enter、念錯按 r 重念、按 s 跳過（跳過的不算），程式自己算錯字率，同時量筆電麥克風直接收的（會印出麥克風名稱和音量）。
