# Windows 工作檔：SilentTalk 與 EdgeAgent

更新：2026-10-02｜開發分支：`copilot-story-mode`｜報告分支：`laptop-report`

這份工作檔取代原本 E4B＋私人 LoRA 的角色測試指示。產品現已分成獨立編程 Agent 與語音角色玩具；舊版本保留在 Git 歷史。共通規則仍以根目錄 `AGENTS.md` 為準；使用者本次要求優先於舊工作範圍。

## 目前產品與位置

| 項目 | 位置與責任 |
|---|---|
| SilentTalk | `C:\Users\A8fm0\Downloads\SilentTalk`；Discord 語音角色、回覆選項與 TTS |
| EdgeAgent | `C:\Users\A8fm0\EdgeAgent`；獨立編程 Agent、模型管理、推論與租借 |
| SilentTalk 啟動 | `啟動 SilentTalk.cmd`；同一入口首次部署與缺損修復 |
| EdgeAgent 啟動 | `開啟 EdgeAgent.cmd` 或部署後的 `edge-agent` |
| 報告 | `handoff/reports/laptop.md`；只提交到 `laptop-report` |

推論由 EdgeAgent 的 llama.cpp router 管理，最多載入一個完整模型。編程流程使用 Pi SDK；SilentTalk 經 localhost 控制 API `18087` 租借角色模型，使用回傳推論端點 `18089`，歸還後恢復原 Agent 配置。SilentTalk 不自行啟動 llama-server，也不共用 EdgeAgent 的 Python 環境。

預設 Agent 模型為 `Qwen3.5-4B-Q4_K_M.gguf`、context 16,384、thinking off；角色預設為公開 Gemma 4 E4B、context 32,768。模型與 adapter 在 EdgeAgent 的 `models` 目錄，STT 在 SilentTalk 的 `.runtime/models`。LoRA 預設空白，只支援使用者自行安裝的相容 GGUF adapter；不附帶、下載、自動選擇或配對個人 LoRA。

## 已交付與驗證

- EdgeAgent 原始碼發行為 `bootstrap-v7`；Windows 玩家包為 `windows-2026.10.02`。manifest 由 `scripts/edge-agent-distribution.json` 管理。
- 玩家 ZIP 含已驗證的 EdgeAgent 來源；取得 ZIP 後，部署不再要求 GitHub 登入。repository／發行頁仍是私人的，下載時需要存取權限。
- 首次啟動部署各自的 venv、Python／Git、Node／Pi、推論引擎、公開基底、FFmpeg 與 STT。重開沿用完成紀錄，元件改變或缺損走同一安裝流程。
- EdgeAgent pytest 74 passed、Ruff 通過；SilentTalk 完整 pytest 224 passed、1 skipped。SilentTalk 原有背景 fixture 例外與八項 Ruff 基線問題另有報告，不當成新功能已修復。
- 兩個小型 Python 修碼案例通過獨立驗證；大型專案能力尚未建立。較小的 2B 模型曾因無進展停止，不算完成工作。
- 真實 Edge 驗證通過模型切換、LoRA 載入與移除、基底變更清除 adapter、原 Agent 恢復，以及八種視窗尺寸。未預期瀏覽器錯誤為零；不存在資料夾的 HTTP 400 是已確認的負向案例。
- 新目錄部署成功，沿用既有 Python／Git 與公開下載快取；不是乾淨 OS 安裝實測。自行建立的兩個部署測試目錄已刪除。
- 驗證結束時服務與專用測試 Edge 已關閉，不應自動啟動程式或連 Discord；沒有待使用者配合的角色聊天測試。

## 按任務讀取與執行

只做使用者指定的工作。收到「繼續／開工」而沒有未完項時，先確認 Git 分支、工作樹及最新報告；不要自動重跑舊的真人聊天或念句子測試。

| 任務 | 需要時才讀 |
|---|---|
| 使用說明、安裝問題 | SilentTalk `README.md` |
| SilentTalk 架構或程式修改 | `ARCHITECTURE.md` 與該功能對應檔案 |
| 安裝／修復／發行 | `scripts/bootstrap.ps1`、`scripts/package_windows.py`、`scripts/edge-agent-distribution.json` |
| 租借問題 | `silenttalk/agent_lease.py`；必要時 EdgeAgent `edge_agent/service.py` |
| 模型／LoRA／Agent | EdgeAgent `README.md`、`VALIDATION.md`，再讀相關實作 |
| 狀態與驗證證據 | `handoff/reports/laptop.md`；只讀事件與數字 |

部署驗收用 `啟動 SilentTalk.cmd --check`，不連 Discord，會實際載入 STT、租借角色並恢復 Agent。只部署用 `--setup-only`。已有人租借時先結束該會話，不搶占它。EdgeAgent `開啟 EdgeAgent.cmd --check` 是元件部署／檢查，不等同完整角色租借實測。

程式修改後執行對應測試並看原始 exit code；必要時跑完整 `.venv\Scripts\python.exe -m pytest -q`。文件修改核對實作、檔案路徑與指令，執行 `git diff --check`。通過且未改的部分不例行重跑。

## 資料與提交規則

- 不讀寫使用者 `.env`、`settings.json`、`personas.json`、`character_state.json`，也不讀 `silenttalk.log` 對話原文。對話、prompt、轉錄與錄音不寫入報告或測試資產。
- 個人 LoRA 只由使用者安裝；不把個人檔案或設定放入 Git／來源包／Windows ZIP。
- 程式與說明提交到 `copilot-story-mode`，不能在 `main` commit。報告只寫數字與事件，提交到 `laptop-report`；用獨立 worktree 可避免切換正在工作的分支。
- push 使用正常 push，不覆寫遠端報告歷史。使用者已授權此任務的 commit／push，不因舊流程再次詢問。
- 關程式按自己的 PID；不批次關閉使用者 Edge。結束測試後歸還租借、恢復原模型、停止自行啟動的服務並驗證清理。