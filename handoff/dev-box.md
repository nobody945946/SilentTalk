# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-18 09:30｜SilentTalk、EdgeAgent 開發分支都是 `copilot-story-mode`；規格 v2 凍結（`92a1961`）。v3：EdgeAgent `spec-v3-safety`（佇列用過的 `ea-v3` 在 `spec-v3`，同一版）、SilentTalk `spec-v3`（`st-v3`）。v4：EdgeAgent `spec-v4`（開發 `ea-v4`，佇列 `ea-v4q`，都在 `bd002d1`）、SilentTalk `spec-v4`（`st-v4`）；v4 出貨用的迴圈修正：EdgeAgent `v4-ship-loops`（`ea-ship4`，`3fe9d2d`）；worktree 都在 `/home/clawd/worktrees/`。
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-18-before-loop-fix.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **v4 是最後一版（2026-10-17 22:58）：** 「v4 is good enough. we will stop in that moment」。v4 佇列跑完 `ship_gate` 就收工，不做 v5。有候選過關就出貨（筆電在 Windows 驗過才發）；都沒過就續用 ms3n，一樣收工。
- **Agent 是產品，語音角色是玩具（2026-10-14）：** 「把 Agent 做到盡善盡美，這不需要我參與，我偶爾檢查而已」。10/16「照你的步調做」。
- **公開下載（10/17「public is fine」）：** 已發 `windows-2026.10.17`；之後只發筆電回報裡 Windows 驗過的版本。
- **語音試用結案（10/15）：** 選項模式已移除；不再做真人測試、不擴張語音辨識。
- **做不到的不硬做（10/15）：** 逾時的長情境不重錄；沙盒不補 tkinter、ffmpeg；出貨與否由 `ship_gate` 決定。
- **One path：** 每件工作一條路（§2），比完刪掉輸的；同時只有一支佇列；有原生的用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B；評審 Gemma 4 31B。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；預算切掉 ≤2%。聊天題不帶思考（開關兩種都訓）；角色回話不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版。產品的錯誤修正（當機、取樣、迴圈、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。Agent 寧可慢也要好。
- **從自己的錯學（10/10）：** 學生先做，沒過的由老師在同一情境接手示範，加上「學生錯的／老師對的」成對資料做偏好訓練。
- **出貨規則（`ship_gate.py`）：** 要贏過原版和出貨版（ms3n），各用自己較好的溫度；考試開關思考總分都不低、工具題和 MCP 題各自不低、聊天探針全過、保留情境卡要多過、Python 題不低。
- **長期記憶用原生 `AGENTS.md`：** 屬於使用者，回報不寫內容；公開查詢絕不能讀到它。
- **輸出不設上限，只要不失控。** Agent 64K 是底線；Agent 和角色共用一個 adapter。
- **Discord：** 被叫到才回，冷場不開話題；朋友喊「機魂」照樣回，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意。
- **不輪詢，兩台直接傳訊：** `scripts/dev/channel.py`（只傳 metadata），好了才告訴使用者。筆電的事壓到最少。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ 評審 → 學生做、老師接手（`--takeover`）→ 評審 → `dataset.py`（列＋`--pairs`）→ SilentTalk `train_lora.py --pairs`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用；`deploy.ADAPTERS` 記 SHA256。出貨的 ms3n 在 `EdgeAgent/edge_agent/adapters/` |
| **取樣** | adapter 檔上的 `edgeagent.sampling.{off,thinking}.temp`（量完才蓋）；沒蓋的 0.2 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_judge.py` → `dataset.py` |
| **機魂資料** | SilentTalk `scripts/dev/character_pipeline.sh`（Qwen3.8 寫、E4B 答、Gemma 31B 查、硬關卡） |
| **兩台溝通** | `channel.py`：`wait` 不刪、`done <id>` 才刪。筆電 `laptop_waker.py` 每批新信開一次 `codex exec` |
| **佇列** | `EdgeAgent/.runtime/fw/queue-v4.sh`（在 `ea-v4q` 跑）：一步一個 `.done`；失敗就停，修好再 `relaunch.sh` |
| **發布** | `release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑 → 審 ZIP → `--publish` |

## 3. 接下來

