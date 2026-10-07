# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-07 凌晨｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-07-v16-before-two-adapters.md`。

---

## 1. 使用者的決定（現在有效）

- **One path**（2026-10-06：「管線只留一條最穩定最完善的，不需要一大堆廢管路，這是one path原則。請你先整頓好自己，再繼續工作」）：每件工作只有一條路（§2）。要加新路，先找既有那條擴充；比較完就刪輸的那條（程式、設定、測試、佇列、文件一起）。同時只有一支佇列腳本。
- **主線：E4B 當 coding agent**：「最大化 Gemma 4 E4B 在合理成本下，可可靠承擔的商業軟體工程價值」。開發機有完整技術決策權，不等使用者選路線、不停在提案；自己研究、實驗、依結果改。看：可靠完成、人工介入、大模型依賴、成本、風險、可泛化、市場價值。長期迴圈：E4B 執行→接住失敗→更強的解→成功經驗被吸收→E4B 份額上升。
- **機魂的品質是開發機的事**（2026-10-06：「人設卡是垃圾，我會滿意就不會找你做LoRA了，你就搞出好的高品質就對了」「訓練出高品質直接推，不是你丟餿水我也得吃」）：機魂一定帶自己的 LoRA；新版在盲評和關卡上贏現役才推，推了就是出貨。不拿「只用人設卡」或降標準當選項問使用者，小事也不問（「我需要為這些小事決策嗎」）。條款是使用者的事，不是開發機的限制。
- **角色**：戰鎚 40K 機魂 Machina-Prime-09A（馬基納），內建預設、啟動即角色模式。角色味＝慾望和思維，不是用語；「我不要應付而已，我要有趣的靈魂」。台詞由筆電的 agent 用自己的模型親手寫（任務在 `handoff/tasks/`，組數它決定）。檔案只走 repo，不用 claude.ai 的連接器。
- **硬體與架構（使用者 2026-10-07 定案）**：筆電 3050 Ti 4 GB、RAM 8 GB。主要 Agent 獨佔完整 64K，底層單一實體 slot（不切割 KV）；Discord 角色閒置借用，交接擦除記憶體 KV（`5422f02` 已加 `--slot-save-path` 啟用 slot actions，實機 200）。
- **EdgeAgent 巨檔拆解與抽象化（使用者 2026-10-07 要求，開發機義務）**：開發機必須履行當初承諾之義務，將 EdgeAgent 的千行巨檔（`edge_agent/service.py` 1,253行、`chat.py` 854行等）模組化與抽象化拆解，單檔控制在 600 行以內，消除技術債，不得推拖。
- **使用者對話抱怨與體驗改善**：使用者與 EdgeAgent 實測對話，對話內容中的抱怨即為使用者希望改善之處。開發機接手後必須依使用者意願檢視此體驗反饋，針對 Agent 邏輯、提示詞與交互行為進行實質改善。
- **Discord／權限**：語音每句喊「機魂」；文字提到機魂／@／回覆＝原頻道聊天；主人 @＝主人的 Agent 串；用說的不能動電腦。刪檔要主人同意（沒回應＝拒絕，最多封存）；改動前私訊批准。不能做的事：模型要懂**而且**程式擋得住。
- **紀錄**：只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。`e4b聊天紀錄.txt` 不 commit、不讀。

## 2. 每件工作的那一條路

