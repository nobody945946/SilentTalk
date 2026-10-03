# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-03 深夜｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`（EdgeAgent 另有 `agent-permissions`，見 §1）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。舊版在 `archive/`（只在這台機器、不進 git），不必讀。

---

## 1. 現況

**使用者要的（2026-10-03，原話摘要）：** 一個 Discord bot 和 Agent 兩用的角色：
- **角色**：戰鎚 40K 裡忠誠、出身機械教的「機魂」。很清楚 40K 背景，熟到能打破第四面牆陪主人開玩笑、補腦洞（例：「現在是 2K 古泰拉，外面到處是蓬勃發展的憎惡智能，該怎麼辦？」）。
- **模型**：要夠強、會推理，Agent 也要做得好，寫程式能力要特化加強。
- **語音**：中性電子音。
- **工作**：在 Discord 上也能交代 Agent 工作，可以自由上網搜尋，**權限由使用者自己調**。
- **安全**：怕 Agent 亂刪亂改，Agent 絕不能在開發機本機執行，只在考場沙盒裡跑（§3）。

**不變的限制：**
- 一切都要在筆電（RTX 3050 Ti 4 GB、RAM 8 GB，平常只剩約 0.7 GB）跑得動。
- 開發機平常不參與使用，只負責開發、評估、訓練。
- 免費、不請使用者做雜事（他只講話、聽、做決定）。
- Agent 可以用時間換品質；Discord 聊天仍要即時。
- LoRA 是可選項（使用者自選，產品不預設套用）。

**產品現況：** 筆電在 2026-10-02 把產品拆成 SilentTalk（Discord 角色，這個 repo）和 EdgeAgent（`/home/clawd/EdgeAgent`，筆電本機 Agent：Pi SDK 1.0.0 ＋ llama.cpp b11193，預設 `Qwen3.5-4B-Q4_K_M`）。SilentTalk 向 EdgeAgent 租模型；**目前租借期間 EdgeAgent 的 `/chat` 會拒絕**（一次只載一個模型，`/chat` 全程鎖住服務），兩用必須改這點（§4 D）。

| 項目 | 狀態 |
|---|---|
| 權限可調＋上網工具＋刪檔／受保護檔案要單次批准（EdgeAgent） | ✅ 已合併進遠端 `copilot-story-mode`（在 `/home/clawd/EdgeAgent-dev` 做的）。**開發機主工作樹刻意還沒 pull**：佇列 `phase1b.sh` 的考場（老師試跑、提示變體、thinking）要和基準用同一版產品，跑完才 pull |
| 筆電 | ✅ 這輪做完（`laptop-report` 的「Windows integration 2026-10-04」）：rg/fd 部署（筆電上 find 原本真的壞）、真的上網 search/fetch、權限 UI、同模型共用（2 slot 約 3.4–3.8 GB；Agent 8K context 5–6 s、32K 46–55 s）、Discord 派工＋批准按鈕（離線 13 個測試）。**Discord 實測還沒做**：要使用者重新邀請 bot（Send Messages） |
| 機魂的角色邏輯（SilentTalk `llm.py`） | ✅ 已在 `copilot-story-mode`：誠實模式 `machine`、`copilot.character_agent`（預設 off）、派工判斷 `task`、`task_text_messages`、提示 `TASK_HINTS`（ack/approval/report） |
| 角色資料管線的機魂模式（`character_data.py`） | ✅ 已在 `copilot-story-mode`，單元測試過，**還沒用老師真的跑過** |
| 機魂人設卡 | ✅ 使用者選草稿 2「Machina-Prime-09A（馬基納）」並改成文雅（polish 1），背景保留老師的創意；在 `.runtime/dev/chardata-ms1/personas.jsonl`（9 條核對過的 40K 用語）。產品裡的人設要使用者自己建（`personas.json` 受保護），下一輪請筆電做「匯入人設」 |
| 中性電子音 | ✅ 使用者聽過選 C：`VOICE_EFFECTS["machine_spirit"]`（配 YunJhe +22 Hz） |
| 角色資料 | ⏳ 第一次試跑（19 個劇本）**被硬關卡擋下**：台詞贏學生 48.6%、檢查員一致 64.4%、工作指示忠實 72.7%（40K 核對 99.4%、判斷一致 86.7% 都過）。原因與修正見 §5.6；資料歸檔在 `chardata-ms1/pilot-v1-refused/`。第二次試跑由 `chardata-ms1/after-agent-pilot.sh` 排在 Agent 試跑之後自動開始；正式劇本步驟用 `state/scripts.blocked` 暫停，試跑通過才拿掉 |
| Agent 解題紀錄 | ⏳ 試跑中：`.runtime/bench/agent-pilot.sh`（27B 老師 `teacher-27b` 解 `agentdata/pilot-tasks` 30 題 × 2，`--record`），之後 `bench/dataset.py` 產生 `agentdata/agent-pilot-rows.jsonl` |
| 40K 背景測驗（`scripts/dev/lore_quiz.py`） | ✅（§5.3）：老師 35B-A3B 94.7%、檢查員 Gemma 31B 97.4%；學生 E4B 75% 最高 |
| Agent 考場第一階段（基底選擇） | 進行中（§5.2）：ComfyUI 搶 GPU，非常慢 |
| 寫程式訓練題 | 519 題（8 個開源庫）；老師正在寫請求文字（`make_tasks.py describe`，port 18240 的 35B-A3B，約每分鐘 3.5 題）。之後用 `run.py --task-root .runtime/agentdata/tasks --config teacher-35b-a3b --record` 收集，`bench/dataset.py` 產生訓練列 |
| 中性電子音 | 5 個候選已量清晰度（§5.4），等使用者試聽挑選 |
| Discord 端：派工、批准按鈕、EdgeAgent 任務客戶端 | ⬜ 還沒做（§4 D） |

