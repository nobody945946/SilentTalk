# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-15 15:45｜SilentTalk、EdgeAgent 開發分支都是 `copilot-story-mode`；規格 v2 凍結（`92a1961`）。v3：EdgeAgent `spec-v3-safety`（worktree `ea-v3-merge`；佇列跑的 `ea-v3` 在 `spec-v3`，每次快轉到同一版）、SilentTalk `spec-v3`（`/home/clawd/worktrees/st-v3`）。v4：EdgeAgent `spec-v4`（`ea-v4`）。
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-15-before-v3-train.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **Agent 是產品，語音角色是玩具（2026-10-14）：** 「把 Agent 做到盡善盡美，這不需要我參與，我偶爾檢查而已」。
- **語音試用結案（2026-10-15）：** 選項模式已移除（`9f29c2a`）；不再做真人測試、不再擴張語音辨識，Discord 真人驗收不做。
- **做不到的不硬做（2026-10-15）：** 逾時的長情境不重錄；沙盒不補 tkinter、ffmpeg；v3 用過關卡的資料繼續做，出貨與否由 `ship_gate` 決定。
- **One path：** 每件工作一條路（§2），比完刪掉輸的；同時只有一支佇列；有原生的用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B；評審 Gemma 4 31B。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；預算切掉 ≤2%。聊天題不帶思考（開關兩種都訓）；角色回話不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版。產品的錯誤修正（當機、取樣、迴圈、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。
- **從自己的錯學：** 學生先做，沒過的由老師在同一情境接手示範。
- **出貨規則（`ship_gate.py`）：** 要贏過原版和出貨版（ms3n），各用自己較好的溫度；考試開關思考總分都不低、工具題和 MCP 題各自不低、聊天探針全過、保留情境卡要多過、Python 題不低。
- **長期記憶用原生 `AGENTS.md`（v3）：** 屬於使用者，回報不寫內容；公開查詢絕不能讀到它。
- **輸出不設上限，只要不失控。** Agent 64K 是底線；Agent 和角色共用一個 adapter；Agent 品質優先、角色速度優先。
- **Discord：** 被叫到才回，冷場不開話題；朋友喊「機魂」照樣回，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意。
- **不輪詢，兩台直接傳訊：** 兩台用 `scripts/dev/channel.py` 溝通（只傳 metadata），好了才告訴使用者。筆電的事壓到最少。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ `thought_stats.py` → 評審 → `dataset.py` → SilentTalk `train_lora.py`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用；`deploy.ADAPTERS` 記 SHA256。出貨的 ms3n 在 `EdgeAgent/edge_agent/adapters/`（蓋了關 1.0、開 0.2）；`SilentTalk/.runtime/models/llm/` 的開發複本沒蓋 |
| **取樣** | adapter 檔上的 `edgeagent.sampling.{off,thinking}.temp`（`stamp_adapter_sampling.py`，量完才蓋）；沒蓋的 0.2。bench 照產品讀它，`run.py --sampling` 指定 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_judge.py`（程式關卡＋評審）→ `dataset.py` |
| **機魂資料** | SilentTalk `scripts/dev/character_pipeline.sh`：personas → write（Qwen3.8）→ render → student（E4B）→ check（Gemma 31B）→ filter（硬關卡；`LINES_BY_RULES=1`）。出錯就停，不重試 |
| **角色派工** | SilentTalk `runtime._respond` → `llm.chat_task`（是／否）→ `task_runner.dispatch` |
| **兩台溝通** | `channel.py`：信箱在開發機，`wait` 不刪、`done <id>` 才刪。筆電 `laptop_waker.py` 每批新信開一次 `codex exec` |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停，修好再 `relaunch.sh`；v3 步驟在 `ea-v3` 跑 |

## 3. 接下來

1. **公開下載（ms3n＋選項移除）：** 已問使用者、還沒回；**沒有「好」就不發**。回好之後：`release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑 → `--publish`，刪 `ea-ship`、`st-ship`。
2. **筆電：** 沒有交辦中的回合（第 16 回合 4/4 完成）。
3. **v3 佇列（照順序）：** `v3-char` ✓ → `v3-rows` ✓（2,599 列）→ 對手 ms3n 考完 ✓（數字在第 6 項）→ `v3-train`（13:37 起，746 步、每步約 78 秒，約 16 小時；超過 32768 token 的列 4／6,149）→ `chat_task` 的基底和 `ms3n-v3` → **v3 一路走到關卡**：off／high 各在 0.2、0.6、1.0 → `msv3-chat-task` → `msv3-stamp`（考試總過數最多的溫度，同分取完成多的、再取低的，蓋在檔上）→ 情境卡、Python → `msv3-gate`（印 SHIP 或 NOT SHIPPED，`why.txt` 在候選的 off run 裡）→ **才** `v3n-train` 和它的同一串。順序在 10/15 改過：兩版共用角色資料和訓練設定，v3 先判完能早 16 小時看到兩版共同的問題。舊佇列（PID 1287986）在印出 `== v3n-train start` 時由等待程式停掉、換新腳本重跑，log 會有 `== reorder:` 一行；沒有這行就是舊佇列還在跑 v3n，自己停掉它（v3-train 已完成的話）再 `relaunch.sh`。每步完成看收和退、每類退件看一則。
4. **關卡之後：** 兩版都過，選總分高的；機魂看派工題（v3 題）兩版對基底和 `ms3n-v3`（ms3n 的權重答同一題；出貨的 ms3n 用 v2 題 37/40）。贏的那版跑「從自己的錯學」：學生 `--record` 跑訓練卡 → 評審 → 老師 `run.py --takeover <學生 run> --at 0.4,0.75` → 評審 → 合併重訓。出貨時更新兩個試合併分支再合併（下一項）；`laptop.md` 加：記憶檢視編輯、PowerShell 7.6.6、唯讀查本機。
5. **v3 的修正在哪：**
   - EdgeAgent `spec-v3-safety`（`283b381`）：公開工作的外洩修正、卡片檢查、接手工具、bench 照產品讀 adapter 取樣、沒網路的關卡（沒網頁的卡伸手找網路就不過，`dataset.py` 再擋一次）、考場的公開資料夾、`run.py` 有工作崩潰就以失敗結束；接手不挑當機後重跑過的題（`f2196f0`）；出貨關卡一次比多個對手、Python 題算進去（`283b381`，含從開發分支搬來的工具／MCP 規則 `efe09c8`）。
   - SilentTalk `spec-v3`（`98bada4`）：派工看「答案要不要查」；角色本來就知道的設定自己答；角色聊天由 Qwen3.8 寫；評審答派工問題先想再答。
   - **試合併（10/15，Windows CI 都綠）：** EdgeAgent `v3-integration`（`ea-v3-int`，`7546f62`，7 個衝突兩邊功能都留）、SilentTalk `v3-integration`（`st-v3-int`，`35c5deb`，只有 `turn_eval_model.py` 的 import）。出貨時把 v3 分支的新 commit 再合進去（`ship_gate.py` 用 `spec-v3-safety` 的），然後合進 `copilot-story-mode`。chardata 的規則雜湊（`RULE_FILES`）合併後會變，v3 資料要先做完。
