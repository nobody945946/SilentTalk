# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-17 04:17｜SilentTalk、EdgeAgent 開發分支都是 `copilot-story-mode`；規格 v2 凍結（`92a1961`）。v3：EdgeAgent `spec-v3-safety`（worktree `ea-v3-merge`；佇列跑的 `ea-v3` 在 `spec-v3`，同一版）、SilentTalk `spec-v3`（`/home/clawd/worktrees/st-v3`）。v4：EdgeAgent `spec-v4`（開發 `ea-v4`，佇列 `ea-v4q`）、SilentTalk `spec-v4`（`st-v4`）；worktree 都在 `/home/clawd/worktrees/`。
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-17-before-v3n-verdict.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **Agent 是產品，語音角色是玩具（2026-10-14）：** 「把 Agent 做到盡善盡美，這不需要我參與，我偶爾檢查而已」。使用者 10/16 說「照你的步調做」。
- **語音試用結案（2026-10-15）：** 選項模式已移除（`9f29c2a`）；不再做真人測試、不再擴張語音辨識，Discord 真人驗收不做。
- **做不到的不硬做（2026-10-15）：** 逾時的長情境不重錄；沙盒不補 tkinter、ffmpeg；出貨與否由 `ship_gate` 決定。
- **One path：** 每件工作一條路（§2），比完刪掉輸的；同時只有一支佇列；有原生的用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B；評審 Gemma 4 31B。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；預算切掉 ≤2%。聊天題不帶思考（開關兩種都訓）；角色回話不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版。產品的錯誤修正（當機、取樣、迴圈、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。
- **從自己的錯學（2026-10-10）：** 學生先做，沒過的由老師在同一情境接手示範，**加上「學生錯的／老師對的」成對資料做偏好訓練**。
- **出貨規則（`ship_gate.py`）：** 要贏過原版和出貨版（ms3n），各用自己較好的溫度；考試開關思考總分都不低、工具題和 MCP 題各自不低、聊天探針全過、保留情境卡要多過、Python 題不低。
- **長期記憶用原生 `AGENTS.md`（v3）：** 屬於使用者，回報不寫內容；公開查詢絕不能讀到它。
- **輸出不設上限，只要不失控。** Agent 的請求不帶上限（`agent_bridge.mjs` 拿掉 `max_tokens`），只有迴圈守門和 context 會停一步。Agent 64K 是底線；Agent 和角色共用一個 adapter。
- **Discord：** 被叫到才回，冷場不開話題；朋友喊「機魂」照樣回，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意。
- **不輪詢，兩台直接傳訊：** `scripts/dev/channel.py`（只傳 metadata），好了才告訴使用者。筆電的事壓到最少。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ `thought_stats.py` → 評審 → `dataset.py` → SilentTalk `train_lora.py`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用；`deploy.ADAPTERS` 記 SHA256。出貨的 ms3n 在 `EdgeAgent/edge_agent/adapters/`（蓋了關 1.0、開 0.2） |
| **取樣** | adapter 檔上的 `edgeagent.sampling.{off,thinking}.temp`（`stamp_adapter_sampling.py`，量完才蓋）；沒蓋的 0.2 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_judge.py` → `dataset.py` |
| **機魂資料** | SilentTalk `scripts/dev/character_pipeline.sh`（Qwen3.8 寫、E4B 答、Gemma 31B 查、硬關卡）。出錯就停 |
| **兩台溝通** | `channel.py`：`wait` 不刪、`done <id>` 才刪。筆電 `laptop_waker.py` 每批新信開一次 `codex exec` |
| **佇列** | `EdgeAgent/.runtime/fw/queue-v4.sh`（在 `ea-v4q` 跑；v3 的 `queue.sh` 已跑完）：一步一個 `.done`；失敗就停，修好再 `relaunch.sh` |

## 3. 接下來

1. **公開下載（ms3n＋選項移除）：** 已問使用者、還沒回；**沒有「好」就不發**。回好之後：`release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑 → `--publish`，刪 `ea-ship`、`st-ship`。
2. **筆電：** 沒有交辦中的回合。v4 要出貨時才交：批准卡認得 `explicit === 'memory'`（「要寫進你的長期記憶，需要單次批准」）、記憶檢視編輯、PowerShell 7.6.6、唯讀查本機。
3. **v3 線結案：v3、v3n 都 NOT SHIPPED，筆電續用 ms3n。** v3n（10/17 04:16）對原版／ms3n：關 79／106／**111**（選 1.0）、開 117／127／**125**（選 0.2）、情境卡 30／28／**32**、Python 14／35／**33**；開思考時 MCP 49／50 → **46**（比兩者都低）；聊天轉派題 72 題全對（原版 83%、ms3n 92%）。v3n 停得下來（開思考 157 題做完、情境卡只 8 張中途停，v3 是 21 張），但只學了沒思考的列，開思考時研究題常漏標段落編號 `[n]`（研究 7／14）、MCP 變差。v3（10/16）輸在停不下來：思考打亂順序繞到 context 滿、產品擋了記憶 edit 讓老師用 PowerShell 繞過，兩者 v4 已修。v4 用 v3 當接手的學生，不在 v3 上補。數字在 `EdgeAgent/.runtime/fw/msv3-gate.txt`、`msv3n-gate.txt`。
4. **v3 留下的產品修正跟 v4 一起出：** 記憶修正（`811de6f`）、繞圈守門（`b622a02`）、`/chat` 拒絕代碼（`d2be311`）都在 `spec-v4`。沒有 `v3n-shipped`，v4 的關卡對手是原版和 ms3n。試合併分支 `v3-integration`（EdgeAgent `7546f62`、SilentTalk `35c5deb`）不再用，v4 出貨時從 `spec-v4` 重做合併。
5. **v4 佇列（現在，10/17 04:16 開始）：** `v4-carry` 和乾跑一樣（情境卡 317 去 58、長卡 26 去 4、工具 588 去 20、公開工具 112、Python 420 去 6）→ 評審驗證三種中。
6. **v4 已做（CI 都綠）：** 評審看每種題目的回答（`c99a396`）；繞圈守門、Agent 一步用完 context 照實說（`b622a02`）；主人的記憶：read、edit 可碰那一個檔，edit 每次單次批准，指令提到 `pi-state` 也要（`811de6f`）；`/chat` 中途拒絕帶代碼（`d2be311`）；老師接手點加在學生出錯處（`398935f`）；**成對資料**：接手時存下學生在錯處的回答，`dataset.py --pairs`（`15aae64`、`3e0b179`）；SilentTalk `train_lora.py --pairs`：列訓完後做 DPO（參考＝列訓完的 adapter，另存 `<out>-sft` 一起進關卡），`preference_check.py` 在 CPU 驗過（`6df105c`）；SilentTalk：查詢失敗給中文原因（`0f0bf6a`）；v4、v4-sft、v4n、v4n-sft 的 config（關、開、卡各一），ms3n 三個重複的 config 刪掉，測試擋同名（`10652a7`，`ea-v4q` 在這版）。**v4 的提示和工具定義和 v3 一樣**，v3 錄的資料沿用，只換碰過記憶的。
7. **`queue-v4.sh` 的步驟：** `v4-carry` 把 v3 五個 run 複製成 `v4c-*`，拿掉工具呼叫碰過 `pi-state` 的題（情境卡 58、長卡 4、工具 10、Python 3，清單 `ea-v4q/.runtime/agentdata/v4-memory-tasks.json`），刪舊評審 → 評審驗證情境卡、工具、Python（不被信任就停）→ **接手試跑**：學生 v3（`e4b-laptop-v3-high`／`-scen`，v4 產品）做每 10 題工具、每 10 題 Python（21 題）、每 30 張卡 → 評審 → 老師接手（溫度 1.0）→ 評審 → **`v4-pref-dry`**：試跑的列和成對資料、CPU 檢查、GPU 上幾步列訓＋全部試跑成對資料（32K、4-bit、liger、offload）→ v4 評審全部 `v4c-*` → 老師在 v4 產品重錄記憶題（`v4-mem-*`）→ 評審 → 原版在 v4 產品重考（`v4-base*`）→ ms3n 的 v3 考試複製過來、情境卡用 v4 評審重評 → 機魂資料（`st-v4`，試跑 16 段再 400 段，種子同 v3）→ **`v4-takeover-ok` 停下等我**。
8. **接手試跑完成時（約 10/17 09:00，wake 會叫；佇列接著跑無人值守的步驟，約 10/18 清晨才停在 `v4-takeover-ok`）：** 讀試跑：重播漂移幾題（`replay_differs`）、老師在錯處怎麼做、接手後的評審結果、能收幾列幾對，`v4-pref-dry` 的峰值記憶體和保留成對資料前後偏好對的比例；要改的改在 `spec-v4`（CI 綠、佇列停著時 ff `ea-v4q`）。**後半段已寫好草稿** `EdgeAgent/.runtime/fw/queue-v4-second.draft`（語法、分題不重疊、長度檢查乾跑過）：學生做試跑以外的全部訓練題（工具 289、Python 189、卡 306）各一次 → 評審 → 老師接手 → 評審 → `v4-rows`（`v4c-*`、`v4-mem-*`、所有接手 run；both、none 各一份加 `--pairs`）→ 聊天探針的原版和 ms3n 參考（`st-v4`）→ `v4-v3n`（有 `v3n-shipped` 才把 v3n 的 run 搬來、情境卡重評）→ v4、v4n 依序：用 `st-v4` 的 `train_lora.py --pairs` 訓練（列或成對資料超過 32K 被丟 >2% 就停；最終、`-e1`、`-sft` 都轉 gguf）→ 它和它的 `-sft` 各自：三溫度考試 → 聊天探針 → stamp → 情境卡 → Python → `ship_gate`（對原版 `v4-base*`、ms3n，有 `v3n-shipped` 加 v3n，**再加上一個過關的 v4 候選**：過的寫進 `.runtime/fw/v4-best`，佇列跑完時 `v4-best` 裡的那個出貨）。佇列停在 `v4-takeover-ok` 且試跑沒問題時接上：
   ```bash
   cd /home/clawd/EdgeAgent/.runtime/fw && head -n -1 queue-v4.sh > queue-v4.new && cat queue-v4-second.draft >> queue-v4.new && bash -n queue-v4.new && mv queue-v4.new queue-v4.sh
   touch /home/clawd/worktrees/ea-v4q/.runtime/v4-takeover-ok
   cd /home/clawd/EdgeAgent && setsid -f bash .runtime/fw/relaunch.sh >> .runtime/fw/queue.log 2>&1
   ```
   預期：`queue.log` 出現 `== v4-takeover-ok done`、`== v4-student-tools start`。`bash -n` 失敗就不 `mv`，先修草稿。
