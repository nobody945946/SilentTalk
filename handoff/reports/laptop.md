# 筆電回報：第 9 回合（量測完成、tunnel 修復、無人值守 skill）

## 1. 機魂劇本

本回合無。

## 2. 時間與額度

2026-10-09，Asia/Taipei（UTC+08:00）。SilentTalk 已拉至 `02af899`，部署 EdgeAgent 維持 `5422f02`。獨立量測先採用上游 `e6bff0d`，修正測試語意後使用 `feabd5e434847316035c4b87d3d9ec7076a3c4f7`。最終量測 01:49:24 開始，02:03 前結束，02:03:09 恢復驗收通過。沒有可靠的帳戶額度或 token 用量資料，不估算。

## 3. 目標完成度

V1 的對照組、兩組有效量測、完成事件與恢復均完成。雙管路產品尚未整體通過：分開 adapter 的角色請求在 Agent 生成時仍 30.02 秒逾時（HTTP 502）。共用現有角色 adapter 的效能對照可以同時回應，但不證明 Agent 工具品質或未來共用 adapter 的品質。

使用者後續明確要求負責修復完成，覆蓋工作檔「不改程式、不要重試」；本回合修正量測 owner、重跑並交付可審閱分支。部署、模型和使用者設定未修改。

上游修正版雖 exit 0，第二組實際兩邊都沒有 adapter，完整視窗也只測 62,186 tokens，留有足以容納角色快取的空間，不能當作原需求證據。已修正第二組為同一個非空 adapter；以整段 tokenizer 二分搜尋填至原預算上限。以下只採用最終有效量測。

Tunnel 已恢復並核對雲端有 1 個 host；WSL 已停止。無人值守 skill 已安裝並完成 trigger 與模型修復驗證。

## 4. 測試執行結果

正式對照組（01:49:22，角色 ready、64K、單槽）：

```json
{"event": "memory_baseline", "vram_used_mib": 3471, "vram_free_mib": 492, "dedicated_mib": 3471.0, "shared_mib": 176.0, "ram_free_mib": 245.4}
```

最終量測兩組原始輸出，程序 exit code 0：

```json
{"lease_lora": "machine-spirit-char-v1.q8_0.gguf", "agent_lora": "", "pool": 65536, "gpu_layers": 41, "memory": {"vram_used_mib": 3533, "vram_free_mib": 430, "dedicated_mib": 3533.0, "shared_mib": 176.0, "ram_free_mib": 288.2}, "alone": [{"status": 200, "first_s": 0.52, "seconds": 0.99, "chunks": 14}, {"status": 200, "first_s": 0.45, "seconds": 1.01, "chunks": 17}, {"status": 200, "first_s": 0.49, "seconds": 1.0, "chunks": 16}], "during_decode": {"character": {"status": 502, "seconds": 30.02}, "agent": {"status": 200, "first_s": 0.34, "seconds": 40.53, "chunks": 1496}}, "during_prompt": {"character": {"status": 200, "first_s": 3.73, "seconds": 4.28, "chunks": 15}, "agent": {"status": 200, "first_s": 54.78, "seconds": 56.2, "chunks": 30}}, "full_window": {"prompt_tokens": 65024, "status": 200, "first_s": 65.44, "seconds": 66.94, "chunks": 30}, "after_full_window": {"status": 200, "first_s": 2.41, "seconds": 2.88, "chunks": 14}, "memory_after": {"vram_used_mib": 3581, "vram_free_mib": 382, "dedicated_mib": 3581.0, "shared_mib": 176.0, "ram_free_mib": 244.2}}
```

