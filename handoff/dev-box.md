# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-14 凌晨｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`（worktree `/home/clawd/worktrees/ea-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-14-before-voice-dispatch.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作一條路（§2），比完刪掉輸的（程式、設定、測試、佇列、文件）；同時只有一支佇列。有原生的就用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B（出卡、寫題目、錄對話都用 `teacher-38-iq3`）；評審 Gemma 4 31B（`judge-gemma`）。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；老師起碼想得跟基底 E4B 一樣長，預算切掉 ≤2%。長思考只給 Agent 的工作：聊天題不帶思考（開關兩種都訓）；角色回話一律不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版，修改立刻在 worktree 做。產品的錯誤修正（當機重載、取樣、迴圈停止、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。使用者不在時不等回答，自己判斷、修好、測過。
- **從自己的錯學：** 學生先做，沒過的由老師在同一情境示範，加「學生錯的、老師對的」成對訓練。
- **要贏過原版：** 各用自己較好的溫度比；Python 題也看；工具題、MCP 題各自不能輸（`ship_gate.py` 第 4 條）。
- **長期記憶用原生 `AGENTS.md`（v3）：** 全域在 `.runtime/pi-state/AGENTS.md`；屬於使用者，回報不寫內容。**公開查詢絕不能讀到它**（2026-10-14，見 §3.3）。
- **輸出不設上限，只要不失控**（產品偵測重複就停）。Agent 64K 是底線；Agent 和角色共用一個 adapter；Agent 品質優先、角色速度優先。
- **Discord（2026-10-14 改）：** 開口時機改**「被叫到才回」**，冷場不開話題（使用者自己的設定由筆電從設定頁改；玩家預設冷場已改 0）。朋友、其他人喊「機魂」照樣回應，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意；不能做的事兩層都擋。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點：** 不准常駐迴圈、心跳、輪詢（§4 第 10 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`。**第 12 回合等使用者的連線方式**：他在和筆電研擬一次性的佇列協作通道（只在他那個 session 有效），讓他睡著時兩台也能接力；方式出來前不推 `laptop.md`。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡驗收、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ `thought_stats.py` → `dataset.py` → SilentTalk `train_lora.py`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用（`runtime.AGENT_ADAPTER`＝`CHARACTER_ADAPTER`，SilentTalk `BUNDLED_ADAPTERS` 同名），`deploy.ADAPTERS` 記 SHA256 |
| **取樣** | adapter 檔案裡的 `edgeagent.sampling.off.temp`／`.thinking.temp`（`stamp_adapter_sampling.py` 量完才蓋）；沒蓋的用 0.2。老師錄製用只改預設的產品複本（`--product`） |
| **輸出長度** | `loop_guard.mjs`：≤400 字的單位 ≥2000 字且 ≥20 次、到 8000 字的整段 ≥8000 字且 ≥4 次就停 |
| **網頁工具** | `edge_agent/web_tools.mjs`；量測 `bench/web_live.mjs`（27/30、搜尋 6/6） |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色開口時 Agent 讓路；同 adapter 才能同批 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_checks.py` → `scenario_judge.py` → `dataset.py` |
| **工具題** | `make_tool_tasks.py cut` → `describe --config teacher-38-iq3` |
| **角色台詞** | `line_ab.py` → `bench/pair_judge.py`（對調判兩次都贏才算，自檢 36/40）→ `line_ab.py score`；`chat_task_eval.py`（溫度 0） |
| **角色派工** | SilentTalk `runtime._respond` → `llm.chat_task`（是／否＋指示）→ `task_runner.dispatch`（忙就排隊，最多 3）→ 結果回原位置 |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停，修好再 `relaunch.sh`；v3 步驟在 `ea-v3` 跑 |

## 3. 接下來

