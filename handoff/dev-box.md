# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-12 深夜｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`（worktree `/home/clawd/worktrees/ea-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-12-before-ship.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作一條路（§2），比完刪掉輸的（程式、設定、測試、佇列、文件一起）；同時只有一支佇列。**有原生的就用原生的**，不另立名目。
- **蒸餾：** 老師只用 Qwen3.8-27B（出卡、寫題目、錄對話都用 IQ3 的 `teacher-38-iq3`）；評審 Gemma 4 31B（`judge-gemma`）。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **長思考內化（DeepSeek 的做法）：** 學生學老師完整的長思考，只用過關的軌跡；錄得久、筆電上想得久都接受（2026-10-10）。老師起碼要想得跟基底 E4B 一樣長，預算切掉的比例要 ≤2%。**長思考只給 Agent 的工作；聊天是另一回事：** 純聊天在任何模式都直接回答（`dataset.py` 的聊天題不帶思考，開關兩種都訓）；角色的回話一律不開思考（SilentTalk `reply_transport.py` 送 `enable_thinking: false`）。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版；但下一版的修改立刻在 worktree 做，不等這一輪考完。產品的錯誤修正（當機重載、取樣、迴圈停止）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；沒過關要診斷、修好、出下一版。被資料關卡擋掉的失敗還是產品的問題。
- **使用者不在時不等回答：** 自己判斷、修好、測過，結果寫進這份。
- **從自己的錯學：** 學生先做，沒過的由老師在同一個情境示範做對，加上「學生錯的、老師對的」成對訓練。使用者願意等。
- **要贏過原版：** 每個模型用自己較好的溫度比；Python 題也要看；工具題、MCP 題各自不能輸（`ship_gate.py` 第 4 條）。
- **長期記憶用原生 `AGENTS.md`：** 全域在 EdgeAgent 的 `.runtime/pi-state/AGENTS.md`（Pi 的 agentDir），加專案資料夾裡的；主人說「記住…」就用 `edit` 寫進全域那份。它和 `personas.json` 一樣屬於使用者，回報不寫內容。
- **輸出不設上限，只要不失控：** 失控（重複迴圈）由產品偵測停下。
- **不降規：** Agent 64K 是底線；角色在 Agent 工作時照常即時回話（所以 Agent 和角色共用一個 adapter）。Agent 品質優先、可以慢；角色速度優先。
- **Discord／權限：** 語音每句喊「機魂」；用說的不能動電腦；刪檔要主人同意；不能做的事兩層都擋。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點：** 不准有常駐迴圈、心跳、輪詢、log 垃圾（§4 第 10 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡驗收、Python 題、`ship_gate.py`。資料：老師在框架裡錄（`--record`）→ `thought_stats.py`（切斷 ≤2%）→ `dataset.py` → SilentTalk `train_lora.py` |
| **adapter** | 一個給 Agent 和機魂共用（`runtime.AGENT_ADAPTER`＝`CHARACTER_ADAPTER`，SilentTalk `BUNDLED_ADAPTERS` 同名），放 `edge_agent/adapters`，`deploy.ADAPTERS` 記 SHA256 |
| **取樣** | adapter 檔案裡的 `edgeagent.sampling.off.temp`／`.thinking.temp`（`edge_agent/models.py` 讀；SilentTalk `scripts/dev/stamp_adapter_sampling.py` 量完才蓋，蓋在產品那份複本上）；沒蓋的用 0.2 |
| **輸出長度** | Agent 不送上限；`loop_guard.mjs` 邊收邊看（思考、正文、工具參數都看），同一個 ≤400 字的單位連續重複 ≥2000 字且 ≥20 次就停 |
| **網頁工具** | `edge_agent/web_tools.mjs`。量測 `bench/web_live.mjs`：開發機 27/30、6/6 搜尋 |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色開口時 Agent 讓路；同一個 adapter 才能同批 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck`、`generate`、`files`、`tasks`）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己）→ `dataset.py` |
| **工具題** | `make_tool_tasks.py cut`（CPU）→ `describe --config teacher-38-iq3`（老師寫請求，自己開伺服器） |
| **角色台詞** | `line_ab.py`（每組帶資料自己的台詞 `ref`）→ `bench/pair_judge.py`（Gemma 先想再答，對調判兩次都贏才算；自我檢查要 36/40）→ `line_ab.py score`；`chat_task_eval.py`（溫度 0，結果固定） |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；被擋的步驟移到最後。v3 的步驟在 `ea-v3` 裡跑，資料在它自己的 `.runtime/agentdata` |

## 3. 接下來

1. **ms3n 過關，出貨中（2026-10-12）：** `machine-spirit-fw3n`（和 ms3 同樣的對話，不帶老師被切短的思考）對基底 E4B，各用自己最好的溫度：

   | | 基底（0.2） | **ms3n** |
   |---|---|---|
   | off（126 次） | 60、64 | **78**（1.0；0.2 是 77、鬼打牆 26 場；0.6 是 72） |
   | high（126 次） | 86、89 | **91**（0.2；0.6 是 87；1.0 是 84） |
   | 情境卡（91）／Python（57） | 35／21 | **39／36** |
   | 機魂台詞（對 char-v1）／聊天工作 | char-v1 39/40 | 31 比 33、12 平手／**37/40** |

   - `ship_gate.py` 五項全過，工具、MCP 都沒變差。
   - **退步：** 聊天工作漏了「查最新消息」三題（今天新聞、遊戲上市日、油價），char-v1 只漏一題；v3 要補（第 4 項）。
   - **失控：** ms3n 思考開時 217 場有 3 場在思考裡重複到 8192 上限（基底 0 場）。v3 的 `loop_guard` 已搬進出貨版（`327269f`），測試補上思考（`f56ca16`）。7.3 萬則歷次輸出重播：停的 200 則全是迴圈，這三場會在 2,000–5,500 字停下。
   - **出貨步驟：** 分支 `ship-ms3n`（worktree `ea-ship`、`st-ship`）→ 快轉進 `copilot-story-mode` → 推 EdgeAgent、SilentTalk，等 CI 綠 → 整份重寫 `laptop.md`（第 11 回合，草稿在 scratchpad 的 `laptop-r11.md`：部署、Windows 測試、雙管路實量、Discord 實測含機魂用語音回答）→ `wake.sh handoff 48`。
   - **筆電回報 D1 過、兩個 repo 測試全過：** `release_windows.py --edge-agent ../EdgeAgent --notes <筆電驗證摘要> --publish` 發公開版（玩家的語音也壞了），刪 `ea-ship`、`st-ship`。
2. **2026-10-12 修好的（都已在 `copilot-story-mode`）：**
   - EdgeAgent：每個 adapter 依模式取樣（`5eeb610`）；模型程序當掉會自己重新載入（`81a50bd`）；評審先想再答（`d2cc7ab`）；迴圈停止（上面）。
   - SilentTalk：Edge 朗讀改走 `api.msedgeservices.com`（`8b0e317`；10/10 起舊位址 403，edge-tts 7.2.8 還在用舊的；忙線 429／503 再試一次）。上游出新版時 `test_edge_styles.py` 會失敗，提醒拿掉覆寫。
3. **v3 的佇列步驟（在 `ea-v3`，正在跑 `v3-think-pilot`）：** `v3-pilot-check`（`thought_stats.py --base base-v2f-high`；任一類切掉 >2% 就停：加大老師的 `--reasoning-budget`、刪 `ea-v3/.runtime/bench/v3-think-pilot` 重跑）→ `v3-py-pilot` → `v3-cards`（C 組補回 55／10）→ `v3-describe`（322 題工具題的請求）→ `v3-base`、`-high`（先看新題有沒有考場錯）→ `v3-tools`、`v3-py`（各兩次）、`v3-scen`（一次，試錄併入）→ `v3-judged` → `v3-thoughts` → 基底的 v3 情境卡、Python。
4. **v3 之後：**
   - `dataset.py` 帶完整思考（聊天題不帶）和不帶思考兩份，各訓一個合一版；數 token，超過 `--max-length 32768` 的多就加大。
   - 角色資料補「要查最新消息的就交給 Agent」：Qwen3.8 寫，不用 `chat_task_eval.jsonl`（那份只考試）。目標聊天工作 ≥39/40。
   - off／high × 0.2、0.6、1.0（基底也補 0.6）→ 蓋最佳溫度 → 情境卡、Python、台詞、`chat_task`（角色回話不能有思考、不能比 char-v1 慢）→ 關卡選贏的，對手是 ms3n。
   - 「從自己的錯學」：含重複關卡提醒之後的那一步、思考裡的迴圈。
   - 出貨時合併 `spec-v3`（含 `next-world`）；`laptop.md` 加記憶的檢視和編輯、PowerShell 7.6.6、唯讀查本機、`test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`。
5. **之後：** coding agent（Qwen3.8 軌跡）；清 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web`、`ea-t1`、`ea-v3` 用完後）；v3 `configs.json` 的 `think512/1024/2048` 合併前刪。使用者問過 AirLLM：每個字都從硬碟讀整個模型，筆電上一步要幾分鐘，不做；要大模型得先加 RAM，再用 llama.cpp 把 MoE 專家放 RAM 實測。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。取樣、上限這類設定每個模型、每個模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或工作的掛載先跑 `--containment`。
3. 考試題先過 `--selftest`（訓練工具題沒有參考解，只看「不做事不能過」）；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練。資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們。吃滿整台機器、大下載先問使用者。考試中不要另外對考場的模型伺服器發請求。
6. 關程序只用確認過的 PID，不用字串比對。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`bench/web_fixture.py`、`bench/grade.py` 是即時掛載（主工作區和 `ea-v3` 都是）。`ea-v3` 的 `edge_agent` 從試錄到錄完都不能改（同一份凍結規格）。每次考試開考時複製一份 `edge_agent`，之後改主線不影響它。
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
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池加 `--no-cache-idle-slots`；考場固定 `--fit off`。請求沒給溫度時讀模型檔（Gemma 4：1.0／64／0.95，min-p 0.05）。當過兩次（-11，都在一個槽生成到 8192 之後），佇列接手續跑，產品會自己重載；再發生就查版本（筆電同版）。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色開口要等：兩個不同 adapter 逾時（30 秒），共用一個 0.62 秒；可用 RAM 只剩 200–290 MiB。
- **老師：** SWE-bench 36/60。v2 錄製（預算 1024）：情境 314 張 15 小時、工具 152 題 1.7 小時、Python 210 題 2.9 小時、評審 1.6 小時；思考中位數情境 1252 字、工具 288 字、Python 245 字（基底 650）。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40；基底 34/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；595 段對話＋角色資料 2 輪約 3.5 小時。

