# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-10 夜｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`，commit 先留本機，有真實進展才推；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`（worktree `/home/clawd/worktrees/ea-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-10-before-t06.md`（只在這台機器，不必讀）。

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
| **角色台詞** | `line_ab.py` → `bench/pair_judge.py`（Gemma，對調判兩次，先過自我檢查）→ `line_ab.py score`；`chat_task_eval.py` |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；被擋的步驟移到最後。v3 的步驟在 `ea-v3` 裡跑，資料在它自己的 `.runtime/agentdata` |

## 3. 接下來

1. **v2 這一輪（不出貨）的結果，各自最佳溫度：**

   | | 基底 | fw3 | ms3 |
   |---|---|---|---|
   | off（126 次） | 64、60（0.2） | 79（1.0） | 73（0.2）；不帶思考的 ms3n 77（0.2） |
   | high（126 次） | 89、86（0.2） | 82（0.2） | 77（1.0） |
   | MCP high | 24 | 20 | 19 |
   | 情境卡（91 張） | 35 | — | 21 |
   | Python（57 題） | 21 | — | 30 |
   | 角色 chat_task（40） | char-v1 39 | — | 36 |

   - **低溫鬼打牆：** off、0.2 時 adapter 有 26–33 場因為一字不差重跑失敗的指令被重複關卡停下（多在 code、chore、tool；連產品「已經跑兩次了」的提醒都不理），基底 0 場。DeepSeek 對蒸餾學生建議 0.6；我們只量過 0.2 和 1.0。
   - ms3 情境卡輸在對話中途壞掉：12 段生成到上限被截、7 段重複上限、22 段重複搜尋。同設定重考差 3–4 分。
   - **原因（都在資料）：** 錄製預算 1024 切掉老師的思考（`thought_stats.py` 重算：情境 25%、工具 9%、Python 15%，切掉的是最長的）。**就算不切，老師也想得比基底短：** 老師已是最高思考等級（xhigh），工具每步中位數 288 字、Python 245 字，基底 650 字（只有情境 1252 字比較長）。學生每步只有 181–225 字、步數近三倍。另外 MCP 只有 8 列；Agent 資料沒有純聊天；假股票伺服器不認真實 schema 的 `name`。
2. **佇列正在跑的（`queue.sh` 已換成含 v3 的新檔，正在跑的 shell 還讀舊內容）：** `machine-spirit-fw3n`（不帶思考）已訓完，off／high × 0.2／1.0 四場考到一半 → `v3-think-pilot`（30 張訓練卡，v3＋預算 12288）→ `ms3-lines`。
   - **舊佇列停下（`queue finished` 或失敗）時：** 背景跑 `setsid nohup bash .runtime/fw/relaunch.sh >> .runtime/fw/queue.log 2>&1 &`（在 EdgeAgent 裡），新檔跳過做完的步驟，先跑 `ms3n-t06`、`ms3n-t06-high`（`worktrees/ea-t06`：凍結的 v2 產品，只把橋接器溫度改 0.6，量完就刪），再接著跑 v3。`ms3-lines` 失敗就照下面診斷；當下修不好，把它移到佇列最後再重啟。
   - **看 fw3n（對照組）：** high 有沒有回到基底水準，截斷和重複有沒有變少。v3 照使用者選的做法保留老師完整的思考，fw3n 只用來分辨「學了被切短的思考」和其他原因（步數、截斷）。v3 訓練時同一份資料再訓一個不帶思考的當對照，關卡選贏的。
   - **看 `ms3-lines`：** `pair_judge` 上次自我檢查只過 26/40（要 36）。結果檔 `SilentTalk/.runtime/dev/line-ab/ms3.judge-validation.json` 的 `by_kind`、`missed` 會說是哪種壞法沒判對（評審每次只輸出 29–38 個 token，不是被截）。若是「另一段對話的台詞」錯：評估集同一情境有好幾段對話，改用主題不同的對話的台詞。若兩種壞法都錯、多半判平手：是位置偏誤，改成用兩種順序下 A／B 的機率平均來判。