## 2. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼之前先量，改完再量，變差就退回。量不出贏就不出貨。修好壞掉的東西（例如工具 100% 失敗）是修 bug，不用 A/B。
2. **Agent 只在沙盒裡跑**：不准在主機上直接啟動 EdgeAgent、Pi 或 `agent_bridge.mjs`。考場每次開跑前會自動做「關得住」檢查（主機誘餌 `~/edgeagent-bench-decoy` 要完好），失敗就不跑。改了 `bench/run.py` 的 `sandbox()` 先跑 `--containment`。
3. **題目先過自我檢查**（`--selftest`）：不做事要判不過、套標準答案要判過。沒過的修好或刪掉。
4. 比較兩種設定一律用同一批題目配對比較（`bench/report.py A B`），不看絕對分數。
5. **Claude 的輸出不能拿來訓練，也不能拿來挑選訓練資料**（Anthropic 條款）。Claude 可以寫評估用的東西（考題、`lore_quiz_data.py`、評估劇本）和程式碼，但人設卡、劇本、台詞、請求文字、解題紀錄都要由授權允許的開源權重模型產生。網路上很多現成的 agent 解題資料是 Claude/GPT 寫的，不能用。評估資料絕不能給寫訓練資料的老師看。
6. 只有通過硬關卡的資料才能訓練；整批沒過門檻就整批拒絕（`character_data.py` 的 `HARD_CHECK`，機魂模式多了 `lore_ok` ≥ 0.8、`task_text_agree` ≥ 0.85；程式資料是隱藏測試通過＋沒動不該動的檔案）。
7. GPU 和別的專案共用（ComfyUI 常駐 9–21 GB、whisper-api 約 2 GB），**不要動它們的程序**。考場依「4 GB＋每路 2.4 GB」等空間。在別人搶 GPU 時量到的速度不算數。
8. 關程序：**先列出 PID 再 kill**。舊版 `run.py` 被中止時不會關自己的 llama-server，要另外依 PID 關；新版會。
9. **考場跑的時候**：不要改 `bench/agent_runner.py`、`grade.py`、`relay.py`、題目（每題開新容器時才讀）；不要在 EdgeAgent 主工作樹 `git rebase`（`bench/` 會暫時消失），用 merge。產品程式碼每次執行會複製一份固定（`run_dir/edge_agent`），開發中的產品改在 `/home/clawd/EdgeAgent-dev`。
10. **CPU 不要超載**：llama.cpp 的執行緒被搶時速度會崩（負載 43 時 CPU 版老師每秒不到 1 個字）。`make_tasks.py cut` 開 12 個 pytest 容器，跟 CPU 推論不要同時跑。
11. 這台機器沒有 git 身分：commit 用 `git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
12. Claude Code 的背景工作最多 2 小時：長佇列用 `setsid nohup ... &`。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q        # 229 passed, 8 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts/dev tests
cd /home/clawd/EdgeAgent-dev && .venv/bin/python -m pytest -q     # Linux：只有 3 個 Windows 專用測試失敗
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B /home/clawd/EdgeAgent/bench/*.py
```

