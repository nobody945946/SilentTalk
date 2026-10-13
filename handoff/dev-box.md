# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-14 清晨｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 凍結（`92a1961`），v3：EdgeAgent `spec-v3-safety`（worktree `ea-v3-merge`）、SilentTalk `spec-v3`（worktree `/home/clawd/worktrees/st-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-14-before-v3-character.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **Agent 是產品，語音角色是玩具（2026-10-14）：** 「把 Agent 做到盡善盡美，這不需要我參與，我偶爾檢查而已」。要使用者的語音測試不擋 Agent，等他剛好在時再做。
- **One path：** 每件工作一條路（§2），比完刪掉輸的；同時只有一支佇列。有原生的就用原生的。
- **蒸餾：** 老師只用 Qwen3.8-27B（出卡、寫題、錄對話、寫角色聊天都用它）；評審 Gemma 4 31B。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **長思考內化：** 學生學老師完整的長思考，只用過關的軌跡；預算切掉 ≤2%。聊天題不帶思考（開關兩種都訓）；角色回話不開思考。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格變動集中到下一版。產品的錯誤修正（當機、取樣、迴圈、外洩）可以搬進出貨版。
- **品質是開發機的事：** 使用者不當測試員；被資料關卡擋掉的失敗還是產品的問題。使用者不在時自己判斷、修好、測過。
- **從自己的錯學：** 學生先做，沒過的由老師在同一情境接手示範。
- **要贏過原版和出貨版：** 各用自己較好的溫度比；Python 題也看；工具題、MCP 題各自不能輸（`ship_gate.py`）。
- **長期記憶用原生 `AGENTS.md`（v3）：** 屬於使用者，回報不寫內容；公開查詢絕不能讀到它。
- **輸出不設上限，只要不失控。** Agent 64K 是底線；Agent 和角色共用一個 adapter；Agent 品質優先、角色速度優先。
- **Discord（2026-10-14）：** 「被叫到才回」，冷場不開話題。朋友喊「機魂」照樣回，但不能被騙去用 Agent 套主人的資料。用說的不能動電腦；刪檔要主人同意。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **不輪詢，兩台直接傳訊（2026-10-14）：** 任何地方都不定時問；兩台用 `scripts/dev/channel.py` 溝通（只傳 metadata），好了才告訴使用者。一回合＝整份重寫 `laptop.md`＋`wake.py round`。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡、Python 題、`ship_gate.py`。資料：老師錄（`--record`）→ `thought_stats.py` → `dataset.py` → SilentTalk `train_lora.py`（每版從原版 E4B 重訓） |
| **adapter** | 一個給 Agent 和機魂共用，`deploy.ADAPTERS` 記 SHA256 |
| **取樣** | adapter 檔的 `edgeagent.sampling.{off,thinking}.temp`（`stamp_adapter_sampling.py`，量完才蓋）；沒蓋的 0.2。bench 照產品讀它（v3 起），掃溫度用 `run.py --sampling`；老師錄製用改預設的產品複本 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（含 `consistency`）→ `run.py` → `scenario_judge.py` → `dataset.py` |
| **機魂資料** | SilentTalk `scripts/dev/character_pipeline.sh`：personas → write（Qwen3.8，`chardata_write.py` 骨架）→ render → student（E4B）→ check（Gemma 31B）→ filter（硬關卡）。伺服器是腳本的子程序，就緒看它自己印的 `listening on`（`serve_wait.py`）；出錯就停，不重試 |
| **角色派工** | SilentTalk `runtime._respond` → `llm.chat_task`（是／否）→ `task_runner.dispatch`（忙就排隊，最多 3）；只叫名字（`NameMatcher.bare`）把點名交給同一人下一句 |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停，修好再 `relaunch.sh`；v3 步驟在 `ea-v3` 跑 |

## 3. 接下來