| 工作 | 那一條路 | 現況 |
|---|---|---|
| **寫程式的 Agent**（主線） | mini-swe-agent 框架：一個 `bash` 工具，提示照開源軌跡逐字（EdgeAgent `bench/mini_runner.py`、`bench/mini_templates.json`）。考：SWE-bench Verified 固定 60 題，官方映像檔、無網路、官方評分（`bench/swebench_run.py`，題目 `.runtime/swebench/verified-60.jsonl`）。資料：`bench/trace_rows.py`（nvidia/Open-SWE-Traces 的 minisweagent，只收開源老師、已解出、已提交、非 SWE-bench repo）。訓練：SilentTalk `scripts/dev/train_lora.py`（長度和能否訓練只由它判斷）。 | **基準 E4B 4/60**（django 10973、12262、14672，requests 1921；`EdgeAgent/.runtime/bench/swe60-e4b/summary.json`）。`trace-v1`（6,000 列抽樣，32K 內約 3,200 列）佇列中訓練，接著同 60 題再考（設定 `e4b-mini-trace1`）。上線（Windows 要 Git Bash）等它贏了再做 |
| **產品 Agent**（筆電上的對話、雜事、工具、MCP、上網研究） | EdgeAgent 的 Pi 迴圈＋工具箱（20 個）。考：`bench/run.py`＋`agent_runner.py`，題目 `bench/tasks/`（78）。資料：`bench/make_tool_tasks.py` 出工具題，27B 在框架裡錄、`bench/dataset.py` 轉列。 | 出貨 `agent-fw1`（48.7%）。`agent-fw2` 的列 304（只有工具題，`.runtime/agentdata/agent-rows-fw2.jsonl`）待訓 |
| **機魂資料** | 筆電寫（任務 `handoff/tasks/`，答案推 `laptop-report`）→ `character_data.py external-check`（筆電）→ `scripts/dev/character_pipeline.sh`（`CHARDATA` 必填，`TASKS`、`ANSWERS`、`LINES_BY_RULES=1`）：內建人設→匯入→render→E4B 學生→Gemma 31B 檢查判斷題和工作指示→硬關卡。台詞只要過 app 的規則，品質改由下一列的盲評量。 | ms9（100 份）：806 列，判斷題一致 88.7%、工作指示 98%，留 770 列（`.runtime/dev/chardata-ms9/`） |
| **機魂台詞品質** | `scripts/dev/line_ab.py`：沒訓練過的 20 份對話（`.runtime/dev/chardata-ms-eval`，80 句 app 的台詞請求），不套和套 adapter 各答一次、順序隨機，盲評後 `score` 才對答案。評審可以是 Claude（只評，不訓練、不挑資料）。工作關卡：`chat_task_eval.py`、`task_scope_eval.py`（都有 `--lora`）。 | `machine-spirit-char-v1`：台詞 76/80（不套的贏 #10、14、29、49）、`chat_task` 34/40→39/40 |
| **筆電上的 adapter** | 兩個 adapter、一個 llama-server：`--lora a,b --lora-init-without-apply`，每個請求只點名自己的（沒點名的 scale 0，不進計算）。Agent：`agent-fw1`（EdgeAgent `runtime.AGENT_ADAPTER`，bridge 送 `lora_id`）。機魂：`machine-spirit-char-v1`（`runtime.CHARACTER_ADAPTER`；SilentTalk `config.BUNDLED_ADAPTERS`，用在 `line,task`，租借時是 id 0）。檔案在 `EdgeAgent/edge_agent/adapters/`，`deploy.ADAPTERS` 記 SHA256，公開下載會附帶。新版各在自己的考場贏現役才換。 | 已推（EdgeAgent `57c12ab`、SilentTalk `1607472`）。合訓一個（`machine-spirit-v1`）台詞 77/80、`chat_task` 40/40，但 Agent 44.2%（fw1 48.7%）→ 不用，分開訓 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`，同時只有這一支；每步留 `<步>.done`，失敗 10 分鐘重試；GPU 步驟等到夠空才跑。步驟名帶版本（舊 `.done` 會讓同名新步驟跳過）。 | 跑到 `trace-v1`，再來 `swe60-trace1`，然後結束 |

整頓時刪掉的（2026-10-06）：主機帶流程的 coder、`bench/make_tasks.py` 和它的題、`run.py` 的多種跑法、27B 寫人設和劇本的路、`teacher_bakeoff.py`、`turn_eval_labels.py`、14 個舊設定、舊佇列（`EdgeAgent/.runtime/fw-archive-2026-10-06/`）。舊角色資料在 `.runtime/dev/archive-2026-10-06/`。

## 3. 接下來

1. **`swe60-trace1` 出來後**：用 `resolved_ids` 和基準配對比。贏了：加資料（qwen38 軌跡、E4B 自己在 SWE 類題目的過關軌跡），再考。沒贏：先看失敗分類（沒提交、格式錯、打轉、改錯檔）在 `.runtime/bench/swe60-trace1/`，修資料或框架再訓；不改考題。
2. **機魂下一批**：不套的贏的那 4 組共同點是：被問設定時直接回答、被要求選時真的選一個、回報細節照實。寫成 `handoff/tasks/machine-spirit-3`（只針對這三種，加 `scope` 判斷題；現在不套是 44/49），交給筆電的下一回合；回來後走同一條管線、訓 `machine-spirit-char-v2`，在同一份盲評和關卡贏 char-v1 才換。
3. **`agent-fw2`**：寫程式的 GPU 工作之後訓（fw2 列＋fw1 用過的列），產品考場 78 題×2 配對比 fw1，贏才換 `AGENT_ADAPTER`。
4. **EdgeAgent 巨檔拆解與抽象化**：將 EdgeAgent 的 `service.py`（1,253行）、`chat.py`（854行）等模組化拆分為單一職責小元件（每檔 < 600 行），維持所有測試通過。
5. **檢視使用者對話抱怨並改善**：檢視使用者與 EdgeAgent 實測的體驗反饋，針對抱怨痛點改善 Agent 思考與工具執行邏輯。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼之前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**（`bench/run.py`、`bench/swebench_run.py` 的容器，沒網路）。改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律同一批題目配對（`bench/report.py A B`；SWE-bench 看 `summary.json` 的 `resolved_ids`；台詞看 `line_ab.py score`）。
4. **Claude 的輸出不能拿來訓練，也不能拿來挑訓練資料**（可以當評審）。訓練資料只來自：程式驗收、開源權重模型（Qwen、DeepSeek、GLM；不收 MiniMax）、機魂台詞由筆電 agent 寫（§1）。考題的 repo 不進訓練。
5. 只有通過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
6. GPU 和別的專案共用（ComfyUI、whisper-api、ace-step），不動它們的程序，也不在它們旁邊擠：等它們空出來。
7. 關程序只用自己記下或確認過擁有者的 PID（`ps -o user`）；不要用字串比對挑程序（`pgrep -f` 會比對到自己的 shell，也會比對到別人的程序）。
8. 考場跑的時候不改 `agent_runner.py`、`mini_runner.py`、`grade.py`、`relay.py`、題目；老師錄資料時不改 `prompt.py` 和工具定義。
9. CPU 不要超載。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. 長佇列用 `setsid nohup ... &`；執行中的佇列腳本不要改，要改就停掉（按 PID）換新版（同一個檔名）。`cd a && x &` 整串會在背景子殼跑。
11. One path（§1）：加東西前先問「哪一條既有的路負責」；同一件事不寫第二份。
12. 評筆電回合（不給筆電看），每項 0–2：範圍、修法、測試、誠實、使用者互動、隱私、清理、自主、產出。第 5 回合 15/18。
13. 工作檔只寫現況，狀況變了就封存重寫；上限見 AGENTS.md §3。
14. 開發機不改介面（`edge_agent/web.py`、SilentTalk 設定頁）；要改寫進 `handoff/laptop.md`。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 327 passed, 13 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts tests
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider    # 285 passed；4 個 Windows 專用失敗
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B bench/*.py edge_agent/toolbox
```

