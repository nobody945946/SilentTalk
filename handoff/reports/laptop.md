# 第 11 回合：卡在第 9 步（等待真人 Discord 驗收）

更新：2026-10-13T17:31:44+08:00。使用者已重新授權完成第 11 回合，只做必要部分；因此只啟動本回合必要的 EdgeAgent 與 SilentTalk，其他清理後關閉的程式、自啟動設定保持原狀。

## 1. 機魂劇本

本回合無。

## 2. 時間與額度

自動補驗從 2026-10-13T17:15:47+08:00 開始，17:27:55 角色與 Discord 就緒，17:31:44 重查狀態正常。API token／帳戶額度沒有可用證據，不推算。

## 3. 目標完成度

8/11：第 1–8 步均完成；D1、D2、D3 尚未取得真人驗收結果。第 10 步恢復完成，兩個服務均在執行。不能把本機工具探測、量測中的合成角色請求當作 Discord 真人通過；尚不符合 D1 通過後發布語音修正版的條件。

兩個 repo 已 pull，指定祖先檢查通過，SilentTalk HEAD／收件回條為 `03070c0798bcf7a4b7a33d544d039ca5fa556793`。SilentTalk 實際路徑為 `C:\Users\A8fm0\Downloads\SilentTalk`，工作檔舊路徑不存在。已通過的完整測試與 CI 直接沿用，沒有為恢復回合重跑。

## 4. 測試執行結果

- SilentTalk 完整 pytest：367 passed、1 skipped、2 warnings，15.77 秒，exit 0。
- EdgeAgent 完整 pytest（`EDGE_AGENT_UI_REGRESSION=1`）：446 passed、6 skipped、1 warning，234.26 秒，exit 0。完整測試後增加的 runtime 路徑案例，連同部署測試補跑 23 passed，exit 0。
- `ruff check edge_agent tests`、`git diff --check`：exit 0；模型頁對應測試先紅後綠。
- 先前兩個 Windows 失敗來自舊權限 fixture，已修正，8 項相關測試通過；Unicorn 的原生 access-violation 診斷仍會印出，三項測試通過、pytest exit 0，未宣稱診斷消失。
- 第 6 步：既有模型頁選上 fw3n，SilentTalk 設定讀回也是 fw3n，無須改設定。停機量測前 SilentTalk 原本未執行、log 最後更新 2026-10-09，無最近十分鐘語音活動。將量測集中在同一次停機內，做完才一次恢復兩個 app。
- `tests/lanes_check.py --install C:\Users\A8fm0\EdgeAgent`：exit 0、runs 2，所有量測請求 status 200；沒有重試或改記憶體設定。
- 正常啟動器 exit 0，`app.py --character-mode` 執行；新 session 的 `discord_ready`、`character_lease_connected`、`copilot_runtime_ready` 各 1，啟動 warning／error 0。
- 第 7 步正式 SilentTalk 租用的狀態（17:31:44 查核）：

```json
{"mode":"character","ready":true,"context_size":65536,"inference_slots":2,"model":"gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf","lora":"machine-spirit-fw3n.q8_0.gguf","character_lora":"machine-spirit-fw3n.q8_0.gguf"}
```

第 8 步原始數字輸出：

```json
{"lease_lora": "machine-spirit-fw3n.q8_0.gguf", "agent_lora": "machine-spirit-fw3n.q8_0.gguf", "pool": 65536, "gpu_layers": 41, "memory": {"vram_used_mib": 3533, "vram_free_mib": 430, "dedicated_mib": 3533.0, "shared_mib": 176.0, "ram_free_mib": 110.0}, "alone": [{"status": 200, "first_s": 0.66, "seconds": 1.22, "chunks": 16}, {"status": 200, "first_s": 0.45, "seconds": 0.92, "chunks": 14}, {"status": 200, "first_s": 0.44, "seconds": 0.89, "chunks": 14}], "during_decode": {"character": {"status": 200, "first_s": 0.61, "seconds": 1.14, "chunks": 14}, "agent": {"status": 200, "first_s": 0.44, "seconds": 49.36, "chunks": 1496}}, "during_prompt": {"character": {"status": 200, "first_s": 2.81, "seconds": 9.78, "chunks": 14}, "agent": {"status": 200, "first_s": 66.45, "seconds": 68.06, "chunks": 30}}, "full_window": {"prompt_tokens": 65024, "status": 200, "first_s": 80.56, "seconds": 82.78, "chunks": 30}, "after_full_window": {"status": 200, "first_s": 2.38, "seconds": 2.84, "chunks": 14}, "memory_after": {"vram_used_mib": 3569, "vram_free_mib": 394, "dedicated_mib": 3569.0, "shared_mib": 176.0, "ram_free_mib": 698.4}}
{"lease_lora": "machine-spirit-fw3n.q8_0.gguf", "agent_lora": "machine-spirit-fw3n.q8_0.gguf", "pool": 65536, "gpu_layers": 41, "memory": {"vram_used_mib": 3533, "vram_free_mib": 430, "dedicated_mib": 3533.0, "shared_mib": 176.0, "ram_free_mib": 79.6}, "alone": [{"status": 200, "first_s": 0.66, "seconds": 1.2, "chunks": 15}, {"status": 200, "first_s": 0.48, "seconds": 0.95, "chunks": 14}, {"status": 200, "first_s": 0.5, "seconds": 1.12, "chunks": 19}], "during_decode": {"character": {"status": 200, "first_s": 0.53, "seconds": 1.69, "chunks": 17}, "agent": {"status": 200, "first_s": 0.47, "seconds": 49.66, "chunks": 1496}}, "during_prompt": {"character": {"status": 200, "first_s": 2.98, "seconds": 10.27, "chunks": 14}, "agent": {"status": 200, "first_s": 69.34, "seconds": 70.97, "chunks": 30}}, "full_window": {"prompt_tokens": 65024, "status": 200, "first_s": 83.05, "seconds": 84.75, "chunks": 30}, "after_full_window": {"status": 200, "first_s": 2.42, "seconds": 2.89, "chunks": 14}, "memory_after": {"vram_used_mib": 3569, "vram_free_mib": 394, "dedicated_mib": 3569.0, "shared_mib": 176.0, "ram_free_mib": 849.1}}
{"event": "lanes_check_done", "runs": 2}
```

