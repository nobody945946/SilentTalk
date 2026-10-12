# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-12 晚上｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`，commit 先留本機，有真實進展才推；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`（worktree `/home/clawd/worktrees/ea-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-12-before-restart.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作一條路（§2），比完刪掉輸的（程式、設定、測試、佇列、文件一起）；同時只有一支佇列。**有原生的就用原生的**，不另立名目。
- **蒸餾：** 老師只用 Qwen3.8-27B（出卡、寫題目、錄對話都用 IQ3 的 `teacher-38-iq3`）；評審 Gemma 4 31B（`judge-gemma`）。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **長思考內化（DeepSeek 的做法）：** 學生學老師完整的長思考，只用過關的軌跡；錄得久、筆電上想得久都接受（2026-10-10）。老師起碼要想得跟基底 E4B 一樣長，預算切掉的比例要 ≤2%。**長思考只給 Agent 的工作；聊天是另一回事：** 純聊天在任何模式都直接回答（`dataset.py` 的聊天題不帶思考，開關兩種都訓）；角色的回話一律不開思考（SilentTalk `reply_transport.py` 送 `enable_thinking: false`）。
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
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`（v3：81 題×2，`ship_gate.py`）、情境卡驗收、Python 題。資料：老師在框架裡錄（`--record`）→ `thought_stats.py`（切斷 ≤2%）→ `dataset.py` → SilentTalk `train_lora.py` |
| **取樣** | 橋接器是 owner。Agent adapter 檔案裡的 `edgeagent.sampling.off.temp`／`.thinking.temp`（`edge_agent/models.py` 讀；SilentTalk `scripts/dev/stamp_adapter_sampling.py` 量完才蓋）；沒蓋的用 0.2（基底兩種模式都 0.2 最好） |
| **輸出長度** | Agent 不送上限；`loop_guard.mjs` 邊收邊看，同一個 ≤400 字的單位連續重複 ≥2000 字且 ≥20 次就停。`max_output_tokens` 只給整理上下文留空間 |
| **網頁工具** | `edge_agent/web_tools.mjs`。量測 `bench/web_live.mjs`：開發機 27/30、6/6 搜尋 |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色開口時 Agent 讓路；共用一個 adapter 才成立（§6） |
| **adapter** | 產品要合一版（Agent＋角色，`machine-spirit-fw*`）；只有 Agent 的（`agent-fw*`）只在要分辨角色資料有沒有拖累時才訓 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck`、`generate`、`files`、`tasks`）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己）→ `dataset.py` |
| **工具題** | `make_tool_tasks.py cut`（CPU）→ `describe --config teacher-38-iq3`（老師寫請求，自己開伺服器） |
| **角色台詞** | `line_ab.py`（每組帶資料自己的台詞 `ref`）→ `bench/pair_judge.py`（Gemma 先想再答，對調判兩次都贏才算；自我檢查用 `ref` 對另一段的 `ref`、對切成 4 字，要 36/40）→ `line_ab.py score`；`chat_task_eval.py` |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；被擋的步驟移到最後。v3 的步驟在 `ea-v3` 裡跑，資料在它自己的 `.runtime/agentdata` |

## 3. 接下來

1. **結果（v2 產品，126 次）：**

   | | 基底 0.2 | ms3（帶被切的思考） | **ms3n（不帶思考）** |
   |---|---|---|---|
   | off | 64、60（MCP 21） | 73 | **78（1.0，MCP 22）**；0.2 是 77、MCP 19、鬼打牆 26 場 |
   | high | 89、86（MCP 24） | 77 | **91（0.2，MCP 25）**；1.0 是 84 |
   | 情境卡（91）／Python（57） | 35／21 | 21／30 | 排隊中 |

   - 上一輪輸在學了被切短的思考；ms3n 每步想 488 字（基底 650、ms3 181），出錯 4 場（ms3 43）。
   - **低溫鬼打牆：** adapter 在 0.2 一字不差重跑失敗的指令（基底不會），1.0 少很多；DeepSeek 對蒸餾學生建議 0.6（`ms3n-t06*` 在量）。
   - 老師（xhigh）本來就想得短：工具每步 288 字、Python 245，基底 650；只有情境 1252。