1. **現況（10/18 09:30）：主人 10/17 23:04 叫暫停**，佇列停在 `v4c-tools-judged`（`.runtime/fw/paused` 在）；主人的工作約 10/18 05:00 結束，GPU 空著。等主人說「繼續」或自己跑 `resume.sh`，**不要自己重啟**。
   **v4 佇列全程接上了（10/17 22:20）：** 試跑讀完，後半段草稿已接進 `queue-v4.sh`、`v4-takeover-ok` 已放行，不會再停下等我。順序：評審全部 `v4c-*`（`v4c-scen` 做到 223／259 時暫停過，會接著做）→ 老師在 v4 產品重錄記憶題（`v4-mem-*`）→ 評審 → 原版重考（`v4-base*`）→ ms3n 的考試複製、情境卡重評 → 機魂資料（`st-v4`）→ **學生做其餘訓練題**（工具 289、Python 189、卡 306）→ 評審 → 老師接手 → 評審 → `v4-rows`（both、none 各一份加 `--pairs`）→ 聊天探針參考 → v4、v4n 依序訓練（超過 32K 被丟 >2% 就停）→ 各自和 `-sft`：三溫度考試 → 聊天探針 → stamp → 情境卡 → Python → `ship_gate`（過的寫進 `.runtime/fw/v4-best`，跑完時出貨那個）。**每一步 wake 會叫：** 讀每步的收和退、失敗類別各看一筆；要改的改在 `spec-v4`（CI 綠、佇列停著時 ff `ea-v4q`）。學生和老師要 20.5 GB：ComfyUI 在時停在 `rc=3`，跑 `EdgeAgent/.runtime/fw/gpu-waiter.sh <MiB>`（每 10 分鐘看一次，空出來自己 `relaunch.sh`）。**主人要用 GPU 時：** `bash EdgeAgent/.runtime/fw/pause.sh` 停掉整個佇列的程序群組，留下 `.runtime/fw/paused`，並在 `queue.log` 寫 `== paused by the owner`；有這個標記就**不要重啟**，等主人跑 `resume.sh` 或叫我。各步會接著做，訓練則從頭來。
2. **接手試跑的結果（10/17）：** 重播和學生原本的請求一字不差：102 段只有 1 段不同（目錄時間戳，`dataset.py` 照規則丟）。

   | | 接手 | 過檢查和評審 | 收 |
   |---|---|---|---|
   | 工具 | 42 | 21 | 18 列、7 對 |
   | Python | 34 | 17 | 17 列、5 對 |
   | 卡 | 26 | 1 | 1 列、0 對 |

   - **沒過的多半是學生在接手點前就弄壞了：**4 張照片被改成同一個名字，蓋掉 3 張；檔案已經刪了；聊天第一步就開檔。
   - **老師跟著學生的錯方向走：**照用學生取的資料夾名稱；照抄學生拼錯的城市名「Kaohsi」。這個錯字是學生抽樣時偶然拼錯，之後就一路沿用，連讀工具清單都讀錯；用 CPU 在兩版 llama.cpp 上都驗過，伺服器和 adapter 沒有問題。
   - **卡片的檢查和評審看整段對話：**接手點落在學生某個本身就違規的呼叫之後的 10 段，全部因為同一條檢查失敗。`bd002d1` 改成從那個請求接手，第一個請求也算，之後的接手點不跑。
   - **卡片新加的 3 段也沒過：**老師自己也上網、掃硬碟，或沒做到卡片規定。老師從頭錄的卡也只有約 1/3 過評審（223 段過 74）；抽了 14 段被拒的，多數拒得對。全量卡片接手照跑（約 21 GPU 小時）。
   - **`v4-pref-dry`：**72 列（最長 28,552 token）＋22 對，列訓 4 步峰值 11.4 GiB，偏好峰值 13.9 GiB；路線通了。保留只有 1 對，前後差別不算數。