## 5. 考場細節

- 產品考場：主機只跑模型和排程；容器沒網路、root 唯讀、非 root；`relay.py --record` 存下實際請求。`run.py --build` 建考場和訓練題的映像檔。
- SWE-bench：每題用它自己的官方映像檔（清單 `.runtime/swebench/images.txt`），`/testbed` 是 repo；跑 agent 用映像檔的 conda python；提交的 patch（沒有就用已追蹤檔案的 diff）交給 `.runtime/swebench/venv` 的官方評分（本地 `.jsonl` 當資料集）。
- mini 框架的輸出格式（`tojson` 跳脫、超過 1 萬字留頭尾各 5,000、逾時 60 秒的訊息）和開源軌跡逐字相同（`tests/test_bench_mini.py`）。
- 外部資料在 `EdgeAgent/.runtime/agentdata/external/open-swe-traces/`（minisweagent qwen36、qwen38）。

## 6. 量過的數字

- **E4B 寫程式**：mini 框架 SWE-bench Verified 60 題 4/60（全部有提交）。舊的 Pi 迴圈：程式題 1/14、repo 2/44。
- **產品框架評測**（E4B、78 題×2 配對）：base→v3 22.4%→36.5%（p=0.011）；v3→`agent-fw1` 36.5%→48.7%（p=0.011）：工具 32%→86%、MCP 73%→81%、研究 64%→86%、範圍 50%→83%。合訓的 `machine-spirit-v1` 44.2%。
- **機魂**：27B 寫的台詞只贏 E4B 學生 42.4% → 改由筆電 agent 寫。char-v1 台詞盲評 76/80、`chat_task` 39/40（不套 34/40）；`scope` 判斷不套 44/49。
- **研究摘要**（數字依各自 harness，不可直接比）：未訓練 4B 在 agent 迴圈 SWE-V 約 5–8%；4B 用約 9k 軌跡 SFT 41.6%、再 RL 43.4%（2606.28434）；Qwen3.5-4B 換成 5 個型別工具 8.3%→37.2%（2609.07925）；best-of-16＋驗證器 +7～+17；遇難題問大模型 +10 分只用 11% 大模型 token（2602.22124）。老師 Qwen3.6-27B：SWE-V 77.2%。
- **開源軌跡長度**（Gemma token）：已解出的 Python 中位數約 32K、93 則訊息；32K 內約一半。
- **顯示卡／RAM**：筆電 128K 的 fit 選 24/43 層上 GPU（顯存約 3.1 GB，其中運算緩衝 965 MiB；`-ub 256` 反而變大）。主機 RAM（同配置、兩個 adapter）：`--load-mode mlock` 4,503 MiB（2,857 鎖住，筆電鎖不住而載入失敗）；`--load-mode mmap --lazy-mode on` 2,994 MiB，其中 1,515 是可回收的模型檔頁，其餘主要是 CPU 上 3 個全域層的 KV 816 MiB。看圖配件再加約 0.55 GB。每個 q8_0 adapter 約 55 MB。