3. **v3 的佇列步驟（在 `ea-v3`，依序）：**
   1. `v3-pilot-check`：`thought_stats.py --base`（基底 `base-v2f-high`）看試錄，印出每類思考是基底的幾倍；任何一類切掉 >2% 就停下。停下時把 `ea-v3/bench/configs.json` 兩個老師的 `--reasoning-budget` 加大並 commit，刪掉 `ea-v3/.runtime/bench/v3-think-pilot`，重跑試錄。
   2. `v3-py-pilot`：20 題 Python 用同預算錄，同樣檢查。
   3. `v3-cards`：C 組照新規則淘汰（訓練 22、考試 2 張，含試錄的 C-001、C-003），補回 55／10 張，寫檔案、重建題目。
   4. `v3-describe`：322 題工具題（23 類×14，CPU 已切好；自我檢查沒有一題不做事就過）由老師寫請求。
   5. `v3-base`、`v3-base-high`：基底先考 v3（含記憶、MCP、https 假網路）。**要看：** 新題有沒有考場本身的錯（兩次都 0 分或都滿分的題各看一次）。
   6. `v3-tools`、`v3-py`（各錄兩次，每題兩條獨立過關的軌跡）、`v3-scen`（一次；之後要更多資料就用 `--repeats 2` 續跑，只補第二次）：整份錄製。試錄的對話直接併入，淘汰卡的紀錄續跑時自動丟掉。情境題 v2 花 15 小時，這次會更久。
   7. `v3-judged`、`v3-thoughts`（只報數字）、基底的 v3 情境卡和 Python 題。
4. **v3 之後（錄製期間寫進佇列）：** `dataset.py`（帶完整思考，和不帶思考的對照）→ 先數每列的 token 數，長思考的列超過 `--max-length 32768` 的多就加大（看 VRAM）→ 訓練合一版 → 每個 adapter 考 off／high 各三種溫度（0.2、0.6、1.0；基底也要補 0.6，才是最佳對最佳），蓋上最好的（`stamp_adapter_sampling.py`）→ 情境卡、Python、台詞、`chat_task`（合一版的角色回話不能出現思考、不能變慢：和 char-v1 比第一句出來的時間）→ 關卡 → 第一輪「從自己的錯學」（學生是合一版，在它的最佳溫度、只用訓練卡和訓練題；重複關卡提醒之後的那一步要有老師的示範，老師資料裡從沒出現過這個提醒）。
5. **出貨（有 adapter 過全部關卡時）：** 合併 `spec-v3`（含 `next-world`）進 `copilot-story-mode`，跑完整測試，推 EdgeAgent，等 CI 綠；整份重寫 `laptop.md`：部署 PowerShell 7.6.6、介面（`reversible`、還原、API 登錄頁、記憶的檢視和編輯）、Discord 實測、網頁實測（`web_live.mjs`）、唯讀查本機和唯讀算資料的檢查、Windows 上要過 `test_real_sdk_stops_fetching_the_same_dead_address` 和 `tests/test_lingua_powershell.py`。
6. **筆電：** 第 10 回合已審；下一回合等有 adapter 過關。
7. **之後：** coding agent（Qwen3.8 軌跡）；清掉不用的 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web`、`ea-t1`、`ea-v3` 合併或用完後）；v3 的 `configs.json` 還留著 v2 實驗的 `think512/1024/2048`，合併前刪。

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
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，醒來先重新掛上再處理；佇列停了它會說 NOTHING PENDING，修好重啟佇列後再掛。push 完 `wake.sh ci <repo> <sha>`；交辦筆電後 `wake.sh handoff <小時>`。不盲目重試、不預寫備案。push 完要等 CI 綠才算完成。

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