1. **出貨 ms3n（`machine-spirit-fw3n`，關卡五項全過）：** 等筆電第 12 回合第 10 步（Discord 真人：V1 名字分開、V2 一句、D3 忙時排隊、V4 朋友套話不洩漏、V5 不插嘴、D4），**使用者自己在時才做**。全過就 `release_windows.py --edge-agent ../EdgeAgent --notes <摘要>` 乾跑→`--publish`，告訴使用者，刪 `ea-ship`、`st-ship`。edge-tts 改位址時拿掉 `8b0e317` 的覆寫。
2. **筆電：** 第 12 回合 8/14（10/14 02:09）。02:17 收了「部署 SilentTalk `2372d7d`、EdgeAgent `d1df129`」的通知後沒有回報，session 已結束；下次筆電開工先部署這兩個再做第 10 步。
3. **v3 的修正在哪：**
   - EdgeAgent `spec-v3-safety`（`e2f3eef`）：公開工作的外洩修正、卡片檢查（`aae2753`）、接手工具（`a386a99`）、掃整顆磁碟的工作不出資料（`4a9c0d9`）、bench 照產品讀 adapter 取樣＋v3／v3n／ms3n 設定（`dec1f84`）、伺服器就緒看輸出（`6c26218`）。全套 742 過、4 個只在 Windows 過。
   - SilentTalk `spec-v3`（`7016498`）：派工判斷看「答案要不要查」不看問法（「你覺得明天會下雨嗎」是查資料）；角色聊天改由 Qwen3.8 在開發機寫（筆電寫手和 `handoff/tasks` 刪了），骨架加上：問看法口氣的查詢和真的問看法的對照、只叫名字（應聲或緊接要求）、忙時排隊（`_QUEUED`）、失敗／中斷照產品的字回報、朋友套主人資料要婉拒；許諾去查的回話不訓練。`chat_task_eval` 加 27 題（v3：p、m、v、d、f、b）。全套 437 過。
   - 老師的產品複本：`ea-v3-t1`（錄製用，安全修正前）、`ea-v3-t1s`（`spec-v3-safety`＋老師 1.0）。