## 7. 踩過的雷

- **沒量過的預設值：** Agent 溫度 0.2 從改寫起就在，對基底剛好，對 adapter 不一定。溫度要每個模型、每個模式各自掃，至少 0.2、0.6、1.0。
- **蒸餾的學生低溫會鬼打牆：** adapter 在 0.2 一字不差重跑失敗的指令，思考裡也會重複到上限；基底不會。
- **錄製省下的預算會被學走：** 預算切掉的正好是最深入的思考。
- **只看分數的關卡會漏掉失控：** 分數贏了，失控照樣出貨；每個里程碑都看結束原因（`reason`）和基底比。
- **考場不忠實會冤枉模型：** 假伺服器不認真實參數、評分把起飛前解鎖當多餘，都算到模型頭上。
- **已知的副作用要追到學生身上：** 每個里程碑都要拿資料和基底比（思考長度、切斷、步數）。
- **自我檢查的題目也要檢查：** 評審沒過自我檢查時，先看是評審錯，還是「壞的那一句」其實也說得通。
- **重試沒用：** 必然重現的失敗重試沒用；佇列失敗就停下，由 session 診斷。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **Node 的錯誤：** 只說「fetch failed」，原因在 `cause`。
- **被殺的 `run.py`：** 它的 relay 會變孤兒留著，停佇列後要清。
- **這台的 `gh`：** 太舊，用 API 的 `head_sha` 查 CI。
- **試跑要走對方的實際路徑。** `cd a && x &` 整串會在背景子殼跑。