2. **2026-10-12 補上的（都已 commit，未推）：**
   - EdgeAgent 主線：每個 adapter 依模式取樣（c6bc244 搬進 `5eeb610`，沒蓋的仍是 0.2）；**模型程序當掉會自動重新載入**（`81a50bd`：實測 b11193 的 worker 當掉後 router 還在、模型 unloaded、每個請求都「model is not loaded」，沒有人重載）；評審先想再答（`d2cc7ab`）。
   - SilentTalk：**角色的語音壞了已修**（`8b0e317`：微軟 10/10 起把 Edge 朗讀換到 `api.msedgeservices.com`，舊位址一律 403，edge-tts 7.2.8 是最新版仍用舊的；新位址用舊的 token 和版本可用；忙線 429／503 在出聲前再試一次）。上游出新版時 `test_edge_styles.py` 會失敗提醒拿掉覆寫。
   - **佇列停了 42 小時沒人知道：** 10/10 22:56 醒來處理當機後沒重新掛 `wake.sh`，23:45 `ms3n-lines` 失敗就一直停著。每次醒來第一件事就是重新掛上。
3. **佇列（重啟後的順序）：** `ms3n-lines`（評審已在手動跑 ms3n 的 80 組；有 `ms3n.verdicts.json` 就跑 `line_ab.py score --out .runtime/dev/line-ab/ms3n --verdicts ...ms3n.verdicts.json | tee EdgeAgent/.runtime/fw/ms3n.lines.txt` 再 `touch EdgeAgent/.runtime/fw/ms3n-lines.done`）→ `ms3n-t06`、`-t06-high`（`worktrees/ea-t06`，量完刪）→ `scen-eval-ms3n`、`py-eval-ms3n`、`ms3n-chat-task`、`ms3n-gate`（off 用 `ms3n-t1`）→ `v3-think-pilot` → v3。
   - **ms3n 過全部關卡就出貨（不等 v3）：** `stamp_adapter_sampling.py` 蓋 off／thinking 的最佳溫度（目前 1.0／0.2；0.6 若較好就用 0.6）→ 推 EdgeAgent、SilentTalk，等 CI 綠 → 整份重寫 `laptop.md` 一回合：部署新版 EdgeAgent 和蓋過溫度的 `machine-spirit-fw3n.q8_0.gguf`、SilentTalk 新版（語音修正）、Discord 實測角色說話、Agent 實測；`release_windows.py` 發公開版（玩家的語音也壞了）→ `wake.sh handoff`。
   - **沒過：** 看 `why.txt`，修資料或考場，v3 照常。
