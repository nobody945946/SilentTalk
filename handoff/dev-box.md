# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-15 05:00｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 凍結（`92a1961`），v3：EdgeAgent `spec-v3-safety`（worktree `ea-v3-merge`；佇列跑的 `ea-v3` 在 `spec-v3`，每次都快轉到同一版）、SilentTalk `spec-v3`（worktree `/home/clawd/worktrees/st-v3`）。兩個 v3 分支 10/15 起推上 GitHub，Windows CI 綠（SilentTalk 的要手動觸發：`gh api -X POST repos/nobody945946/SilentTalk/actions/workflows/windows-tests.yml/dispatches -f ref=spec-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-15-before-char-v3.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **Agent 是產品，語音角色是玩具（2026-10-14）：** 「把 Agent 做到盡善盡美，這不需要我參與，我偶爾檢查而已」。
- **語音試用結案（2026-10-15，筆電第 15 回合回報 `ed6573d`）：** 語音辨識有限但可用、打字舒服；「選項模式很差勁，可以拔掉省效能」（已移除，`9f29c2a`）。不再做真人測試、不再擴張語音辨識改良，Discord 真人驗收不是延後而是不做。
- **做不到的不硬做（2026-10-15）：** 逾時的長情境不重錄；沙盒不補 tkinter、ffmpeg；v3 用過關卡的資料繼續做，出貨與否由 `ship_gate` 對原版和 ms3n 決定。
- **One path：** 每件工作一條路（§2），比完刪掉輸的；同時只有一支佇列。有原生的就用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B（出卡、寫題、錄對話、寫角色聊天都用它）；評審 Gemma 4 31B。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；預算切掉 ≤2%。聊天題不帶思考（開關兩種都訓）；角色回話不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版。產品的錯誤修正（當機、取樣、迴圈、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。使用者不在時自己判斷、修好、測過。
- **從自己的錯學：** 學生先做，沒過的由老師在同一情境接手示範。
- **要贏過原版和出貨版：** 各用自己較好的溫度比；Python 題也看；工具題、MCP 題各自不能輸（`ship_gate.py`）。
- **長期記憶用原生 `AGENTS.md`（v3）：** 屬於使用者，回報不寫內容；公開查詢絕不能讀到它。
- **輸出不設上限，只要不失控。** Agent 64K 是底線；Agent 和角色共用一個 adapter；Agent 品質優先、角色速度優先。
- **Discord：** 「被叫到才回」，冷場不開話題。朋友喊「機魂」照樣回，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **不輪詢，兩台直接傳訊（2026-10-14）：** 任何地方都不定時問；兩台用 `scripts/dev/channel.py` 溝通（只傳 metadata），好了才告訴使用者。一回合＝整份重寫 `laptop.md`＋`wake.py round`。筆電的事壓到最少：只交開發機做不到的（他的設定、Windows 本機）。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ `thought_stats.py` → `dataset.py` → SilentTalk `train_lora.py`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用，`deploy.ADAPTERS` 記 SHA256 |
| **取樣** | adapter 檔的 `edgeagent.sampling.{off,thinking}.temp`（`stamp_adapter_sampling.py`，量完才蓋）；沒蓋的 0.2。bench 照產品讀它（v3 起），掃溫度用 `run.py --sampling`；老師錄製用改預設的產品複本 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（含 `consistency`）→ `run.py` → `scenario_judge.py`（先跑 `scenario_checks.failures`，再由評審看）→ `dataset.py`（每個工作再過一次關卡） |
| **機魂資料** | SilentTalk `scripts/dev/character_pipeline.sh`：personas → write（Qwen3.8，`chardata_write.py` 骨架）→ render → student（E4B）→ check（Gemma 31B）→ filter（硬關卡；台詞照規則收 `LINES_BY_RULES=1`：評審比台詞前後對調會翻三成，比較和設定檢查只報不擋）。寫手不開思考。伺服器就緒看它印的 `listening on`；出錯就停，不重試 |
| **角色派工** | SilentTalk `runtime._respond` → `llm.chat_task`（是／否）→ `task_runner.dispatch`（忙就排隊，最多 3）；只叫名字（`NameMatcher.bare`）把點名交給同一人下一句 |
| **SilentTalk 對話頁** | 只有「角色」和「打字」（選項模式 10/15 移除）。角色沒開時，聽到的話只轉錄、顯示、記錄，不問模型。舊 `settings.json` 寫了 `options` 照常載入（`ai_options.REMOVED_LORA_PARTS`） |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **兩台溝通** | `channel.py`：信箱在開發機，`wait` 不刪、`done <id>` 才刪；筆電的通道金鑰只能跑 `channel.py gate`。筆電 `laptop_waker.py`（登入時啟動）每批新信開一次 `codex exec`；筆電關機時信留著，開機後接 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停，修好再 `relaunch.sh`；v3 步驟在 `ea-v3` 跑 |

## 3. 接下來