6. **v3 量到的：**
   - 錄製：情境收 120／317（程式關卡擋 97，其中沒網路 25；評審退 100）；長情境 4／26（逾時不重錄）；工具 587 列、Python 340 列、公開工具 56／56。思考切斷都 ≤2%。
   - 基底 E4B：v3 考試關 79、開 117／162；情境卡 30／91；Python 14／57；派工 0.833（Gemma 31B 0.972）。
   - ms3n（出貨的產品和溫度）：v3 考試關 106、開 127／162（v2 題上 79、97／126，對得上它的 v2 紀錄 78、91，考場沒冤枉它）；情境卡 28／91（v2 時 35，掉的 12 張：4 張是 v3 新的程式檢查擋的，像重複搜尋、沒網頁卻上網；8 張評審不過，抽一張是它把金鑰指令寫錯、還說遮起來的金鑰是假的）；Python 35／57。**v3 要過的線：** 關 ≥106、開 ≥127、情境卡 ≥31、Python ≥35，工具和 MCP 各自不低於兩個對手，聊天探針全過。
   - 機魂：試跑第三次過（`gate_chat_task` 0.975）。全套劇本 400 段留 303（被丟：用講的提附件 49、沒照骨架的說話順序 30，關卡擋得對；留下的仍有 52 句打字附件）。評審 4 小時（07:07–11:08）：閘題 1,578 題一致 0.977（派工 0.983、答否 0.981；動手範圍 0.962、答否 0.927；派工指示 0.939），留 3,550 列（派工 1,138、範圍 404、指示 382、回報 472、台詞 751、接下工作 337、冷場 66）。抽查：失敗回報 48 列有 23 列照念英文代碼（「工作失敗了（connection）」），因為產品交給角色的就是原始代碼（`task_runner._FAILED`），見 §3 第 7 項。