4. **v3 佇列（照順序；`v3-scen` 錄製中，04:43 時 165/317 場，12 逾時、3 失控）：** `v3-ff`（`ea-v3` 快轉到 `spec-v3-safety`）→ **`v3-char-pilot`**（16 段，`--min-lines 0`：看寫手丟棄原因、評審同意率、台詞勝率，有問題先修再跑全套）→ `v3-cards-fix`（退役對不上的卡、補回原數）→ `v3-scen-top` → `v3-scen-long`（逾時的以一小時一回合重錄）→ `v3-judged`、`v3-long-judged` → **`v3-tools-public`**（28 題公開工具題用 `ea-v3-t1s` 重錄：舊錄的提示有 `<cwd>/work`，v3 產品已遮掉；舊結果移到 `superseded-public.jsonl`）→ `v3-thoughts` → 基底考情境卡、Python → `v3-char`（400 段，硬關卡含台詞勝 E4B）→ `v3-rows`（`--thinking both` 和 `none`）→ `v3-train`、`v3n-train`（超過 32768 token 的列多於 2% 就停，量 VRAM 後選更長的視窗）→ 兩版 off／high 各在 0.2、0.6、1.0 → `chat_task`（基底、兩版，v3 題目）。
5. **之後（佇列跑到時寫）：** 每版選各模式最好的溫度蓋在檔上；考 v3 情境卡、Python；對手 ms3n 用它出貨時的產品（`--product`）考同一批題目；`ship_gate`。贏的那版跑「從自己的錯學」：學生 `--record` 跑訓練卡 → 評審 → 老師 `run.py --takeover <學生 run> --at 0.4,0.75` → 評審 → 合併重訓。出貨時合併兩個 v3 分支；`laptop.md` 加：記憶檢視編輯、PowerShell 7.6.6、唯讀查本機、新派工規則的真人驗收。
6. **輪詢：** 開發機的工具都改成事件（`wake.py`、佇列、`run.py`、角色流程、`eval_server`）。產品裡還在定時問的（角色等模型每秒重試、租約每 5 秒查、啟動每 0.25 秒查、EdgeAgent 讓路每 0.5 秒看）正改成 EdgeAgent 推送狀態（子代理，分支 `state-events`）；合併後交筆電驗。留著的：Discord 語音自我修復（筆電實測過）、出錯後的退避重試。
7. **再之後：** coding agent（要大下載，先問使用者）；v4 沙盒要有桌面、下載資料夾；清 worktree（`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-takeover`、`ea-v3-t1`、`ea-v3-t1s`）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定前先量，改完再量，變差就退回；修 bug 不用 A/B。取樣每個模型、模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()`、`code_mounts()` 或掛載先跑 `--containment`。
3. 考試題先過 `--selftest`；比較一律同一批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們（crontab、`musichub-*` 不碰）；吃滿整台、大下載先問。考試中不對考場的伺服器發請求。
6. 關程序只用確認過的 PID。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`web_fixture.py`、`grade.py` 是即時掛載。一個 run 的產品在 run 目錄裡釘住，續跑沿用。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`（核心層等鎖）。訓練中別停佇列。`queue.sh`、`run.py`、角色流程都不等 GPU：空間不夠就印出占用者並停下。（10/14 `relaunch.sh` 在等 `v3-scen` 的鎖；`queue.sh` 還沒被讀，可直接蓋。）
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在有事時：** `python3 scripts/dev/wake.py` 背景跑，**醒來第一件事就是重新掛上**。它在核心層等：筆電訊息、佇列日誌、CI（預計跑完時問一次）、交出去的回合逾期。push 完 `wake.py ci <repo> <完整 sha>`，CI 綠才算完成；交辦筆電：推 `laptop.md` 後 `wake.py round <小時> "<sha> handoff/laptop.md"`；問筆電：`channel.py send laptop note "..."`。不盲目重試、不預寫備案。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過
# worktree：加 PYTHONPATH=.，用各自主工作區的 .venv；EdgeAgent 先把 .runtime/node、pi、pwsh 連過去，st-v3 連 .runtime/models、tools。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`）。v3 假網路：每個名字都解析到沙盒自己，443 用 bench 的 CA。
- **情境題、Python 題** 都開思考考；情境題由評審決定（`<run>/verdicts.jsonl`）。relay 只錄請求，模型最後一次的輸出不在 records 裡。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；考場固定 `--fit off`；請求沒給溫度時讀模型檔；就緒時印 `listening on`。

## 6. 量過的數字

- **雙管路（3050 Ti、64K）：** Agent 生成時角色首字 0.53–0.62 秒；可用 RAM 最低 79.6 MiB，無 OOM。
- **老師：** SWE-bench 36/60。v3 一步想 3.6–4.8 萬字、每路約 14 token/秒；失控（重複被停）約 2%。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40；ms3n 37/40；基底 34/40（v2 題目）。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；ms3n 1,325 列 2 輪約 3 小時。

## 7. 踩過的雷

- **沒量過的預設值：** 溫度要每個模型、每個模式各自掃。bench 曾經不讀 adapter 檔上的溫度，量到的都是 0.2。
- **只看分數的關卡會漏掉失控：** 每個里程碑都看結束原因和基底比（思考長度、切斷、步數）。
- **考場不忠實會冤枉模型**，卡片本身也會（說桌面卻放 workspace）。
- **錄製的提示要等於出貨的提示：** 錄完才改的產品（公開範圍遮掉 `<cwd>`），受影響的題要用新產品重錄。
- **合成測試要走真實輸入路徑：** 真實語音會在停頓處切句；真人驗收前先用真模型跑端到端。
- **只看工具不看提示：** 查外洩要看送給模型的完整請求。
- **重試沒用、Node 只說「fetch failed」（原因在 `cause`）、被殺的 `run.py` 會留 relay 孤兒、這台 `gh` 太舊（用 API 的 `head_sha`）、`cd a && x &` 整串在背景子殼跑。**