```json
{"lease_lora": "machine-spirit-char-v1.q8_0.gguf", "agent_lora": "machine-spirit-char-v1.q8_0.gguf", "pool": 65536, "gpu_layers": 41, "memory": {"vram_used_mib": 3533, "vram_free_mib": 430, "dedicated_mib": 3533.0, "shared_mib": 176.0, "ram_free_mib": 271.7}, "alone": [{"status": 200, "first_s": 0.61, "seconds": 1.23, "chunks": 16}, {"status": 200, "first_s": 0.52, "seconds": 1.14, "chunks": 19}, {"status": 200, "first_s": 0.48, "seconds": 1.12, "chunks": 20}], "during_decode": {"character": {"status": 200, "first_s": 0.62, "seconds": 1.22, "chunks": 16}, "agent": {"status": 200, "first_s": 0.39, "seconds": 49.42, "chunks": 1496}}, "during_prompt": {"character": {"status": 200, "first_s": 3.08, "seconds": 10.5, "chunks": 14}, "agent": {"status": 200, "first_s": 69.91, "seconds": 71.5, "chunks": 30}}, "full_window": {"prompt_tokens": 65024, "status": 200, "first_s": 82.89, "seconds": 84.56, "chunks": 30}, "after_full_window": {"status": 200, "first_s": 2.41, "seconds": 2.88, "chunks": 14}, "memory_after": {"vram_used_mib": 3569, "vram_free_mib": 394, "dedicated_mib": 3569.0, "shared_mib": 176.0, "ram_free_mib": 214.0}}
```

```json
{"event": "lanes_check_done", "runs": 2}
```

恢復：部署目錄執行 `ensure_service()`，再以正常啟動器啟動 SilentTalk。02:03:09 由 trigger 包裝實際 status 驗收，exit code 0：

```json
{"mode": "character", "ready": true, "context_size": 65536, "inference_slots": 1, "lora": "", "character_lora": "machine-spirit-char-v1.q8_0.gguf"}
```