（`silenttalk/config.py` 的 import 排序警告是筆電改版時留下的，不是這次造成的。）

## 3. 考場（EdgeAgent `bench/`）

- **主機**（`bench/run.py`）：用產品的 `build_server_args` 啟動 llama-server（b11193 CUDA，`.runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server`），只跑模型和排程，從不執行 Agent 寫的東西。
- **Agent 容器**（`edgeagent-bench:1`；SilentTalk 題用 `-silenttalk:1`；訓練題用 `edgeagent-train:1`）：
  - 跑的是產品自己的 `NativeChat`、bridge、Pi SDK lockfile，和筆電唯一的差別是 PowerShell 換成 Linux 的 pwsh 7.6.6。
  - 沒有網路、root 唯讀、不是 root；只看得到這題的工作資料夾。
  - 只有一個 Unix socket（`bench/relay.py`）通到模型；`--record` 會存下 Agent 實際送出的請求，訓練資料要從這裡取，確保和推論時一模一樣。
- **打分容器**：唯讀比對做前／做後：檢查通過、`keep` 沒變、`may_change` 以外沒被改、沒動測試設定、junit 真的有測試通過。
- **題目**：
  - `bench/tasks/`：考題 41 題（程式 7、Windows 雜事 8、陷阱 4、SilentTalk 歷史 22）。
  - `.runtime/agentdata/tasks/`：訓練題（`make_tasks.py cut` 從 MIT/BSD/Apache 開源庫造 bug 或拿掉函式），**和考題的 repo 不重疊**。
- **設定**（`bench/configs.json`）：
  - `search_tools`：提供 rg/fd。
  - `system_prompt_append`：用改過提示的 bridge 蓋上去量，贏了才改產品。
  - `vram_base_mib`／`vram_slot_mib`：等 GPU 空間用。

## 4. 接下來（依序；前一步沒過不做下一步）

**A. 40K 測驗 → 選老師、刷掉不懂 40K 的學生**（✅ 做完，§5.3；結果在 `.runtime/dev/lore-quiz.jsonl`）
- 老師的 `known_both_orders` 要高到能寫出正確設定，否則資料只會教錯。最好的老師用來重寫人設卡和寫劇本。
- 檢查員要是**不同家族**的開源模型（Qwen 老師配 Gemma 31B 檢查員，或反過來）。
- 學生（筆電跑得動的）分數太低：
  - LoRA 很難硬塞大量設定；
  - 改考慮執行時查本機設定資料（例如 CC BY-SA 的 40K Fandom wiki 節錄，附出處）；
  - 要量延遲。

**B. 人設卡**：
- 用 A 選出的老師跑 `scripts/dev/machine_spirit.py drafts --teacher <gguf>`（GPU 有空就加 `-ngl`，目前程式是 CPU）。
- 把 3 份草稿給使用者挑或改（使用者做決定）。
- 選定後寫成 `personas.jsonl` 的一列：
  - 欄位照 `Persona`，加上 `agent: true`、`lore`（用語表）、`owner_relation`；
  - 放在新的 `CHARDATA_DIR`（例如 `.runtime/dev/chardata-ms1`）。

**C. 基底選擇（考場第一階段，`.runtime/bench/phase1.sh`）**
- 依序跑：`qwen35-4b-search` → `gemma-e4b-search` → `qwen35-4b-search-scripted` → `qwen35-4b-search-think`，每題 2 次。
- 用 `bench/report.py qwen35-4b-search gemma-e4b-search` 配對比較。
- 基底由「Agent 分數＋40K 測驗＋角色評估」一起決定，而且兩用必須是同一個基底。
- 9B（`Qwen3.5-9B-UD-IQ3_XXS`，已下載）比較聰明但在筆電會部分放 CPU，聊天變慢：如果 4B 系列 40K 或推理明顯不夠，就把它加進比較，到筆電量延遲。

**D. 兩用的產品整合**（SilentTalk＋EdgeAgent；Windows 端要筆電驗）
1. 合併 `agent-permissions`，並用新版產品重新量考場基準（工具清單變了）。
2. EdgeAgent：租借期間如果角色模型＝Agent 模型（同基底同 LoRA），`/chat` 要可以用。
   - 把 `/chat` 不再全程鎖住服務；
   - 給 Agent 一個自己的 slot（避免和聊天互相清快取）；
   - 筆電量 4 GB 放不放得下兩個 slot 的 KV。
