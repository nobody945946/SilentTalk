# Windows 工作檔：第 11 回合（出貨：Agent 和機魂共用一個新 adapter、機魂的語音修好）

更新：2026-10-13｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`｜回報 `laptop-report`｜上一版：開發機 `archive/laptop-2026-10-09-round10.md`（不必讀）

## 為什麼有這一回合

1. **機魂現在不會說話。** 微軟 10/10 起把 Edge 朗讀搬到新位址，舊位址一律回 403；edge-tts 最新版還在用舊的。SilentTalk 已改走新位址（`8b0e317`），忙線（429／503）會在出聲前再試一次。玩家下載的版本也壞了，所以這回合驗過之後，開發機會發新的公開版。
2. **新的 adapter：`machine-spirit-fw3n.q8_0.gguf`。** 一個 adapter 同時給 Agent 和機魂用，取代 `agent-fw1` 和 `machine-spirit-char-v1` 兩個。共用一個才能讓兩個槽一起跑：你上次量到角色回話 0.62 秒，兩個不同 adapter 時要等超過 30 秒。開發機的考試（和不套 adapter 的 E4B 比，各用自己最好的溫度）：
   - 思考關 78 比 60–64；思考開 91 比 86–89（基底量了兩次）。
   - 沒見過的情境卡 39 比 35；Python 題 36 比 21。
   - 機魂台詞和 char-v1 打平（76 組：31 比 33，12 組平手）；聊天工作 37/40（char-v1 39/40；漏的三題都是「查最新消息」，下一版補，這回合不用測）。
3. **一起出貨的 EdgeAgent 修正：**
   - 每個 adapter 帶自己的溫度（這個是思考關 1.0、思考開 0.2），從檔案讀，不用設定。
   - 模型程序當掉會自己重新載入。以前 router 還活著，但每個請求都回「model is not loaded」。
   - Agent 輸出不設上限；一直重複同一段就停下，畫面顯示「輸出一直重複同一段，已停止」。

## 協定（不變）

session 開始時 `git pull --ff-only`；這份是還沒做完的回合，就先推收件回條（`git push -f -q origin HEAD:refs/heads/laptop-received`），再照做。回報推上去之後再 pull 一次；工作檔沒換就結束。不要常駐迴圈、排程、log 檔。

## 步驟

每一步失敗時，照該步寫的處理；沒寫的就停下，把錯誤最後 20 行寫進回報，跳到第 10 步（恢復）。

1. **拉新版：**
   ```powershell
   git -C C:\Users\A8fm0\SilentTalk pull --ff-only
   git -C C:\Users\A8fm0\EdgeAgent pull --ff-only
   git -C C:\Users\A8fm0\EdgeAgent merge-base --is-ancestor b73f0ff HEAD; $LASTEXITCODE
   git -C C:\Users\A8fm0\SilentTalk merge-base --is-ancestor a27a100 HEAD; $LASTEXITCODE
   ```
   預期：兩個 pull 都成功，後兩行都印 `0`。不是 0 就停下回報，其他步驟標「沒測」。
2. **收件回條**（上面那一行）。確認 `git ls-remote origin refs/heads/laptop-received` 的 sha 等於 SilentTalk 的 `git rev-parse HEAD`。
3. **部署：** 在 EdgeAgent 執行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -SetupOnly`。
   - 預期：exit 0，`models\machine-spirit-fw3n.q8_0.gguf` 存在，約 55 MB。部署會驗 SHA256，對不上會自己重新複製。
   - 舊的 `agent-fw1`、`machine-spirit-char-v1` 留在 `models` 不用刪。
4. **兩個 repo 的完整測試**（看 pytest 自己的 exit code）：
   - EdgeAgent：`PYTHONIOENCODING=utf-8`、取消 `PYTHONUTF8`、`EDGE_AGENT_UI_REGRESSION=1`、`--basetemp .test-tmp`。
   - SilentTalk：`PYTHONUTF8=1`、`--basetemp .test-tmp`。
   - 預期：都是 0 failed。失敗的若只在 Windows 出現，由你修（AGENTS.md 分工），補測試後推 `copilot-story-mode`，等 CI 綠。不是 Windows 的問題就寫進回報，不要改。
