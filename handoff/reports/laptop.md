# 筆電最終回報 2026-10-01

分支：`copilot-story-mode`。本次變更尚未 commit。

## E4B Core 最終位置

- 唯一實體根目錄：`C:\Users\A8fm0\E4BCore`。
- 內含自己的 `.venv`、`e4b_core/`、`models/`、`config.json`、`pyproject.toml`、`tests/`、README 與 launcher。
- 全域 `e4b.cmd` 直接指向外部 `.venv` 與外部 CLI。
- 登入自啟維持關閉；停用的舊啟動檔仍保存在外部 `disabled-autostart/`。

## SilentTalk 切割結果

- `e4b_core` Junction 已拆除。
- `.runtime/models/llm` Junction 已拆除；`.runtime/models` 只剩 ASR、SenseVoice、VAD。
- repo 內兩個角色 LoRA 只在確認外部副本 SHA-256 完全相同後才刪除；外部副本保留。
- repo 內第二個 E4B launcher 與 `scripts/install_e4b_command.py` 已刪除。
- SilentTalk source 不再 import `e4b_core`，也不再擁有 `build_server_args` 或自行啟動 llama-server 的 fallback。
- `silenttalk/edge_ai.py` 是自足的 loopback HTTP client；需要時透過全域 `e4b start` 啟動外部服務，再用 `/character`、`/base` 租用與釋放。
- `setup_copilot.py` 只部署語音模型；SilentTalk launcher 不再安裝 llama.cpp、下載 LLM、安裝 E4B 指令或提供第二個 E4B 入口。
- runtime 與 dev scripts 已無 `.runtime/models/llm`；dev 評測使用 `E4B_MODEL_DIR`，預設 `%USERPROFILE%/E4BCore/models`。

## 實機驗證

- 無 repo Junction 時，SilentTalk client 成功啟動外部 E4B base。
- 真實租用切換成功：base → character（18088）→ base（18089）。
- `啟動 SilentTalk.cmd --check`：exit code 0。
- SilentTalk：compileall 通過；pytest `204 passed, 1 skipped, 1 warning`，exit code 0。
- 外部 E4B Core：Ruff 通過；pytest `18 passed`，exit code 0。
- 最終執行 `e4b stop`；18087、18088、18089 均無 LISTENING。

## 已刪除項目的恢復性

- repo 追蹤檔可由 Git 歷史恢復，但不應恢復，否則會重新形成第二條核心／模型管線。
- 外部核心與模型未刪除，仍在 `C:\Users\A8fm0\E4BCore`。

## 仍未解決、不得誤報完成

- llama.cpp Windows `/tools` 不能可靠處理中文 workspace 路徑：`x-tool-cwd` 會亂碼，Unicode 絕對路徑會回 code-page HTTP 500。
- E4B 的 `get_info` 與 shell cwd 已由本機橋接處理；`read_file`、`file_glob_search`、`grep_search`、`write_file`、`edit_file` 的完整 Unicode 本機實作仍待後續 agent 完成。
- 這個問題現在只存在外部 E4B Core；SilentTalk 已不再承載或遮蔽核心實作。

---

# 筆電交接驗收 2026-10-01 15:45:10 +08:00
commit：24b73e5（copilot-story-mode）；驗收包含既有未提交修改。

## 更新
- git fetch origin、git pull --ff-only：成功，已是最新版本。
- requirements 安裝：exit code 0。
- setup_copilot：exit code 0；ASR encoder INT8、ASR decoder INT8、ASR tokens、SenseVoice INT8、SenseVoice tokens、Silero VAD 均為 OK。
- 交接要求的 Gemma E4B 與 Character LoRA v3 兩行 OK 未出現；現有 setup 只部署語音模型，回覆模型由外部 E4B Core 管理。未修改程式。

## 一鍵驗收
- app.py --copilot-smoke：exit code 0；STT PASS / LLM PASS。
- Gate C1：5 個合成語音測試，每個 CER 0%；平均 CER 0.0%，門檻 15%，PASS。
- Gate C2：E4B 模型載入 27.8 秒；3 次生成分別 2.0、1.5、1.7 秒，各為 4/4 選項；中位數 1.69 秒，門檻 4 秒；格式 OK。
- 測試結束釋放模型 4.6 秒。
- 輸出中的測試句與生成文字依隱私規則不寫入回報；僅記驗收數字與事件。

## 角色模式語音測試
- 尚未執行；使用者選擇稍後再做。App 未為真人測試啟動。
- 角色模式分鐘數、選項模式分鐘數、頻道人數：未量測。
- 開口時機、角色感受、選項使用感受：尚未詢問，待真人測試後回饋。

## log 數字
以下是既有 log 的累計摘要，不代表本輪真人聊天測試。

| 項目 | 數字 |
|---|---|
| GPU（llama.cpp 看到的） | Vulkan0: Intel(R) Iris(R) Xe Graphics (3941 MiB, 3547 MiB free) | Vulkan1: NVIDIA GeForce RTX 3050 Ti Laptop GPU (3962 MiB, 3367 MiB free) |
| 連上 Discord（ready／resumed） | 9／0 |
| 語音接收 | 沒有啟動 |
| 收音（每 30 秒記一次） | — |
| STT 斷出的句子 | 15 |
| STT 片段音量／頻譜平坦度（人聲 < 0.3，雜訊約 0.56） | 中位數 -24.9 dBFS／0.04；像雜訊（> 0.4）0/15 段 |
| 真人辨識測試（--stt-check） | 沒有跑 |
| STT 聲音片段長度（SenseVoice） | 中位數 1958 ms、p90 1990 ms（n=15） |
| STT 辨識一段花的時間 | 中位數 168 ms、p90 229 ms（n=15） |
| STT 聽到聲音但沒辨識出字（SenseVoice） | 0 |
| 打字訊息 | 0 |
| 角色判斷次數 | 0（開口 0、沒開口 0） |
| 聽到 → 角色的話備好（開口時） | — |
| 聽到 → 決定不開口 | — |
| 模型本身（開口時） | — |
| 因為還在說話而丟掉的句子 | 0 |
| 說出口的句子 | 0（串流 0） |
| TTS 到第一段聲音（串流） | — |

警告／錯誤（只列事件名稱和次數）：
- ERROR general_edge_ai_restore_failed（e4b_core.runtime.E4BCoreError） × 1

## 其他
- 保留所有既有未提交修改與刪除，未改使用者設定檔。
- e4b stop：exit code 0；模型與 GPU 記憶體已釋放。
- 角色聊天品質與使用者感受尚未驗證，本輪不能宣稱整份交接完成。

## 2026-10-02 提交與遠端保存

- standalone_core_pushed：私人 repository https://github.com/nobody945946/E4BCore；分支 copilot-story-mode；3 commits；HEAD b10b007。
- silenttalk_migration_pushed：copilot-story-mode；4 commits；HEAD 192620b。分組為服務租用、安裝啟動、開發工具、內嵌核心與重複模型移除。
- silenttalk_pytest：204 passed、1 skipped、1 warning；exit code 0。
- e4b_pytest：36 passed；exit code 0。包含租用保護、接管重用、重啟交接、停止釋放及保留埠保護。
- e4b_ruff：PASS；exit code 0。
- remote_sync_verified：兩個開發分支 ahead 0、behind 0；工作目錄 clean。
- model_preservation_verified：外部兩個角色 LoRA 的 Git blob hash 與 SilentTalk 原有版本相同；外部模型、設定、環境及測試暫存未提交。
- live_voice_test_pending：真人聊天測試尚未執行。