4. **v3 的佇列步驟（在 `ea-v3`）：** `v3-pilot-check`（`thought_stats.py --base base-v2f-high`；任一類切掉 >2% 就停：加大老師的 `--reasoning-budget`、刪 `ea-v3/.runtime/bench/v3-think-pilot` 重跑）→ `v3-py-pilot` → `v3-cards`（C 組補回 55／10）→ `v3-describe`（322 題工具題的請求）→ `v3-base`、`-high`（先看新題有沒有考場錯）→ `v3-tools`、`v3-py`（各兩次）、`v3-scen`（一次，試錄併入）→ `v3-judged` → `v3-thoughts` → 基底的 v3 情境卡、Python。
5. **v3 之後：** `dataset.py` 帶完整思考（使用者選的 DeepSeek 做法；聊天題不帶思考）和不帶思考兩份，各訓一個合一版 → 數 token，超過 `--max-length 32768` 的多就加大 → off／high × 0.2、0.6、1.0（基底也補 0.6）→ 蓋最佳溫度 → 情境卡、Python、台詞、`chat_task`（角色回話不能有思考、不能比 char-v1 慢）→ 關卡選贏的 → 「從自己的錯學」（含重複關卡提醒之後的那一步）。出貨時合併 `spec-v3`（含 `next-world`），`laptop.md` 加記憶的檢視和編輯、PowerShell 7.6.6、唯讀查本機、`test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`。
6. **之後：** coding agent（Qwen3.8 軌跡）；清 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web`、`ea-t1`、`ea-t06`、`ea-v3` 用完後）；v3 `configs.json` 的 `think512/1024/2048` 合併前刪。使用者問過 AirLLM：每個字都從硬碟讀整個模型，筆電上一步要幾分鐘，不做；要大模型得先加 RAM，再用 llama.cpp 把 MoE 專家放 RAM 實測。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。取樣、上限這類設定每個模型、每個模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或工作的掛載先跑 `--containment`。
3. 考試題先過 `--selftest`（訓練工具題沒有參考解，只看「不做事不能過」）；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練。資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們。吃滿整台機器、大下載先問使用者。考試中不要另外對考場的模型伺服器發請求。
6. 關程序只用確認過的 PID，不用字串比對。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`bench/web_fixture.py`、`bench/grade.py` 是即時掛載（主工作區和 `ea-v3` 都是）。`ea-v3` 的 `edge_agent` 從試錄到錄完都不能改（同一份凍結規格）。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列本身（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`。**訓練中別停佇列**：`train_lora.py` 不能接續，重啟會從頭訓。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，**醒來第一件事就是重新掛上**（漏一次，佇列停了 42 小時沒人知道），再處理；佇列停了它會說 NOTHING PENDING，修好重啟佇列後再掛。push 完 `wake.sh ci <repo> <sha>`；交辦筆電後 `wake.sh handoff <小時>`。不盲目重試、不預寫備案。push 完要等 CI 綠才算完成。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過：test_processes 1、test_sdk_permissions 1、test_terminal 2
# worktree：加 PYTHONPATH=.，用 EdgeAgent 的 .venv；先把 .runtime/node、pi、pwsh 連到主工作區。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root；沒有瀏覽器。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`；v3 的 `Get-Process`、`Get-PSDrive`、`Get-ComputerInfo` 是 `bench/pshome` 的真 cmdlet）。v3 的假網路：每個名字都解析到沙盒自己，443 用 bench 的 CA 簽憑證，網址照卡片原樣。
- **情境題、Python 題：** 都開思考考。情境題由評審決定（`<run>/verdicts.jsonl`）。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池加 `--no-cache-idle-slots`；考場固定 `--fit off`。請求沒給溫度時讀模型檔（Gemma 4：1.0／64／0.95，min-p 0.05）。當過一次（-11，一個槽生成到 8192 後清檢查點時），佇列接手續跑；再發生就查版本（筆電同版）。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色開口要等：兩個不同 adapter 逾時（30 秒），共用一個 0.62 秒；可用 RAM 只剩 200–290 MiB。
- **老師：** SWE-bench 36/60。v2 錄製（預算 1024）：情境 314 張 15 小時、工具 152 題 1.7 小時、Python 210 題 2.9 小時、評審 1.6 小時；思考中位數情境 1252 字、工具 288 字、Python 245 字。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；595 段對話＋角色資料 2 輪約 3.5 小時。

## 7. 踩過的雷

- **沒量過的預設值：** Agent 溫度 0.2 從改寫起就在，對基底剛好，對 adapter 不一定，兩個 adapter 方向還相反。
- **蒸餾的學生低溫會鬼打牆：** 基底 0.2 最好，adapter 在 0.2 一字不差重跑失敗的指令；溫度要每個模型各自掃，至少 0.2、0.6、1.0。
- **錄製省下的預算會被學走：** 預算切掉的正好是最深入的思考。
- **考場不忠實會冤枉模型：** 假伺服器不認真實參數、評分把起飛前解鎖當多餘，都算到模型頭上。
- **已知的副作用要追到學生身上：** 10/08 就知道預算切掉 21% 的思考，只做了「被切的不訓練」，結果丟掉的正好是最長的；只看分數的里程碑檢查抓不到。每個里程碑都要拿資料和基底比（思考長度、切斷、步數）。
- **自我檢查的題目也要檢查：** 評審沒過自我檢查時，先看是評審錯，還是「壞的那一句」其實也說得通。
- **重試沒用：** 必然重現的失敗重試沒用；佇列失敗就停下，由 session 診斷。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **Node 的錯誤：** 只說「fetch failed」，原因在 `cause`。
- **被殺的 `run.py`：** 它的 relay 會變孤兒留著，停佇列後要清。
- **這台的 `gh`：** 太舊，用 API 的 `head_sha` 查 CI。
- **試跑要走對方的實際路徑。** `cd a && x &` 整串會在背景子殼跑。