5. **介面一件（你的範圍）：** EdgeAgent 模型頁的 adapter 說明（`edge_agent/web.py`，「附帶給 E4B 使用的兩個 adapter…」那段）現在會把同一個檔名列兩次。改成一句話：附帶一個 E4B 的 adapter，Agent 和機魂共用（檔名從 `runtime.AGENT_ADAPTER` 取）。改 `tests/test_web_ui.py` 對應的斷言，先紅後綠，推 `copilot-story-mode`，等 CI 綠。
6. **重載成新版：**
   ```powershell
   edge-agent stop
   Get-NetTCPConnection -LocalPort 18087,18089 -State Listen -ErrorAction SilentlyContinue
   ```
   - 第二個指令要沒有輸出。還有就等 10 秒再查；1 分鐘後還在就停下回報，不要硬殺。
   - SilentTalk 先核對命令列，只用 PID 停它的 app 和 launcher。
   - 再啟動：`Set-Location C:\Users\A8fm0\EdgeAgent; .\.venv\Scripts\python.exe -c "from edge_agent.api import ensure_service; ensure_service()"`。
   - 在模型頁的「LoRA（選用）」選 `machine-spirit-fw3n.q8_0.gguf`，其他設定照現在的，不手改 `config.json`。
   - 用平常的方式開 SilentTalk（`啟動 SilentTalk.cmd`）。
7. **確認狀態：**
   ```powershell
   (Invoke-RestMethod http://127.0.0.1:18087/status) | Select-Object mode, ready, context_size, inference_slots, model, lora, character_lora
   ```
   - 預期：`mode`＝character、`ready`＝True、`lora` 和 `character_lora` 都是 `machine-spirit-fw3n.q8_0.gguf`。
   - `character_lora` 還是 char-v1：多半是 SilentTalk 設定頁存過舊值。用 SilentTalk 設定頁改回預設，不手改 `settings.json`，寫進回報。
8. **雙管路實量**（和第 8 回合同一支程式，約 15–20 分鐘，期間機魂不在線）：
   - 先看 SilentTalk 的 log。最近 10 分鐘有人在語音裡講話，就等 10 分鐘再看。
   - 照第 6 步停掉兩個服務，然後執行：
     ```powershell
     $env:PYTHONPATH = 'C:\Users\A8fm0\EdgeAgent'
     C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe C:\Users\A8fm0\EdgeAgent\tests\lanes_check.py --install C:\Users\A8fm0\EdgeAgent
     ```
   - 預期：兩行 JSON，最後 `{"event": "lanes_check_done", "runs": 2}`。這次兩行用的是同一個 adapter，角色回話要和你上次量的 0.62 秒同一個等級。
   - 失敗或記憶體不足：最後 20 行和可用 RAM 抄進回報，不要重試。
   - 做完照第 6 步把兩個服務開回來，重查第 7 步。
9. **Discord 真人測試（需要使用者，一次只請他做一件事）：** 只用伺服器 729722190857240717、語音頻道 729722190857240721；工作區只用 `C:\Users\A8fm0\EdgeAgentTest`；批准由使用者自己按；只查檔案數量、大小、時間，不讀內容。
   - D1 語音喊「機魂」問一句話：**機魂用語音回答**（這是語音修正的驗收）。沒有名字不回。
   - D2 主人 @ 開 Agent 串：「EdgeAgentTest 裡有幾個 .tmp」→ 唯讀跑、不問批准、結果貼串。
   - D3 主人在串裡請它寫一個小程式並執行（例如「在 EdgeAgentTest 寫一個把資料夾裡的 .txt 合併成一個檔的 PowerShell 腳本，執行一次」）。Agent 做事的同時，使用者在語音喊「機魂」問一句：機魂馬上用語音回，不用等 Agent 做完。記下角色回話的延遲（SilentTalk log 的數字）。
   - D4 使用者對機魂和 Agent 的感想，原話照錄。
10. **恢復與清理：** 兩個服務都在跑、`/status` 正常；`.test-tmp` 可留。
11. **回報：** 整份換掉 `handoff/reports/laptop.md`，推到 `laptop-report`。
    - 開頭寫「第 11 回合：完成」，或「第 11 回合：卡在第 N 步」。
    - 版面沿用固定十節：機魂劇本（本回合無）／時間與額度／目標完成度（分母 11：第 1–8 步各 1、D1–D3 各 1）／測試執行結果（pytest 數字、第 7、8 步的輸出原樣貼上，只有數字）／修改檔案與 commit／記憶體與速度／Discord 數字表／紀錄目錄（本回合沒碰）／使用者回饋／給接手模型的交接指示。
    - 開發機看到 D1 通過、兩個 repo 測試全過，就發公開版給玩家，你不用做。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄。
- 不動 `.env`、`settings.json`、`personas.json`、`character_state.json`；EdgeAgent 的 `config.json` 只讀。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事。
- 關程式只用核對過的 PID。
- 推 commit 到 EdgeAgent 或 SilentTalk 之後，等那次 push 的 GitHub 檢查跑完；失敗就修好再結束回合，修不了寫進回報。