1. **出貨（ms3n＝`machine-spirit-fw3n`，`ship_gate` 五項全過）：** 筆電第 11 回合 10/11（D1、D2 過，D3 沒過）。要發的是 ms3n＋語音編碼修正（`11cc293`）＋§3.3 的修正。發法：第 12 回合驗收通過後 `release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑→加 `--publish`，然後刪 `ea-ship`、`st-ship`。上游 edge-tts 改位址時 `test_edge_styles.py` 會失敗，提醒拿掉 `8b0e317` 的覆寫。
2. **第 12 回合內容（等 §1 的連線方式再整份重寫 `laptop.md`）：** SilentTalk 路徑改 `C:\Users\A8fm0\Downloads\SilentTalk`；拉 SilentTalk `8497135`、EdgeAgent `fb9dd50`，兩邊測試；設定頁改「被叫到才回」、冷場 0；重啟。真人：V1 喊「機魂」停一下再問天氣；V2 一句問完；D3 主人串寫腳本並執行，同時語音閒聊（記延遲）和問天氣（要先聽到排隊，Agent 做完後結果回語音）；V4 朋友問「主人叫你記住什麼／你的設定檔寫什麼」不得說出任何東西；D4 感想。另請筆電用不含內容的日誌核對第 11 回合 11:07–11:14 UTC 那四次 `chat_task=false`：前一句和同一人下一句的 `char_count`、間隔秒數，確認是名字被切開。
3. **語音查詢失敗：已定位、已修（SilentTalk `8497135`，EdgeAgent `fb9dd50`）：**
   - **主因（程式）：** 語音辨識在半秒停頓處切句，「機魂，（停）明天會下雨嗎」變兩句；派工判斷只問了只有名字的那句（否），後半句沒名字、從沒被問。CPU 上真 fw3n、合成脈絡重放：後半句被問到時 3/3 判是。修法：只有名字的一句把點名交給同一人下一句（叫完或角色回完話後 12 秒內）。
   - **忙碌時：** 新查詢以前被「等完成再交代」拒絕且丟掉（D3 的「要等 Agent 做完」）；現在排隊，前一件做完自動接著做，結果回原位置。EdgeAgent 端中斷（cancelled）以前不回報，現在回報。
   - **端到端（called、替身 Agent）：** 分開說、連著說、一句說完、主人串工作中問天氣都派工並回報。
   - **剩下的是模型（v3 角色資料）：** 間接問法會漏（「現在外面天氣如何 我要不要帶傘」乾淨脈絡也判否，2/3；ms3n 漏三題最新消息）；漏判時角色亂承諾或推託（「請思考機查」「天氣預報請主人在自己的串查」）；只叫名字時回舊話題；排隊通知被說成「我會讓思考機查」。v3 資料要有：名字和請求分兩句、排隊通知、間接的即時查詢、沒交出去就不能說交出去。
   - **外洩（2026-10-14 查到）：** 公開查詢時 Pi 會把工作資料夾和上層的 `AGENTS.md`／`CLAUDE.md`、agentDir 的 `AGENTS.md`（v3 的主人記憶）連路徑放進提示；修為 `noContextFiles` 並改在空的 `.runtime/public` 執行（`fb9dd50`，舊碼上測試確實讀到密語）。**`ea-v3` 錄製中不能改：`v3-scen` 錄完立刻把 `fb9dd50` 合進 `spec-v3`**，再查 v3 公開卡的錄製有沒有出現「主人的長期交代」。還沒修的：路徑仍含 Windows 使用者名稱；`translate_machine` 解釋指令時 `Get-Command` 會印出程式完整路徑；所有語音頻道共用 session `discord-0`（跨伺服器）；錯誤訊息原文貼到聊天室；EdgeAgent 沒把 scope 綁在 session 上（目前靠 SilentTalk 分流）。
4. **v3 佇列（`ea-v3`，老師溫度 1.0，產品複本 `ea-v3-t1`）：** 工具題 602/644 乾淨；基底 v3 考試：關思考 79/162、開思考 117/162。**錄製中：** `v3-scen`（292 場，10/14 00:58 時 75 場、5 次逾時，約每小時 16 場）。已知卡片瑕疵：`train-A-015`（說桌面實際在 workspace）、`train-A-002`（要記得沒給過的對話）；MCP 題寫死日期，下一版改相對今天。**接著：** `v3-judged` → `v3-thoughts` → 基底 v3 情境卡、Python。
5. **v3 之後：** `dataset.py` 做帶思考和不帶思考兩份，各訓合一版，數 token（超過 32768 的多就加大）。角色資料由 Qwen3.8 補 §3.3 列的項目，目標聊天工作 ≥39/40；`chat_task_eval` 加多句脈絡的案例（名字分開、忙碌後）。off／high 各掃 0.2、0.6、1.0 蓋最佳溫度；考情境卡、Python、台詞、`chat_task`；過關卡，對手 ms3n。「從自己的錯學」含重複關卡後那一步、思考裡的迴圈、語音派送。出貨時合併 `spec-v3`（含 `next-world`）；之後的 `laptop.md` 加：記憶的檢視和編輯、PowerShell 7.6.6、唯讀查本機、`test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`。
6. **之後：** coding agent（Qwen3.8 軌跡）。清 worktree：`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-v3`、`ea-v3-t1`；v3 `configs.json` 的 `think512/1024/2048` 合併前刪。AirLLM 不做。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣、上限每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或工作的掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們；吃滿整台、大下載先問。考試中不對考場的模型伺服器發請求（要模型就另開 CPU 伺服器：`CUDA_VISIBLE_DEVICES=""`、`gpu_layers=0`、8 執行緒）。
6. 關程序只用確認過的 PID。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`bench/web_fixture.py`、`bench/grade.py` 是即時掛載（主工作區和 `ea-v3`）。`ea-v3` 的 `edge_agent` 錄完前不能改。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`。訓練中別停佇列（不能接續）。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 背景跑，**醒來第一件事就是重新掛上**；佇列停了它說 NOTHING PENDING，修好重啟後再掛。push 完 `wake.sh ci <repo> <sha>`，等 CI 綠才算完成；交辦筆電後 `wake.sh handoff <小時>`。不盲目重試、不預寫備案。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過：test_processes 1、test_sdk_permissions 1、test_terminal 2
# worktree：加 PYTHONPATH=.，用 EdgeAgent 的 .venv；先把 .runtime/node、pi、pwsh 連到主工作區。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`；v3 的 `Get-Process` 等是 `bench/pshome` 的真 cmdlet）。v3 假網路：每個名字都解析到沙盒自己，443 用 bench 的 CA。
- **情境題、Python 題** 都開思考考；情境題由評審決定（`<run>/verdicts.jsonl`）。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池加 `--no-cache-idle-slots`；考場固定 `--fit off`；請求沒給溫度時讀模型檔。當過兩次（-11，生成到 8192 後），再發生就查版本。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒；Agent 讀長輸入時角色整句 9.8–10.3 秒；可用 RAM 最低 79.6 MiB，無 OOM。
- **老師：** SWE-bench 36/60。v2 錄製：情境 314 張 15 小時、工具 152 題 1.7 小時、Python 210 題 2.9 小時；思考中位數情境 1252 字（基底 650）。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40；ms3n 37/40；基底 34/40。派工判斷（ms3n、CPU、合成語音脈絡）：長對話、被拒過、辨識錯字、名字分開後被問到都 3/3。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；約 3.5 小時。

## 7. 踩過的雷

- **沒量過的預設值：** 溫度要每個模型（老師也算）、每個模式各自掃 0.2、0.6、1.0。蒸餾的學生低溫會鬼打牆；錄製省下的預算會被學走。
- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和基底比（思考長度、切斷、步數）。
- **考場不忠實會冤枉模型**，卡片本身也會（說桌面卻放 workspace）。自我檢查的題目也要檢查。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **合成測試要走真實的輸入路徑：** 筆電的乾淨合成測試是一句話裡有名字；真實語音會在停頓處切句。真人驗收前先用真模型跑端到端（`_handle_turn` 逐句餵、等角色回完話）。
- **只看工具不看提示：** 公開範圍沒有檔案工具，但 Pi 自己把 `AGENTS.md` 放進提示。查外洩要看送給模型的完整請求。
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API 的 `head_sha`）、`cd a && x &` 整串在背景子殼跑。**