## 5. 修改檔案與 commit

本次補驗沒有改程式碼。前段 EdgeAgent `206efdce5bc42214b10f443009642546e58e577c` 已推 `copilot-story-mode`，CI `https://github.com/nobody945946/EdgeAgent/actions/runs/38373694367` completed／success；first-launch job 依工作流程跳過。

該 commit 修改 `README.md`、`scripts/bootstrap.ps1`、`edge_agent/runtime.py`、`edge_agent/web.py`、`tests/test_bootstrap_windows.py`、`tests/test_deploy.py`、`tests/test_web_ui.py`、`tests/test_sdk_agent.py`、`tests/test_sdk_permissions.py`、`tests/browser_check.mjs`：EdgeAgent 自備 Python／Git／Node／PowerShell，既有 venv 遷移保留套件，共用 adapter 說明修正，Windows fixture 更新。SilentTalk 程式碼沒有修改。本回報整份重寫到 `laptop-report`。

## 6. 記憶體與速度

65,536 context、41 GPU 層、省 VRAM 設定均保留。雙管路單獨角色首字 0.44–0.66 秒；Agent 生成中 0.61／0.53 秒，與先前 0.62 秒同一等級；Agent 讀長輸入時 2.81／2.98 秒，角色整句 9.78／10.27 秒，不能稱此情況也在一秒內完成。65,024 token 的全視窗請求兩輪均 status 200；完成後角色仍可回話。數值詳見原輸出。

量測時顯存最高觀察值 3,569 MiB、共享 GPU 176 MiB；可用 RAM 最低觀察值 79.6 MiB。沒有 OOM 或請求失敗，也沒有為騰 RAM 復活或關閉無關程式。早前獨立 Agent 唯讀工具探測通過（fw3n 10,047 ms、零批准），不能算 D2。

## 7. Discord 數字表

| 項目 | 狀態 |
|---|---|
| D1 真人語音回答 | 待使用者進指定頻道講話、確認聽到 |
| D2 主人串唯讀計數 | 待驗 |
| D3 Agent 工作時並行語音 | 待驗 |
| D4 真人感想 | 未取得；不擴張必要驗收 |

只用伺服器 729722190857240717、語音頻道 729722190857240721、工作區 `C:\Users\A8fm0\EdgeAgentTest`。主人批准由使用者自己按。17:28 已提出 D1 請求；截至本次回報未取得 D1 回答，不自動選擇「有聽到」。

## 8. 紀錄目錄

本回合沒改紀錄設定，沒有讀使用者對話紀錄、人設或角色狀態。日誌僅由數字摘要工具在記憶體篩選事件、時間、數字與錯誤類型，沒有輸出對話內容。app 依既有規則只記錄到使用者指定的 `C:\Users\A8fm0\AgentRecords`。舊 `.test-tmp` 改名保留，未讀內容或改 ACL；沒有新增常駐迴圈、排程或對話 log。

## 9. 使用者回饋

使用者重新要求完成第 11 回合、只做必要部分，並詢問是否需留在語音頻道。已告知量測期間無須留在頻道，恢復後才安排真人驗收。這些是工作方向與安排，不是 D4 試聽感想。

## 10. 給接手模型的交接指示

接續第 9 步，一次只請使用者做一件事：D1 喊機魂並聽語音；通過後 D2 主人 @ 開 Agent 串問 .tmp 數，應不問批准且結果貼串；接著 D3 主人在串內要求寫小程式並執行、自己批准，同時語音叫機魂，記錄角色延遲。只查工作區檔案 metadata、不讀內容；數字與使用者主動給的感想才能寫回報。

不要重跑已通過的完整測試、CI、雙管路或已確認成功的真人項目，不要啟動其他被清理關閉的程式。兩個服務現在正常執行，原有 EdgeAgent 獨立 runtime 保留。D1–D3 未通過前不要把回合寫成完成；D1 未通過前不要通知可以發布公開語音修正版。真人全部通過後整份更新本回報並推 `laptop-report`，再 pull；工作檔沒換即交付。
