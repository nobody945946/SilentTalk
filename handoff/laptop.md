# Windows 工作檔：第 8 回合（雙管路實機量測）

更新：2026-10-08 晚｜SilentTalk `copilot-story-mode`｜EdgeAgent 量測程式在分支 `spec-v2`（`6b8c393`）｜回報 `laptop-report`｜上一版：開發機 `archive/laptop-2026-10-07-round7a.md`（不必讀）

## 這回合只做一件事

使用者要求：在 Discord 語音裡和機魂講話時，不能因為 Agent 在做事就等很久，而且 **Agent 的 64K 是底線，不能降**。現在的設計是 Agent 一開工就獨佔模型，角色只能等它做完。

開發機的新設計（還沒出貨）：同一個 64K 池子分成兩個槽，角色和 Agent 各用一個、各自保留快取。Agent 永遠拿得到完整 64K（需要時清掉角色的小快取）；角色開口時，Agent 還在讀提示的請求先讓開。開發機量過：第二個槽只多約 11 MiB 顯存。但使用者說得對，這要在**這台筆電**上量才算數。這回合就是量它：顯存、共用記憶體（溢出顯卡）、可用 RAM、角色回話的延遲，以及 Agent 在角色占著快取時還能不能用滿整個視窗。

**不改任何程式、不出貨、不動使用者的檔案。** 量測程式在暫存資料夾裡開一個臨時核心，只讀 `C:\Users\A8fm0\EdgeAgent\config.json`。

## 步驟

1. 在 SilentTalk 執行 `git pull --ff-only`；拉不下來就停下回報。
2. 準備量測程式（另開一個資料夾，**不要**切換已部署的 EdgeAgent 分支）：

   ```powershell
   git -C C:\Users\A8fm0\EdgeAgent fetch origin spec-v2
   git -C C:\Users\A8fm0\EdgeAgent worktree add --detach C:\Users\A8fm0\ea-lanes origin/spec-v2
   git -C C:\Users\A8fm0\ea-lanes log --oneline -1
   ```

   預期：最後一行是 `6b8c393 lanes_check: --memory-only ...`。不是就停下回報。

3. **對照組**（現行版本照平常運作時，SilentTalk 和 EdgeAgent 都開著）：

   ```powershell
   $env:PYTHONPATH = 'C:\Users\A8fm0\ea-lanes'
   C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe C:\Users\A8fm0\ea-lanes\tests\lanes_check.py --memory-only
   (Invoke-RestMethod http://127.0.0.1:18087/status) | Select-Object mode, ready, context_size, inference_slots, model, lora, character_lora
   ```

   預期：一行 `{"event": "memory_baseline", ...}`，加上 status。照抄進回報。

4. **選時機**：看 SilentTalk 的 log，最近 10 分鐘有語音活動（有人在講話）就等 10 分鐘再看。量測約 15–20 分鐘，期間機魂不在線。不要叫使用者做任何事。
5. 停掉 SilentTalk 和 EdgeAgent（和前幾回合一樣：先核對命令列，只用 PID 停 SilentTalk 的 app 和 launcher），再：

   ```powershell
   edge-agent stop
   Get-NetTCPConnection -LocalPort 18087,18089 -State Listen -ErrorAction SilentlyContinue
   ```

   預期：第二個指令沒有輸出（兩個連接埠都空了）。還有就等 10 秒再查；1 分鐘後還在就停下回報，不要硬殺。

6. **量測**：

   ```powershell
   $env:PYTHONPATH = 'C:\Users\A8fm0\ea-lanes'
   C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe C:\Users\A8fm0\ea-lanes\tests\lanes_check.py --install C:\Users\A8fm0\EdgeAgent
   ```

   預期：兩行 JSON（第一行 `lease_lora` 是角色的 adapter，第二行是一個 adapter 兩邊共用），最後一行 `{"event": "lanes_check_done", "runs": 2}`。
   - 失敗或 Windows 跳出記憶體不足：把錯誤的最後 20 行和當下的可用 RAM 抄進回報，直接進第 7 步，**不要改程式、不要重試第二次**。
   - 跑超過 40 分鐘沒結束：用 PID 停掉這個 python 程序和它開的 llama-server（核對命令列裡有 `ea-lanes` 或暫存資料夾 `edge-lanes-`），寫進回報，進第 7 步。

7. **恢復**（一定要做，不管第 6 步結果如何）：

   ```powershell
   Set-Location C:\Users\A8fm0\EdgeAgent
   .\.venv\Scripts\python.exe -c "from edge_agent.api import ensure_service; ensure_service()"
   ```

   再用平常的方式啟動 SilentTalk（`啟動 SilentTalk.cmd`）。等 SilentTalk 取得租約後查 status，預期 `mode` 為 `character`、`ready` 為 true、`context_size` 為 65536。

8. 清掉量測資料夾：`git -C C:\Users\A8fm0\EdgeAgent worktree remove --force C:\Users\A8fm0\ea-lanes`
9. 推回報（整份換掉，推到 `laptop-report`）。

## 回報格式（沿用固定十節）

機魂劇本（本回合無）／時間與額度／目標完成度（V1：對照組＋量測兩行＋恢復成功）／測試執行結果（第 3、6 步的輸出原樣貼上；這些 JSON 只有數字，沒有對話內容）／修改檔案與 commit（應該是無）／記憶體與速度（第 3 和第 6 步的顯存、共用記憶體、可用 RAM；Windows 有沒有記憶體不足的通知）／Discord 數字表（本回合無）／紀錄目錄（本回合沒碰）／使用者回饋（使用者自己說的感想，原話照錄）／給接手模型的交接指示。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄。
- 不動 `.env`、`settings.json`、`personas.json`、`character_state.json`；EdgeAgent 的 `config.json` 只讀。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事。
- 關程式只用核對過的 PID。