9. **還沒排的 v4 項目：** 守門停下後讓模型不想直接回答（比整輪結束好），先量；引人去查卻沒附網頁的卡（試專門的問題：逐項列出事實來源），等 GPU 空檔量。**桌面、下載資料夾延到 v5：** 產品邊界已定（檔案工具只在工作資料夾，shell 可以碰系統、照類別批准；v3 的 5,736 次 shell 有 420 次碰到外面，都是查硬體、TEMP 暫存這類正當雜事），v4 不出新卡，沙盒加資料夾用不到。
10. **再之後：** coding agent（要大下載，先問使用者）；清 worktree（`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-takeover`、`ea-v3-t1`、`ea-v3-t1s`）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們（crontab、`musichub-*` 不碰）；吃滿整台、大下載先問。考試或資料流程跑著時不對它的伺服器發請求。
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
- **評審（Gemma 31B，2 槽）：** 機魂的閘題一題平均 18 秒；1,578 題 4 小時。
- **老師錄製（Qwen3.8-27B，4 槽）：** 工具題 588 次 6.3 小時；情境卡 317 張約 18 小時。**評審：** 情境卡 720 次 1.6 小時。
- **訓練 32K 列：** 峰值 14.2 GiB；v3（完整長思考，`--thinking both`，2,599 列）746 步 15 小時 50 分，驗證 loss 0.732 → 0.719；v3n 一步約 60 秒；ms3n 3 小時。
- **v3 一串考試：** 每場 162 題 20–60 分鐘；情境卡 91 張 2.5 小時；Python 57 題 40 分鐘。
- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒；筆電每秒約 20 token，繞到塞滿 context 要等 40 分鐘以上。

## 6. 踩過的雷

- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和思考長度，做完的題另外算通過率。
- **產品自己的提示和守門互相矛盾時，老師照樣錄進去，學生學到繞路：** 錄製前在產品路徑上把每個提示叫它做的事跑一次。
- **迴圈不只一字不差的重複：** 打亂順序繞幾句話也是；新守門先拿全部錄下的訊息校準再上。
- **沒量過的預設值：** 溫度每個模型、每個模式各自掃；長思考的 adapter 低溫會打轉。
- **考場不忠實會冤枉也會教壞模型：** 卡片說桌面卻放 workspace；沒網頁的卡老師照樣去查。
- **「完成」不等於有錄到：** 每步完成都看收和退。分支沒推過就沒跑過 Windows CI。
- **兩條路的同一份規則會漂移：** 出貨關卡在開發分支加了工具／MCP 規則，v3 分支沒有。
- **每份軌跡都有 `pi-state`（系統提示寫了路徑）：** 找碰過記憶的工作要看工具呼叫的參數。工作檔的時間用 `date` 看，不要估。
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API 的 `head_sha`）。**