- EdgeAgent：`test_lanes_check.py`、`test_inference.py`、`test_context_pool.py`，21 passed；修改檔案 Ruff 通過。[該提交 CI](https://github.com/nobody945946/EdgeAgent/actions/runs/37819462484) success，head SHA 為 `feabd5e434847316035c4b87d3d9ec7076a3c4f7`。
- SilentTalk 最新工作樹文件測試 4 passed；它驗入口和工作檔，未驗本回報。本回報另驗十節、JSON 和 diff。
- skill validator 通過；工具缺 PyYAML、Windows cp950 無法讀 UTF-8 的問題已用隔離測試套件及 Python UTF-8 模式處理。
- skill 7 項行為測試通過：成功也稽核、非零保留證據、定時／期限事件、啟動失敗、有界輸出、語意事件、只清理自己啟動的程序。
- 模型端實測：隔離 fixture exit 0 並聲稱成功，但 context 32768 不符要求 65536；模型收到 trigger，修正生成 owner，重跑產物及 assertion 通過。wrapper 沒有預寫修法。
- 正式服務的 `production-restored` trigger 也已收取並核對狀態。

## 5. 修改檔案與 commit

EdgeAgent 只修正 `tests/lanes_check.py` 與 `tests/test_lanes_check.py`，提交 `feabd5e` 已推至 `laptop-lanes-measurement`。[Draft PR #1](https://github.com/nobody945946/EdgeAgent/pull/1) 目標 `spec-v2`，未合併、未部署量測分支。量測 worktree 已清除，部署工作樹保持乾淨。

個人 skill 沿用既有 owner `C:/Users/A8fm0/.codex/skills/unattended-self-iteration`，更新入口及 UI metadata，新增 `references/live-triggers.md`、`scripts/audit_trigger.py` 和行為測試。

Windows tunnel 更新既有登入自啟入口，執行官方 CLI 的 `tunnel --name toughtop --no-sleep --reconnection-grace-time 86400 --accept-server-license-terms`，沒有新增第二套服務或改電源方案。回報整份換掉、推至既有 `laptop-report`。

## 6. 記憶體與速度

| 階段 | 顯存 MiB | 共用 GPU 記憶體 MiB | 可用 RAM MiB |
|---|---:|---:|---:|
| 正常單槽對照組 | 3471 | 176 | 245.4 |
| 分開 adapter，雙槽開始 | 3533 | 176 | 288.2 |
| 分開 adapter，完整視窗後 | 3581 | 176 | 244.2 |
| 共用角色 adapter，雙槽開始 | 3533 | 176 | 271.7 |
| 共用角色 adapter，完整視窗後 | 3569 | 176 | 214.0 |

| 場景 | 分開 adapter，角色首輸出秒 | 共用角色 adapter，角色首輸出秒 |
|---|---:|---:|
| 單獨三次 | 0.52 / 0.45 / 0.49 | 0.61 / 0.52 / 0.48 |
| Agent 正在生成 | 30.02 秒 HTTP 502、無首輸出 | 0.62 |
| Agent 正在讀長提示 | 3.73 | 3.08 |
| Agent 使用完整視窗後 | 2.41 | 2.41 |

兩組完整提示均 65,024 tokens，保留原輸出及模板預算，未降低 65,536 context。角色快取約 1,480 tokens，合計超出池大小，這次有實際快取空間壓力。Agent 完整視窗及之後角色請求都 HTTP 200。

雙槽開始比正常對照多 62 MiB，但 batch、快取及 app 是否運行也有差異，不能全歸因於第二個槽。共用 GPU 記憶體固定 176 MiB，沒有觀察到增加。

02:01 查 System 的 Resource-Exhaustion-Detector 事件 2004，本回合計數 0；未觀察桌面通知，不能據此宣稱沒有通知。可用 RAM 很少，以上為實際數字。

## 7. Discord 數字表

本回合無 Discord 語音實測；HTTP 及服務 ready 不等同 Discord 語音驗收。

## 8. 紀錄目錄

沒有讀寫對話紀錄或角色狀態，未改紀錄目錄或使用者設定。回報只含測試數字、事件和操作證據，不含私人對話。

## 9. 使用者回饋

使用者要求不用監看過程，重要階段由模型主動稽核、修復，本 session 不關閉。使用者表示不需要 WSL，要求不要占記憶體；已停止 WSL 運行，未刪 Ubuntu 或資料。

## 10. 給接手模型的交接指示

量測已完成，正式服務恢復角色 ready、64K、單槽。共用角色 adapter 僅為效能測試，不能直接當作 Agent 正式 adapter 出貨；分開 adapter 的 decode 場景逾時是實測限制。量測 owner 已修正並附 PR，勿交給使用者做安裝或重跑。

Tunnel 名稱 `toughtop`，https://vscode.dev/tunnel/toughtop ，使用原 GitHub 帳號。原 offline 的直接原因是 tunnel 程序沒有運行：當時 status tunnel=null、service_installed=true；官方 log 記錄 RPC client 要求 shutdown，無法確認發送者。沒有證據指向帳號失效或網路故障。修復後本機 Connected；02:04 雲端 HTTP 200、endpoint=1、hostConnectionCount=1。未實測使用者瀏覽器登入。power request 確認 code-tunnel 持有防睡眠請求；Web 斷線寬限 86,400 秒。不保證重開機後舊 shell 仍存在；登入自啟需要登入 Windows。

WSL Ubuntu=Stopped，vmmemWSL 未運行，未移除 WSL；不要擅自刪資料。

`unattended-self-iteration` 在活躍執行時對里程碑、完成、定時、逾時送事件，當前模型依證據 audit → 定位 → 修復 → 驗證；恢復和交付也驗。腳本只傳事件、不猜修法、不無限重試、不開第二模型、不改 hook trust。沿用既有工具 session，不為 wrapper 重跑操作。只保持視窗開啟不能讓 idle turn 自行喚醒；本次以持續工具等待驅動，未建立 Goal 或 scheduler。任務完成後停止輪詢。