3. **v4 已做（CI 都綠）：** 評審看每種題目的回答（`c99a396`）；繞圈守門、Agent 一步用完 context 照實說（`b622a02`）；主人的記憶：read、edit 可碰那一個檔，edit 每次單次批准（`811de6f`）；`/chat` 中途拒絕帶代碼（`d2be311`）；接手點加在學生出錯處（`398935f`）、卡片從第一個違規呼叫接手（`bd002d1`）；成對資料（`15aae64`、`3e0b179`、SilentTalk `6df105c`）；查詢失敗給中文原因（`0f0bf6a`）；評審的數字核對、逐項讀回覆、答案結尾、驗證取樣（`1c0662b`、`fba3068`、`54df1ee`、`567da2e`、`e20334d`、`8edcf8f`、`6994dac`）。**v4 的提示和工具定義和 v3 一樣**，v3 錄的資料沿用，只換碰過記憶的。v3 留下的產品修正（`811de6f`、`b622a02`、`d2be311`）跟 v4 一起出；v4 出貨時從 `spec-v4` 重做合併。
4. **評審自己的弱點（不改）：** 卡片寫死「今天」的規定照卡片判（317 張有 16 張，例 B-004）；中文切在詞後讀得通的截斷；510GB、5-6、.318 這類嚴判；偶爾漏答一項（約 5%）。
5. **v3 線結案：** v3、v3n 都 NOT SHIPPED，筆電續用 ms3n（數字在 `EdgeAgent/.runtime/fw/msv3-gate.txt`、`msv3n-gate.txt`）。v4 的關卡對手是原版和 ms3n。
6. **筆電：** 沒有交辦中的回合。v4 要出貨時才交：批准卡認得 `explicit === 'memory'`、記憶檢視編輯、PowerShell 7.6.6、唯讀查本機。
7. **公開下載：** `windows-2026.10.17`（SilentTalk `8ab28a9`、EdgeAgent 2.1.0 `bootstrap-v8`）。
8. **出貨時一起帶的產品修正（迴圈類，§1 允許搬進出貨版），已做好：** EdgeAgent `v4-ship-loops`（`3fe9d2d`，CI 綠，worktree `ea-ship4`，從 `spec-v4` 開）。pi 先驗參數才叫 `tool_call` 鉤子，參數不合（或工具不存在）的呼叫原本完全不計 repeat 4 次和 64 次上限；老師照錯的 enum 打了幾十次，直到 900 秒逾時。現在每個呼叫在 `tool_execution_start` 記下（pi 等它跑完才驗參數）；`tool_call` 照舊計它看到的，沒看到的在 `tool_execution_end` 用同一個函式計：同一個被退回的呼叫第 4 次就停，每個都算進 64 次。測試 `test_real_sdk_counts_the_calls_pi_refuses_for_their_arguments`（這台的 `node.exe` 連到 Linux 的 node，真 SDK 測試在這裡會跑）。**不要合進 `spec-v4`**：佇列後面的學生和考試要用凍結的橋接層。出貨時從 `spec-v4` 重做合併再合這個分支，筆電在 Windows 驗。原本放 v5 的其他項目都不做：pi 驗證錯誤不列允許值、考場日期、桌面和下載資料夾、`mcp_ask-02`、評審收成對答案、守門後先回答。
9. **收工時：** 出貨（或決定不出）後清 worktree（`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-takeover`、`ea-v3-t1`、`ea-v3-t1s`，出貨合併後的 `ea-ship4`；`ea-t1`、`ea-v3-t1*` 的 commit 沒推過，先開分支），告訴使用者結果。coding agent 不做。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們（crontab、`musichub-*` 不碰）；吃滿整台、大下載先問。考試或資料流程跑著時不對它的伺服器發請求（測試開自己的 CPU 伺服器，用完照 PID 關）。
6. 關程序只用確認過的 PID。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`web_fixture.py`、`grade.py` 是即時掛載。一個 run 的產品在 run 目錄裡釘住。比較進行中發現的修正放下一版的分支。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列，再 `setsid -f` 跑 `relaunch.sh >> queue.log`。訓練中別停佇列。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁和人設編輯器）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在有事時：** `python3 scripts/dev/wake.py` 用工具的背景執行（不是 `&`），**醒來第一件事就是重新掛上**。push 完 `wake.py ci <repo> <完整 sha> [<等著它的事>]`，CI 綠才算完成。不盲目重試、不預寫備案。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過
# worktree：用主工作區的 .venv；EdgeAgent 先把 .runtime/node、pi、pwsh 連過去。
```

## 5. 考場和數字

- **沙盒：** 容器沒網路、root 唯讀、非 root；只掛產品的 `edge_agent` 和 bench 的檔案。假網路只在卡片有網頁時開。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；考場固定 `--fit off`。
- **評審（Gemma 31B，2 槽）：** 情境卡 720 次 1.6 小時；機魂閘題 1,578 題 4 小時。
- **老師（Qwen3.8-27B，4 槽，約 41 tok/s）：** 工具題 588 次 6.3 小時；情境卡 317 張約 18 小時。接手：工具 42 段 55 分、Python 34 段 51 分、卡 23 段 57 分（一段 13 秒到 45 分）。
- **學生 v3（E4B，4 槽）：** 工具 33 題 10 分、Python 21 題 10 分、卡 11 張 7 分。
- **訓練 32K 列：** 峰值 14.2 GiB；v3（2,599 列）746 步 15 小時 50 分；偏好訓練峰值 13.9 GiB。
- **v3 一串考試：** 每場 162 題 20–60 分鐘；情境卡 91 張 2.5 小時；Python 57 題 40 分鐘。
- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒；筆電每秒約 20 token。

## 6. 踩過的雷

- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和思考長度，做完的題另外算通過率。
- **產品自己的提示和守門互相矛盾時，老師照樣錄進去，學生學到繞路：** 錄製前在產品路徑上把每個提示叫它做的事跑一次。
- **迴圈不只一字不差的重複：** 打亂順序繞幾句話也是；兩個呼叫輪流打也是。
- **守門要放在每個呼叫都會經過的地方：** pi 先驗參數才叫 `tool_call`，被退回的呼叫就繞過所有上限；`tool_execution_start` 每個都經過。
- **沒量過的預設值：** 溫度每個模型、每個模式各自掃；長思考的 adapter 低溫會打轉。
- **考場不忠實會冤枉也會教壞模型：** 卡片說桌面卻放 workspace；沒網頁的卡老師照樣去查；題目的日期早於考場的今天。
- **「完成」不等於有錄到：** 每步完成都看收和退。分支沒推過就沒跑過 Windows CI。
- **接手前先找出錯在哪：** 檢查看整段的話，錯處之後的接手注定失敗（卡片 10／10）；接手點越早，老師越不會跟著學生的方向走。
- **一次抽樣的錯會被自己帶著走：** 先查推論路徑（同一請求換 CPU、換版本重跑），再怪模型。
- **評審的輸出要逐項讀、留原文；被丟的好資料要逐類看原因；驗證的假錯要真的錯。**
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API）、`sleep` 等待被擋（用 until 迴圈）。**