1. **出貨 ms3n（`machine-spirit-fw3n`，關卡五項全過）＋選項移除：** Windows 驗收第 14 回合過了；Discord 真人驗收依 10/15 結案不做；筆電第 16 回合過了。**公開下載要不要發，已問使用者、還沒回；沒有「好」就不發。** 回好之後：`release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑 → `--publish`，告訴使用者，刪 `ea-ship`、`st-ship`。edge-tts 改位址時拿掉 `8b0e317` 的覆寫。
2. **筆電：** 第 16 回合完成 4/4（`laptop-report` `6c37dd8`）：拉到 `2b18a3f`，使用者自己的設定載入印 `settings ok True ['line', 'task']`。現在沒有交辦中的回合。
3. **v3 的修正在哪：**
   - EdgeAgent `spec-v3-safety`（`57276da`）：公開工作的外洩修正、卡片檢查、接手工具、掃整顆磁碟的工作不出資料、bench 照產品讀 adapter 取樣＋v3／v3n／ms3n 設定、伺服器就緒看輸出；**沒網路的關卡**（`ffee223`、`f430f64`）：沒網頁的卡伸手找網路（ping、pip install、Resolve-DnsName、`web_*`）就不過；任何工具結果說名字解析不到也不過（自己寫的腳本連出去時看不到呼叫）；`dataset.py` 對每個工作再擋一次。**考場的公開資料夾**（`e94e060`）：每個工作掛自己的 `.runtime/public`（`chat.PUBLIC_DIR`；唯讀沙盒建不了，`v3-tools-public` 56 個全崩）；`run.py` 有工作崩潰就以失敗結束，`thought_stats` 略過崩潰列（`57276da`）。第一次 Windows CI 修了三個測試（`1be623a`）。全套只剩 4 個只在 Windows 過。
   - SilentTalk `spec-v3`（`98bada4`）：派工看「答案要不要查」不看問法；**解釋只算貼在聊天室的東西，角色本來就知道的（自己世界的設定）自己答**（`83a01e5`，試跑 d 的不一致有 5／9 是「STC 是啥」）；角色聊天由 Qwen3.8 在開發機寫（骨架含只叫名字、忙時排隊、朋友套話要婉拒；許諾去查的回話不訓練）；**評審答派工問題先想再答、並知道角色的設定用語**（`98bada4`：同 30 列直接答 23、想過 26、想過＋設定 27；其他閘仍一個字）。`chat_task_eval` 加 27＋4 題（k01–k04 設定題）。全套 440 過。
   - 老師的產品複本：`ea-v3-t1`（錄製用，安全修正前）、`ea-v3-t1s`（`spec-v3-safety`＋老師 1.0）。
4. **v3 量到的（10/15）：**
   - `v3-judged`：收 120／317（程式關卡擋 97，其中沒網路 25；評審退 100）。抽看 C、G 類退件幾乎都是真錯（欄位、排序、沒交表；閒聊時就搜尋），零星誤判（C-024），評審不改（自我驗證原本收 24/40、竄改退 71/72）。`v3-long-judged`：收 4／26（完成 18、逾時 6、失控 2；逾時不重錄）。
   - `v3-tools` 587 列（沒網路的關卡擋 5：`pip install Pillow` 失敗）、`v3-py` 340 列（擋 1：匯率 API 解析不到）、`v3-tools-public` 重錄 56／56 過（沒有沙盒路徑；中位 0.7 分鐘）。工具題的檢查只核對被問的結果：`public_ok-05-r0` 多講的分錢說明算錯（說 8 人拿 .66，應是 4 人），照樣過；開發機不挑資料，v4 讓評審也看工具題的回答。
   - 思考切斷：情境 0.7%、長情境 2.0%、Python 0.35%、工具 0%（`--max-cut 1` 過）。
   - 基底 E4B：v3 情境評測卡 30／91、Python 14／57。派工評測（含 k 題）基底 0.833、Gemma 31B 0.972。
   - 機魂試跑：d、e 被擋（`gate_chat_task_agree` 0.75、0.767），第三次過（0.975，40 列；整體閘 0.974，`task_text` 0.909），留下 137 列，抽看各類正常。
5. **v3 佇列（照順序）：** 錄製、評審、基底評測、`v3-char-pilot` 完成 → `v3-char`（400 段，05:00 起，約 5–6 小時）→ `v3-rows`（`--thinking both` 和 `none`）→ `v3-train`、`v3n-train`（超過 32768 token 的列多於 2% 就停，量 VRAM 後選更長的視窗）→ 兩版 off／high 各在 0.2、0.6、1.0 → `chat_task`（基底、兩版，v3 題目）。每步完成看收和退、每類退件看一則。
6. **之後（佇列跑到時寫）：** 每版選各模式最好的溫度蓋在檔上；考 v3 情境卡、Python；對手 ms3n 用它出貨時的產品（`--product`）考同一批題目；`ship_gate`。贏的那版跑「從自己的錯學」：學生 `--record` 跑訓練卡 → 評審 → 老師 `run.py --takeover <學生 run> --at 0.4,0.75` → 評審 → 合併重訓。出貨時合併兩個 v3 分支：SilentTalk 的 `llm.py`、`reply_*` 會和選項移除衝突（用 `copilot-story-mode` 的，再補 spec-v3 的派工改動），`turn_eval_model.py` 的 import 衝突（用 spec-v3 的再加 `threading`、`Iterator`）；chardata 的規則版本雜湊（`RULE_FILES`）在合併後會變，v3 資料要在合併前做完。`laptop.md` 加：記憶檢視編輯、PowerShell 7.6.6、唯讀查本機。
7. **事件等待：** 產品裡已改完、第 14 回合在 Windows 驗過（v3 分支出貨時才合併）。留著的重試（Discord 語音自我修復，語音已結案不改）和介面計時器（`ui.py`、`settings_ui`，筆電範圍）不動。
8. **再之後：** coding agent（要大下載，先問使用者）；v4：沙盒要有桌面、下載資料夾，故事會引人去查資料的卡給網頁；清 worktree（`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-takeover`、`ea-v3-t1`、`ea-v3-t1s`）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們（crontab、`musichub-*` 不碰）；吃滿整台、大下載先問。考試中不對考場的伺服器發請求。
6. 關程序只用確認過的 PID。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`web_fixture.py`、`grade.py` 是即時掛載。一個 run 的產品在 run 目錄裡釘住，續跑沿用。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`（核心層等鎖）。訓練中別停佇列。`queue.sh`、`run.py`、角色流程都不等 GPU：空間不夠就印出占用者並停下。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁和人設編輯器）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在有事時：** `python3 scripts/dev/wake.py` 用工具的背景執行（不是 `&`），**醒來第一件事就是重新掛上**。它在核心層等：筆電訊息、佇列日誌、CI（預計跑完時問一次）、交出去的回合逾期（只叫一次；筆電收件時重新起算，回報就結束）。push 完 `wake.py ci <repo> <完整 sha> [<等著它的事>]`，CI 綠才算完成；交辦筆電：推 `laptop.md` 後 `wake.py round <小時> "<sha> handoff/laptop.md"`；問筆電：`channel.py send laptop note "..."`。不盲目重試、不預寫備案。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過
# worktree：加 PYTHONPATH=.，用各自主工作區的 .venv；EdgeAgent 先把 .runtime/node、pi、pwsh 連過去，st-v3 連 .runtime/models、tools。
# 介面流程：xvfb-run .runtime/tools/ui-preview-env/bin/python scripts/dev/ui_preview.py --font "Noto Sans CJK TC"，印 UI flow OK
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路（`--network none`）、root 唯讀、非 root。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`）。**假網路只在卡片有網頁（`web`）時開**：每個名字都解析到沙盒自己，443 用 bench 的 CA；沒網頁的卡是真的解析失敗，所以關卡擋伸手找網路的對話（B、E、G 有網頁；D、H、I 沒有；A、C、F 看卡；J 是 API）。
- **情境題、Python 題** 都開思考考；情境題由評審決定（`<run>/verdicts.jsonl`：`checks` 是程式關卡，`judge` 是每一票的必做 M／不可 N 項和評審引的原文；一票不過就不過）。relay 只錄請求，模型最後一次的輸出不在 records 裡。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；考場固定 `--fit off`；請求沒給溫度時讀模型檔；就緒時印 `listening on`。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒；可用 RAM 最低 79.6 MiB，無 OOM。整句回話在筆電的時間沒量過（`smoke.py` 門檻 4 秒）。
- **老師：** SWE-bench 36/60。v3 一步想 3.6–4.8 萬字、每路約 14 token/秒；失控（重複被停）約 2%。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40；ms3n 37/40；基底 34/40（v2 題目）。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；ms3n 1,325 列 2 輪約 3 小時。

## 7. 踩過的雷

- **沒量過的預設值：** 溫度要每個模型、每個模式各自掃。bench 曾經不讀 adapter 檔上的溫度，量到的都是 0.2。
- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和基底比（思考長度、切斷、步數）。
- **考場不忠實會冤枉模型，也會教壞模型：** 卡片說桌面卻放 workspace；沒網頁的卡老師照樣去查，沙盒的解析失敗被寫成「主人的網路斷了」或拿空沙盒的結果回答（10/14 找到 25 場情境＋6 個工具／Python 工作，已由關卡擋）。
- **錄製的提示要等於出貨的提示：** 錄完才改的產品（公開範圍遮掉 `<cwd>`），受影響的題要用新產品重錄。
- **合成測試要走真實輸入路徑：** 真實語音會在停頓處切句；介面檢查要照控制器實際說出的字（Enter 留下的換行會被 `normalize_text` 去掉）。
- **只看工具不看提示：** 查外洩要看送給模型的完整請求。
- **「首字時間」不是「整句時間」**：門檻不能拿首字的數字訂。
- **錄製「完成」不等於有錄到：** 每步完成都看收和退（10/15 公開工具題 56 個全崩還被記成完成，喚醒的最後幾行看得到）。分支沒推過就沒跑過 Windows CI，出貨合併前才會發現（10/15 推上去才找到三個）。
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API 的 `head_sha`）、`cd a && x &` 整串在背景子殼跑。**