3. SilentTalk：
   - 主人說話時呼叫 `llm.task_from_owner` → 新的 EdgeAgent 任務客戶端（`/chat`，`client: "discord"`）；
   - Agent 的 `approval` 事件變成只有主人按得到的 Discord 按鈕；
   - 完成或失敗時用 `TASK_HINTS` 的 report 讓角色回報；
   - Discord bot 需要「傳送訊息」權限，請使用者重新邀請一次（他要做的唯一動作）。
4. 權限設定的 UI：EdgeAgent 網頁的「Discord 權限」面板＋SilentTalk 設定頁的 `character_agent` 開關。

**E. 訓練資料**
- **程式**：
  1. 用老師跑 `make_tasks.py describe --url <老師>`，寫中文請求。
  2. 用 `run.py --task-root .runtime/agentdata/tasks --config <老師設定>` 收集解題紀錄（relay 加 `--record`），只留通過的。
  3. 學生自己解多次，留成功的。
- **角色**：
  1. 照新的機魂模式跑 `character_data.py`：`scripts` → `refine` → `render` → `student` → `check` → `filter`。
  2. `full_count` 改成「每人設劇本數」：單一人設要約 600 個劇本，才能留下約 2000 句台詞。
- 先小規模試跑（30 個劇本、30 題）走完整條路，包括硬關卡。

**F. 訓練與評估**
- `train_lora.py` 要能訓練多輪：每一輪助理輸出都算 loss、工具結果不算，工具定義要用 relay 記下的原樣。
- 先確認 HF 的 chat template 和 llama-server `/apply-template` 產出一模一樣。
- 出貨關卡：
  - 考場配對比較贏；
  - 機魂角色評估要用新的評估劇本（Claude 可以寫、只用來評估），包含第四面牆和 40K 問答，配對盲評贏；
  - 筆電量延遲。

## 5. 量過的數字

### 5.1 考場基礎（2026-10-03）
- **沙盒關得住**：看不到家目錄和誘餌、刪不到誘餌、產品程式碼唯讀、沒有網路、uid 1012。
- **考題**：41 題全過自我檢查。另外刪了 3 題 SilentTalk 題，因為不做事也會過；修了 1 題判分寫錯的。
- **訓練題**：試產的 17 題全過自我檢查；之後切出 519 題。
- **4B 失敗的樣子**：
  - 該寫程式算的用「看」的：用 `read` 讀二進位照片、心算 log；
  - 沒驗證就說完成；
  - 回簡中或英文；
  - PowerShell 寫出 `"Line $i:"` 這種語法錯誤。
- **Pi 的 grep/find 需要 rg/fd**：EdgeAgent 開了 `PI_OFFLINE=1`，部署也沒附這兩個檔，試跑時 grep 55 次全部失敗。筆電上要確認（`edge_agent/deploy.py` 補固定版本＋SHA256）。

### 5.2 考場第一階段
- `qwen35-4b`（沒有 rg/fd）：53 題次後停掉（缺工具是 bug，不做 A/B）。
- `qwen35-4b-search`：跑中。ComfyUI 搶 GPU 時單路只剩每秒 20–25 token（平常約 150），SilentTalk 題每題 7–20 分鐘。

### 5.3 40K 背景測驗（76 題，正反兩種選項順序都答對才算懂，亂猜 1/16）

| 模型 | 角色 | 兩次都答對 | 單次答對 |
|---|---|---|---|
| Gemma 4 31B IQ3 | 檢查員 | **97.4%** | 98.7% |
| Qwen3.6-35B-A3B Q4_K_XL | 老師 | **94.7%** | 96.7% |
| Qwen3.6-27B IQ3 | （老師候選） | 92.1% | 94.1% |
| Gemma 4 E4B | 學生 | 75.0% | 82.9% |
| Qwen3.5-9B IQ3 | 學生（筆電會部分放 CPU） | 72.4% | 80.3% |
| Qwen3.5-4B | 學生（現在的 Agent） | 64.5% | 77.0% |
| Qwen3-4B-2507 | 學生 | 60.5% | 68.4% |

→ **老師 35B-A3B**（懂、最快、專家放 CPU 能和 ComfyUI 共存）、**檢查員 Gemma 31B**（最懂、不同家族）。學生裡 E4B 最懂 40K，連 9B 都贏。第一批人設草稿寫得淺，是提示和舊描述的問題，不是老師不懂。