7. **v4（`spec-v4`，CI 綠）：**
   - 做完：評審看每一種題目的回答（數字、名稱、計算要和工具結果一致或算對；自我驗證多一種「改錯一個數字」，每種竄改都要擋 90%；`dataset.py` 每個工作都要評審通過）（`c99a396`）；卡片不得要助理捏造內容（`1089117`，v3 的卡只擋到 G-040）；併入 v3 的出貨關卡（`d7febb5`）。
   - 要做：v4 佇列對工具、Python、公開工具 run 也跑 `scenario_judge.py judge`（和 validate）；基線用 v4 評審重評；**引人去查卻沒附網頁的卡**（no_network 的 25 場多半是卡的錯，如 C-052 要三家虛構公司的資料、D-001 沒網頁卻要抓 JSON）：加進現有一致性問題沒用（該擋 14 只擋 1），下一步試專門的問題（逐項列出事實的來源：檔案／網頁／自己／沒有），等 GPU 空檔量，不在佇列跑時佔老師；沙盒的桌面和下載資料夾（產品範圍要先定）；**角色的失敗回報**：`task_runner._FAILED` 改給中文原因（逾時、連不上、回答太長被切斷…），不給原始代碼，機魂資料跟著重做（規格變動，不搬進 v3）。
8. **再之後：** coding agent（要大下載，先問使用者）；清 worktree（`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-takeover`、`ea-v3-t1`、`ea-v3-t1s`）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們（crontab、`musichub-*` 不碰）；吃滿整台、大下載先問。考試或資料流程跑著時不對它的伺服器發請求（10/15 的試驗佔了老師的槽，拖慢劇本）。
6. 關程序只用確認過的 PID。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`web_fixture.py`、`grade.py` 是即時掛載。一個 run 的產品在 run 目錄裡釘住。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列，再背景跑 `relaunch.sh >> queue.log`。**角色流程不繼承佇列的鎖**（它把 fd 9 換成自己的 `state/.lock`）：佇列停在 `v3-char` 時，先 `flock <chardata>/state/.lock true` 再 relaunch，不然重跑的那步會撞上還在跑的流程。訓練中別停佇列。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁和人設編輯器）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在有事時：** `python3 scripts/dev/wake.py` 用工具的背景執行（不是 `&`），**醒來第一件事就是重新掛上**。push 完 `wake.py ci <repo> <完整 sha> [<等著它的事>]`，CI 綠才算完成；交辦筆電：推 `laptop.md` 後 `wake.py round <小時> "<sha> handoff/laptop.md"`。不盲目重試、不預寫備案。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過
# worktree：加 PYTHONPATH=.，用主工作區的 .venv；EdgeAgent 先把 .runtime/node、pi、pwsh 連過去。
```

## 5. 考場和數字

- **沙盒：** 容器沒網路、root 唯讀、非 root；只掛產品的 `edge_agent` 和 bench 的檔案。假網路只在卡片有網頁時開；沒網頁的卡伸手找網路就不過。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；考場固定 `--fit off`；就緒時印 `listening on`。
- **評審（Gemma 31B，2 槽）：** 機魂的派工問題先想再答，一題平均 18 秒；全套 1,578 個閘題 4 小時（試跑的閘題少，一段 0.6 分鐘，全套一段約 0.8 分鐘）。
- **老師：** SWE-bench 36/60；v3 一步想 3.6–4.8 萬字、每路約 14 token/秒。**訓練 32K 列：** 峰值 14.8 GiB；一步（16 列）v2 資料 40 秒，v3 資料（老師完整的長思考，`--thinking both`）78 秒，一版 2 epoch 約 16 小時（ms3n 3 小時）。
- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒。

## 6. 踩過的雷

- **沒量過的預設值：** 溫度每個模型、每個模式各自掃。開發複本和出貨檔的取樣戳記不同（ms3n），對手要照出貨檔的值考。
- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和思考長度。
- **考場不忠實會冤枉也會教壞模型：** 卡片說桌面卻放 workspace；沒網頁的卡老師照樣去查。
- **錄製的提示要等於出貨的提示。**
- **「完成」不等於有錄到：** 每步完成都看收和退。分支沒推過就沒跑過 Windows CI。
- **兩條路的同一份規則會漂移：** 出貨關卡在開發分支加了工具／MCP 規則，v3 分支沒有，差點用舊規則判 v3。
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API 的 `head_sha`）。**
