# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-10 晚上｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`，commit 先留本機，有真實進展才推；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-10-before-evening.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作一條路（§2），比完刪掉輸的（程式、設定、測試、佇列、文件一起）；同時只有一支佇列。**有原生的就用原生的**，不另立名目。
- **蒸餾：** 老師只用 Qwen3.8-27B（Q4 出卡 `teacher-38`，IQ3 錄對話 `teacher-38-iq3`）；評審 Gemma 4 31B（`judge-gemma`）。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版；但下一版的修改立刻在 worktree 做，不等這一輪考完。
- **品質是開發機的事：** 使用者不當測試員；沒過關要診斷、修好、出下一版。被資料關卡擋掉的失敗還是產品的問題。
- **使用者不在時不等回答：** 自己判斷、修好、測過，結果寫進這份。
- **從自己的錯學：** 學生先做，沒過的由老師在同一個情境示範做對，加上「學生錯的、老師對的」成對訓練。使用者願意等。
- **要贏過原版：** 每個模型用自己較好的溫度比；Python 題也要看；工具題、MCP 題各自不能輸（`ship_gate.py` 第 4 條）。
- **長期記憶用原生 `AGENTS.md`：** 全域在 EdgeAgent 的 `.runtime/pi-state/AGENTS.md`（Pi 的 agentDir），加專案資料夾裡的；主人說「記住…」就用 `edit` 寫進全域那份。它和 `personas.json` 一樣屬於使用者，回報不寫內容。
- **輸出不設上限，只要不失控：** 失控（重複迴圈）由產品偵測停下。
- **不降規：** Agent 64K 是底線；角色在 Agent 工作時照常即時回話。Agent 品質優先、可以慢；角色速度優先。
- **Discord／權限：** 語音每句喊「機魂」；用說的不能動電腦；刪檔要主人同意；不能做的事兩層都擋。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點：** 不准有常駐迴圈、心跳、輪詢、log 垃圾（§4 第 10 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`（63 題×2，`ship_gate.py`）、情境卡驗收、Python 題。資料：老師在框架裡錄 → `dataset.py` → SilentTalk `train_lora.py` |
| **取樣** | 橋接器是 owner。Agent adapter 檔案裡的 `edgeagent.sampling.off.temp`／`.thinking.temp`（`edge_agent/models.py` 讀；SilentTalk `scripts/dev/stamp_adapter_sampling.py` 量完才蓋）；沒蓋的用 0.2（基底兩種模式都 0.2 最好）。`spec-v3` c6bc244 |
| **輸出長度** | Agent 不送上限；`loop_guard.mjs` 邊收邊看，最後一段是同一個 ≤400 字的單位連續重複 ≥2000 字且 ≥20 次就停（「輸出一直重複同一段，已停止」）。`max_output_tokens` 只給整理上下文留空間。`spec-v3` 21e3ccd |
| **網頁工具** | `edge_agent/web_tools.mjs`。量測 `bench/web_live.mjs`：開發機 27/30、6/6 搜尋 |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色開口時 Agent 讓路；共用一個 adapter 才成立（§6） |
| **adapter** | 同一份資料訓兩個：只有 Agent（`agent-fw*`）、Agent＋角色（`machine-spirit-fw*`，產品要的形狀） |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己）→ `dataset.py` |
| **角色台詞** | `line_ab.py` → `bench/pair_judge.py`（Gemma，對調判兩次，先過自我檢查）→ `line_ab.py score`；`chat_task_eval.py` |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4（蒸餾補不滿的天花板） |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；被擋的步驟移到最後 |

## 3. 接下來

1. **這一輪（v2，不出貨）的結果，各自最佳溫度：**

   | | 基底 | fw3 | ms3 |
   |---|---|---|---|
   | off（126 次） | 64、60（0.2） | 79（1.0） | 73（0.2） |
   | high（126 次） | 89、86（0.2） | 82（0.2） | 77（1.0） |
   | MCP high | 24 | 20 | 19 |
   | 情境卡（91 張） | 35 | — | 21 |
   | Python（57 題） | 21 | — | 30 |
   | 角色 chat_task（40） | char-v1 39 | — | 36 |

   - ms3 情境卡輸在對話中途壞掉：12 段生成到上限被截、7 段重複上限、22 段重複搜尋。同設定重考差 3–4 分。
   - **原因（都在資料）：** 錄製預算 1024 切掉 9–25% 的老師思考（最長的），學生每步只想基底的一半（310 對 610–750 字）、步數近三倍；MCP 只有 8 列；Agent 資料沒有純聊天；假股票伺服器不認真實 schema 的 `name`（一半的 MCP 輸是考場冤枉）。
2. **佇列（今晚）：** 訓練 `machine-spirit-fw3n`（同樣 595 段對話完全不帶思考，`dataset.py --thinking none`）→ 它 off／high × 0.2／1.0 四場 → `v3-think-pilot`（30 張訓練卡、每組 3 張，用 v3 和新預算 12288 錄，量還有多少思考被切）→ `ms3-lines`（延後）。
   - **看 fw3n：** high 有沒有回到基底水準，截斷和重複有沒有變少。回到了，就是「學了被切短的思考」害的；v3 再比「完整長思考」對「不帶思考」。
   - **看試錄：** 切斷率 <2% 才整份錄，否則再放寬；也看思考長度和錄製時間。
   - **`ms3-lines` 為什麼延後：** `pair_judge` 第一次跑自我檢查只過 26/40（要 36）。它把「另一段對話的台詞」當壞的，但機魂的台詞短又泛用，別段的可能也接得上，裁判判平手就算錯。現在會記下每種壞法的分數和沒判對的題目（`c8f0ca6`），重跑時看是裁判還是題目的問題；是題目的話，改用主題不同的對話的台詞當壞的。
3. **v3（`spec-v3`，worktree `ea-v3`；測試只剩 4 個 Windows 專用的失敗；沙盒逃脫檢查通過）：**
   - **記憶：** 提示詞說主人的全域 `AGENTS.md` 是唯一跨對話記憶；橋接器開出這個檔；`run.py` 每個工作給一份可寫的、讀回給評分；考試 `memory-*` 4 題、`chat-memory` 改版；訓練 `tool_tasks_memory.py`（memory、chat）。
   - **MCP：** 7 個日常假伺服器＋照真實 schema 的股票伺服器（`strict.mjs` 錯誤點名參數），訓練 42 題，考試 27 題（`bench/mcp_exam.py`），行事曆不進訓練。
   - **假網路：** 每個名字都解析到沙盒自己，443 用 bench 的 CA 簽每個名字的憑證，網址照卡片原樣，沒有的回 404。
   - **查本機：** Linux 自己的指令算失敗；`$PSVersionTable`、`[Environment]` 改成工具輸出出現沙盒系統才算。
   - **老師思考預算 12288**（ae6b982）、取樣跟著 adapter、輸出不設上限（§2）。
   - **還要做（要 GPU）：** 看試錄；C 組 `recheck` 再 `generate`；新切題前刪掉 `.runtime/agentdata/tool-tasks` 裡舊的 `mcp-00..13`；整份重錄（情境、工具、Python、記憶、聊天、MCP）；訓練；每個 adapter 考 off／high 各兩種溫度，蓋上較好的；第一輪「從自己的錯學」（學生是合一版，在它的最佳溫度、只用訓練卡和訓練題）。
4. **出貨（有 adapter 過全部關卡時）：** 合併 `spec-v3`（含 `next-world`）進 `copilot-story-mode`，跑完整測試，推 EdgeAgent，等 CI 綠；整份重寫 `laptop.md`：部署 PowerShell 7.6.6、介面（`reversible`、還原、API 登錄頁、記憶的檢視和編輯）、Discord 實測、網頁實測（`web_live.mjs`）、唯讀查本機和唯讀算資料的檢查、Windows 上要過 `test_real_sdk_stops_fetching_the_same_dead_address` 和 `tests/test_lingua_powershell.py`。
5. **筆電：** 第 10 回合已審；下一回合等有 adapter 過關。
6. **之後：** coding agent（Qwen3.8 軌跡）；清掉不用的 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web`、`ea-t1`、`ea-v3` 合併或用完後）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。取樣、上限這類設定每個模型、每個模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或工作的掛載先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練。資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們。吃滿整台機器、大下載先問使用者。考試中不要另外對考場的模型伺服器發請求。
6. 關程序只用確認過的 PID，不用字串比對。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`bench/web_fixture.py`、`bench/grade.py` 是即時掛載。改產品程式在 worktree 做。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列本身（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，醒來先重新掛上再處理；佇列停了它會說 NOTHING PENDING，修好重啟佇列後再掛。push 完 `wake.sh ci <repo> <sha>`；交辦筆電後 `wake.sh handoff <小時>`。不盲目重試、不預寫備案。push 完要等 CI 綠才算完成。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過：test_processes 1、test_sdk_permissions 1、test_terminal 2
# worktree：加 PYTHONPATH=.，用 EdgeAgent 的 .venv；先把 .runtime/node、pi、pwsh 連到主工作區。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root；沒有瀏覽器。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`；v3 的 `Get-Process`、`Get-PSDrive`、`Get-ComputerInfo` 是 `bench/pshome` 的真 cmdlet）。
- **情境題、Python 題：** 都開思考考。情境題由評審決定（`<run>/verdicts.jsonl`）。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池加 `--no-cache-idle-slots`；考場固定 `--fit off`。請求沒給溫度時讀模型檔（Gemma 4：1.0／64／0.95，min-p 0.05）。當過一次（-11，一個槽生成到 8192 後清檢查點時），佇列接手續跑；再發生就查版本（筆電同版）。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色開口要等：兩個不同 adapter 逾時（30 秒），共用一個 0.62 秒；可用 RAM 只剩 200–290 MiB。
- **老師：** SWE-bench 36/60。思考預算 4096 仍切掉 7% 的 Python 思考。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB。

## 7. 踩過的雷

- **沒量過的預設值：** Agent 溫度 0.2 從改寫起就在，對基底剛好，對 adapter 不一定，兩個 adapter 方向還相反。
- **錄製省下的預算會被學走：** 預算切掉的正好是最深入的思考。
- **考場不忠實會冤枉模型：** 假伺服器不認真實參數、評分把起飛前解鎖當多餘，都算到模型頭上。
- **重試沒用：** 必然重現的失敗重試沒用；佇列失敗就停下，由 session 診斷。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **Node 的錯誤：** 只說「fetch failed」，原因在 `cause`。
- **被殺的 `run.py`：** 它的 relay 會變孤兒留著，停佇列後要清。
- **這台的 `gh`：** 太舊，用 API 的 `head_sha` 查 CI。
- **試跑要走對方的實際路徑。** `cd a && x &` 整串會在背景子殼跑。