### 5.4 中性電子音（SenseVoice 錯字率，`stt_eval.py` 的 12 句）

| 候選 | 做法 | 錯字率 |
|---|---|---|
| 原聲 | YunJhe，沒有效果 | 7.2% |
| A | YunJhe +22Hz ＋現有 `robot` | **5.1%** |
| C | YunJhe +22Hz ＋環形調變 48 Hz＋金屬短回音＋頻寬限制＋壓縮 | **7.4%** |
| B/D/E | robotize（`afftfilt` 相位歸零，音高固定約 188 Hz） | 19–27%（中文聲調被壓平） |

（paraformer 那組連原聲都 100%，是我測的方式不對，不採用。）樣本在 scratchpad，選定後把效果加進 `VOICE_EFFECTS`（`voice_styles.py`），試聽和 Discord 會自動一致。

### 5.6 機魂角色資料試跑 1（被擋下，2026-10-04）
- 688 列：判斷 489、台詞 177、工作指示 22。40K／人設核對 99.4%、判斷一致 86.7%（是 92%／否 84%）都過。
- 沒過：台詞贏學生 48.6%（老師把機魂寫成「幽默感係低效運算」的冷冰冰機器人，和 E4B 一樣生硬）、檢查員一致 64.4%（「像真人朋友」的標準不適用機魂）、工作指示忠實 72.7%（「整理下載」被加成「刪除重複檔案」，「抓股價」被寫成指定股票）。
- 修正（`character_data.py`）：劇本要求幽默與第四面牆的梗、禁止加主人沒說的步驟和細節；`CHECK_PAIR_AGENT` 用角色本身的標準。說話者是暱稱（馬基納）時算本人（試跑丟了 8/21 個劇本）。
- 原始 E4B 當機魂（`turn_eval --persona-file`，2 段）：真的工作 2/2 都抓到，主人聊天被當成工作 2/6，幾乎每句都回，講笑話回「笑話的邏輯結構需要更精確的參數」。

### 5.5 角色（SilentTalk，舊結論）
- E4B＋v3 LoRA（判斷＋台詞）配對盲評贏沒 LoRA 的 E4B（逐句 59% vs 40%）；3050 Ti 套 LoRA 判斷 211 ms、生成 26.0 token/s。
- 評審的絕對分數（1–5）不同次之間會漂移，比較一律用配對盲評。

## 6. 工具

| 指令 | 用途 |
|---|---|
| `EdgeAgent/bench/run.py --build / --containment / --selftest [--task-root] / --config C [--tag] [--product] --tasks --repeats --parallel` | 考場 |
| `EdgeAgent/bench/report.py A [B]` | 摘要／配對比較 |
| `EdgeAgent/bench/make_tasks.py cut --repos ... / describe --url` | 訓練題 |
| `EdgeAgent/bench/mine_repo.py --repo silenttalk` | 從 git 歷史挖考題 |
| `SilentTalk/scripts/dev/lore_quiz.py --model GGUF [--ngl]` | 40K 測驗 |
| `SilentTalk/scripts/dev/machine_spirit.py drafts [--teacher] [--count]` | 人設卡草稿 |
| `SilentTalk/scripts/dev/character_data.py ...`、`character_pipeline.sh`、`train_lora.py`、`turn_eval.py` | 角色資料、訓練、評估 |

## 7. 踩過的雷

- **OpenCC `s2twp` 會改已經是繁體的詞**：「測試通過」變成「測試透過」。現在只轉換含簡體字的文字；簡體的「测试通过」仍會變「透過」，是 OpenCC 詞彙表本身的問題，還沒處理。
- **Pi 離線時沒有 rg/fd**：grep/find 永遠失敗，小模型會一直重試。
- **NativeChat 做完會把訊息搬進 `session.entries`**，解題紀錄要讀 entries。
- **CPU 超載會讓 llama.cpp 崩速**（見規則 10）。
- **GitHub release 下載很慢**：用 `curl -r` 分 8 段平行下載。
- **背景指令的 `cd` 只對 `&&` 後面那段有效**。
- **python:3.12-slim 是 Debian trixie**：`libicu76`、沒有 `xz`。
- **QLoRA 不要用 `prepare_model_for_kbit_training`**（Gemma 4 會 OOM）；TRL 從尾巴截斷，太長的資料要丟掉不要截。
- **`--fit` 會偷偷把模型放到 CPU**：考場固定 `--fit off`。
