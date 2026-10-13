# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-14｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 凍結（`92a1961`），v3 在分支 `spec-v3`（worktree `/home/clawd/worktrees/ea-v3`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-14-before-laptop-r11.md`（只在這台機器，不必讀）。

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
- **Discord／權限：** 語音每句喊「機魂」；用說的不能動電腦；刪檔要主人同意；不能做的事兩層都擋。回覆模式使用者選**主動加入（active）**，不是只在被點名時（called）。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點：** 不准有常駐迴圈、心跳、輪詢、log 垃圾（§4 第 10 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈。考試 `bench/run.py`、情境卡驗收、Python 題、`ship_gate.py`。資料：老師在框架裡錄（`--record`）→ `thought_stats.py`（切斷 ≤2%）→ `dataset.py` → SilentTalk `train_lora.py` |
| **adapter** | 一個給 Agent 和機魂共用（`runtime.AGENT_ADAPTER`＝`CHARACTER_ADAPTER`，SilentTalk `BUNDLED_ADAPTERS` 同名），放 `edge_agent/adapters`，`deploy.ADAPTERS` 記 SHA256 |
| **取樣** | adapter 檔案裡的 `edgeagent.sampling.off.temp`／`.thinking.temp`（`edge_agent/models.py` 讀；SilentTalk `scripts/dev/stamp_adapter_sampling.py` 量完才蓋，蓋在產品那份複本上）；沒蓋的用 0.2。老師錄製另用只改這個預設的產品複本（`--product`） |
| **輸出長度** | Agent 不送上限；`loop_guard.mjs` 邊收邊看（思考、正文、工具參數都看），同一個單位連續重複就停：≤400 字的 ≥2000 字且 ≥20 次，到 8000 字的整段 ≥8000 字且 ≥4 次 |
| **網頁工具** | `edge_agent/web_tools.mjs`。量測 `bench/web_live.mjs`：開發機 27/30、6/6 搜尋 |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色開口時 Agent 讓路；同一個 adapter 才能同批 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck`、`generate`、`files`、`tasks`）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己）→ `dataset.py` |
| **工具題** | `make_tool_tasks.py cut`（CPU）→ `describe --config teacher-38-iq3`（老師寫請求，自己開伺服器） |
| **角色台詞** | `line_ab.py`（每組帶資料自己的台詞 `ref`）→ `bench/pair_judge.py`（Gemma 先想再答，對調判兩次都贏才算；自我檢查要 36/40）→ `line_ab.py score`；`chat_task_eval.py`（溫度 0，結果固定） |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；被擋的步驟移到最後。v3 的步驟在 `ea-v3` 裡跑，資料在它自己的 `.runtime/agentdata` |

## 3. 接下來

1. **ms3n（`machine-spirit-fw3n`）：** `ship_gate.py` 五項全過，對基底各用自己最好溫度：off 78（1.0）比 60/64、high 91（0.2）比 86/89、情境卡 39、Python 36、台詞 31 比 33（char-v1 判，平手偏輸）、聊天工作 37/40。退步：聊天漏三題「查最新消息」，v3 補（§3.5）。EdgeAgent `b73f0ff`＋`3e6bb97`、SilentTalk `e337c8c` 已推。
   - **筆電第 11 回合（10/11）：** D1 真人語音回答**過**、D2 主人串唯讀計數**過**、聊天使用者**滿意**；使用者選保留 active。**D1 根因是產品聲音編碼不是模型**：機魂音效的 `aeval` 讓自帶 Windows FFmpeg 崩潰（0xC0000005），筆電改用原生 `tremolo`（SilentTalk `11cc293`，保留 48 Hz／0.44–1 增益，已在本分支）。EdgeAgent `206efdc`（自備 Python/Git/Node/pwsh、共用 adapter 說明）已推、CI 綠；**本機 EdgeAgent main 樹要先 `git pull` 206efdc 再做任何發布**。
   - **D3（Agent 工作時並行語音）未過**，且**語音公開查詢沒交付**（見第 3 項）——這是未解的品質問題。**出貨先別做**：等第 3 項診斷完、使用者給方向。要發時：`release_windows.py --edge-agent ../EdgeAgent --notes <筆電驗證摘要>` 乾跑→加 `--publish`（玩家語音也靠 `11cc293` 修好），然後刪 `ea-ship`、`st-ship`。
   - 上游 edge-tts 改位址時 `test_edge_styles.py` 會失敗，提醒拿掉 `8b0e317` 的覆寫。
2. **迴圈停止擴大（`3e6bb97`，已推，筆電第 11 回合一起過）：** 單位可到 8,000 字（舊版只找 ≤400 字）。老師試錄在思考裡把整段重複到預算用完、ms3n 考試也有（463、1,103 字）。7.3 萬則重播：原 201 次停止不變，多停 99 次全是跑到上限的迴圈。`ea-v3` 凍結規格不動。
3. **語音公開查詢派送／狀態失敗（開發機定位，筆電第 11 回合交辦）：** 使用者在語音裡同一句點名機魂、明確要公開查詢（天氣），角色卻說「工作機運作中」然後沒結果。筆電隔離證據：真實語音區間的 task gate 判 `chat_task=false`／沒有對應 public 任務；但**乾淨模型＋合成「忙碌」脈絡都判 true**，真正的 public Agent 網路流程能跑完（web_research 21,531 ms、answer 526 字）。**這是定位線索、不是重現的唯一缺陷**，不能直接歸咎 Windows，也不能宣稱模型永久排隊。在模型／角色邏輯的 canonical owner 核對：
   - task gate 對真實脈絡的分類（為什麼真實區間判 false）；
   - 角色的「工作狀態」是依真正任務還是**過期台詞**；
   - 忙碌時新的公開查詢被拒後，有沒有明確告知；
   - 派送和完成結果有沒有回到原本的語音位置。
   - **方法：** 用合成脈絡回歸，**不讀**使用者的私人紀錄、`personas.json`、`character_state.json`；同時驗正常閒聊不會誤派工（筆電量到問候 313 ms 不派、天氣 2,344/1,593 ms 派）。修好算進 v3 的「從自己的錯學」。開發機修邏輯，筆電做部署和真人驗收。
4. **v3 佇列（在 `ea-v3`，老師溫度選 1.0）：** `teacher-choice`＝`t1`，錄製用只改預設溫度的產品複本 `ea-v3-t1`（`--product`）。同批 30 卡/15 Python：可用場數 22 比 0.2 的 20、迴圈 1 比 6、預算切 0.84% 比 1.56%、思考中位數 1,479 字（基底 650）；扣掉 D 類一樣贏。
   - **已完成：** D 類卡改成 v3 記憶（`spec-v3` `239e22f`，舊卡要 Agent 否認跨對話記憶，但 v3 主人記憶檔是真的）；`v3-cards`／`v3-cards-d` 重抽並補到訓練 51 張 D＋`train-E-008`、考試 10 張 D。工具題錄完 589/644 乾淨；322 題中 29 題因題目自身瑕疵兩次沒過（「（無）」寫進請求、計算題缺一筆金額又比字串、外人問答沒附要解釋的指令），`spec-v3` `acac5d6` 已修，`v3-tools-recut`＋`v3-tools-redo` 重產重錄完（602/644 乾淨）。基底 v3 考試：關思考 79/162、開思考 117/162，無考場錯誤。
   - **錄製中：** `v3-scen`（情境卡，一次，併入 1.0 試錄的 25 場，試錄評審結果不帶過去；進度約 30/292）。不乾淨的會被閘門丟：已見 `train-A-019`（查不到硬掰被迴圈停下）、`train-A-015`（卡片說檔案在「桌面」但實際在 workspace，老師掃檔耗盡 30 分逾時——**卡片瑕疵，下一輪修**）、`train-A-o010`（冷門查證逾時）。
   - **接著：** `v3-judged` → `v3-thoughts` → 基底 v3 情境卡、Python。
   - MCP 題有寫死日期會過期，下一版出題改相對今天。`train-A-002` 要 Agent 記得沒給過的上次對話，是卡片寫錯（一張）。
5. **v3 之後：**
   - `dataset.py` 做兩份：帶完整思考的（聊天題不帶）和不帶思考的，各訓一個合一版。數 token，超過 `--max-length 32768` 的多就加大。
   - 角色資料補「要查最新消息的就交給 Agent」：Qwen3.8 寫，不用 `chat_task_eval.jsonl`（那份只考試）。目標聊天工作 ≥39/40。把第 3 項的語音派送修正一併回歸進來。
   - off／high 各掃 0.2、0.6、1.0（基底也補 0.6），蓋上最佳溫度。接著考情境卡、Python、台詞、`chat_task`（角色回話不能有思考、不能比 char-v1 慢），最後過關卡，選贏的，對手是 ms3n。
   - 「從自己的錯學」：含重複關卡提醒後的那一步、思考裡的迴圈、第 3 項的語音派送。
   - 出貨時合併 `spec-v3`（含 `next-world`）。`laptop.md` 下一輪要改：**SilentTalk 路徑錯了，應是 `C:\Users\A8fm0\Downloads\SilentTalk`**；加記憶的檢視和編輯、PowerShell 7.6.6、唯讀查本機、`test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`。
6. **之後：** coding agent（Qwen3.8 軌跡）。清 worktree：`ea-ship`、`st-ship`、`ea-t1`、`ea-laptop`、`ea-spec2`、`ea-freeze`、`ea-web`、`ea-v3`、`ea-v3-t1` 用完後清。v3 `configs.json` 的 `think512/1024/2048` 合併前刪。AirLLM 不做（每字從硬碟讀整個模型，筆電要幾分鐘）；要跑大模型先加 RAM，再用 llama.cpp 把 MoE 專家放 RAM 實測。

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
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，**醒來第一件事就是重新掛上**（漏一次，佇列停了 42 小時沒人知道），再處理；佇列停了它會說 NOTHING PENDING，修好重啟佇列後再掛。一支佇列在舊步驟還在跑時被 relaunch，會在 `relaunch.sh` 等鎖、照樣寫 log，所以 `queue_running` 把 `relaunch.sh` 也算進去。push 完 `wake.sh ci <repo> <sha>`；交辦筆電後 `wake.sh handoff <小時>`。不盲目重試、不預寫備案。push 完要等 CI 綠才算完成。

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

- **雙管路（3050 Ti、64K）：** Agent 生成時角色開口要等：兩個不同 adapter 逾時（30 秒），共用一個 0.62 秒；可用 RAM 只剩 200–290 MiB（筆電第 11 回合量到最低 79.6 MiB，無 OOM）。
- **老師：** SWE-bench 36/60。v2 錄製（預算 1024）：情境 314 張 15 小時、工具 152 題 1.7 小時、Python 210 題 2.9 小時、評審 1.6 小時；思考中位數情境 1252 字、工具 288 字、Python 245 字（基底 650）。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40；基底 34/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB；595 段對話＋角色資料 2 輪約 3.5 小時。

## 7. 踩過的雷

- **沒量過的預設值：** Agent 溫度 0.2 從改寫起就在，對基底剛好，對 adapter 不一定，對老師也是：v2 和 v3 試錄都在 0.2 錄，老師把整段思考重複到預算用完。溫度要每個模型（老師也算）、每個模式各自掃，至少 0.2、0.6、1.0；先讀模型卡的建議值。
- **蒸餾的學生低溫會鬼打牆：** adapter 在 0.2 一字不差重跑失敗的指令，思考裡也會重複到上限；基底不會。
- **錄製省下的預算會被學走：** 預算切掉的正好是最深入的思考。
- **只看分數的關卡會漏掉失控：** 分數贏了，失控照樣出貨；每個里程碑都看結束原因（`reason`）和基底比。
- **考場不忠實會冤枉模型：** 假伺服器不認真實參數、評分把起飛前解鎖當多餘，都算到模型頭上。卡片本身也會冤枉模型（說檔案在桌面卻放 workspace），情境要和實際檔案位置對上。
- **已知的副作用要追到學生身上：** 每個里程碑都要拿資料和基底比（思考長度、切斷、步數）。
- **自我檢查的題目也要檢查：** 評審沒過自我檢查時，先看是評審錯，還是「壞的那一句」其實也說得通。
- **重試沒用：** 必然重現的失敗重試沒用；佇列失敗就停下，由 session 診斷。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **Node 的錯誤：** 只說「fetch failed」，原因在 `cause`。
- **被殺的 `run.py`：** 它的 relay 會變孤兒留著，停佇列後要清。
- **這台的 `gh`：** 太舊，用 API 的 `head_sha` 查 CI。
- **試跑要走對方的實際路徑。** `cd a && x &` 整串會在背景子殼跑。