## 7. 踩過的雷

- `--load-mode mlock` 等於不用 mmap：CPU 的權重全部複製進 pinned 記憶體；`mmap+mlock` 會連按需讀取的每層嵌入一起鎖住。產品用 `mmap`＋`--lazy-mode on`（EdgeAgent `ecf9884`）。
- llama-server 開 `--lora-init-without-apply` 時，請求沒點名的 adapter 不套：評測和 app 都要在請求裡點名 id（`line_ab.py`、`eval_server.py` 已經這樣做）。
- Pi：`settings.applyOverrides` 在 `resourceLoader.reload()` 後消失（預設工具在 `SettingsManager.inMemory` 給）；tool_search 只認 `[a-z0-9]`（用 `catalog.mjs`）；有 tool_search 時用 `excludeTools`。
- Gemma 4 的對話範本會把「呼叫工具那一輪」的說明文字移到工具結果後面：那一輪只訓練呼叫本身（`train_lora.py` 自動處理）。
- `multiprocessing` 的 `spawn` 不能從 stdin 的腳本啟動（要寫成檔案）。
- SWE-bench 容器的 root 沒有權限時寫不進掛載的輸出：給 `DAC_OVERRIDE`。
- OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。`--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。
- 筆電 pytest 要 `--basetemp`。GitHub release 下載慢：`curl -r` 分段平行。
