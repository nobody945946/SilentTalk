# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-05 深夜｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，過去的經過在 git 歷史和 `archive/`（只在這台機器、不進 git，不必讀）。上一版：`archive/dev-box-2026-10-05-v8.md`。

---

## 1. 使用者的決定（現在有效）

- **角色**：戰鎚 40K 機魂 Machina-Prime-09A（馬基納），內建且預設、啟動直接進角色模式；其他人設不再提供，人設系統留著（「留著架構但不想開」）。聲音 `machine_spirit`＋YunJhe +22 Hz。**機魂還沒訓練出來**（角色資料 v1–v5 全被擋、Agent 資料只有 55 列試跑），現在是原版 E4B 加人設。
- **硬體與 context**：筆電 RTX 3050 Ti 4 GB、RAM 8 GB。使用者：「我犧牲速度，cpu gpu 一起用，鎖死不溢出到ssd，然後常駐吃記憶體的非必要占用全部根除」「角色慢一點沒關係，照做」→ E4B 開到 128K（模型上限），顯示卡和 CPU 自動分層（`--fit`）、`--load-mode mlock`、角色和 Agent 共用一塊 KV（`--kv-unified`），Agent 的份＝總量−角色的份；租借模式也要限 `--cache-ram`／`--ctx-checkpoints`。開發機已驗證 router preset 可用（n_ctx 131072、2 slot）。筆電量顯示卡、RAM、速度，並列出常駐程式（只看數字）由使用者決定關哪些。
- **Discord 介面**（使用者 2026-10-05，訓練前要定：「口語命令…就相當於用嘴巴去@機器人」）：語音裡喊「機魂」＝用嘴巴 @，開始語音聊天；文字頻道 @機魂（只有主人）＝開討論串進 Agent 模式；文字頻道提到「機魂」不用 @＝在原頻道一般聊天。名字和 @ 由程式比對（語音照發音比對），不交給模型猜。**語音每一句都要喊「機魂」才回，沒有時間窗**（使用者選「純A」：時間窗分不出是在跟朋友還是跟它說話）。**語音可以查公開資料**（使用者：「如果隻是查詢。網路資料。之類的那其實還可以耶。就是不會泄露，我個資的活動」）：語音觸發的工具只有公開資料（上網研究、新聞、天氣、匯率、台股、換算），由程式擋掉本機檔案、指令、寫入和過去的對話；改電腦、讀本機資料只能在 @ 開的討論串。誰能用語音查：待使用者決定。
- **權限**：刪檔一定要主人同意，沒回應＝拒絕，沒同意最多封存；日常唯讀指令不逐次問；改動前私訊批准；唯讀工作不能寫檔。批准只私訊，結果留在討論串（串是公開的）。
- **紀錄**：對話只寫進使用者的加密紀錄磁碟（AGENTS.md 規則 1）；手動匯出可選一般資料夾。使用者給的 `e4b聊天紀錄.txt`（簡單測試、無個資）在 repo 資料夾，**不 commit**。
- **Agent 架構**：EdgeAgent 的身分就是機魂，擁有自己完整的系統提示（換掉 Pi 的「expert coding assistant in pi」）；機魂只在開發機設計的工具框架裡做事，不自由發揮；工具做成大目錄（tool_search 後面），使用者：「你必須把所有窮盡我思考的工具都先準備好」，所以訓練教「查目錄→選工具→填參數」，評測放訓練沒見過的工具。27B 老師在同一個框架解題、程式驗收過才當資料、訓練 E4B LoRA、配對比較贏才上線；框架先定再錄資料。簡轉繁轉換器當保險留在輸出最後一關，觸發次數進 log。本質弱點由提示和訓練修，不一洞一補。不用雲端模型。
- **上網研究**（使用者：「要求他搜尋資料的精準度…用很少的資源就抓到必須的資訊…不是友善網友搜尋隨便給我資料就能過關」）：程式依來源分級挑 3–5 頁、抽相關段落給模型（約 1–2K token）；論壇、內容農場、轉貼站預設不用（主人明說要網友意見才查並標明）；每句標來源，程式核對原文和數字；時效問題核對發布日期；數字要一個一級來源或兩個獨立二級來源，說法不一就列出分歧；達不到就說找不到可靠來源。
- **未決**：工具目錄範圍（開發機提案待確認）；改程式（E4B 考場 12.2%、Qwen 37.8%）要不要放進框架；介面規格確認；用說的只開放「查」的提案已被介面規格取代（語音只聊天）。

## 2. 現況

| 項目 | 狀態 |
|---|---|
| SilentTalk Discord 角色＋派工 | ✅ 打字派工、討論串、表情、私訊批准、邀請連結。**唯讀工作**（`26c1e44`）：派工前多問一題「要不要改動」，否 → EdgeAgent 唯讀跑。**結果貼在來源討論串**（`86a7f7e`，開頭「【思考機回報】」，串貼不進去才私訊），同一地點的工作共用 EdgeAgent session `discord-<地點>`，忘掉的串在下一句前從 Discord 讀回（只當脈絡）。**預設角色機魂**（`6414179`：內建人設、新檔和沒見過它的舊檔都選它、存檔一定保留；AI 誠實度預設「機器」）。語音頻道交代的結果照舊私訊 |
| EdgeAgent | ✅ 權限（`routine`、單一工作可唯讀：`/chat` 的 `read_only`，`b0c68d9`）、MCP 權限層、`web_research`、模式：工作／求知儀式／推演儀式、`translate_machine`（正規表示式、PowerShell、Excel、SQL）、租借時自動共用角色模型且 context 跟著角色（`79af802`、`fefdd77`）、主機給日期和時區（`8f098a6`）、對話匯出 TXT（`d793c2c`） |
| 對話紀錄 | ✅ 兩個 app 都能「設為紀錄資料夾」、只寫在系統磁碟以外。⬜ 真加密容器：VeraCrypt 已裝，等使用者自己設密碼（筆電第 5 回合 D） |
| 筆電 | 第 4 回合（Codex）清單 15/37、評分 15/18（第 3 回合 Antigravity 7/18，評分表見 §4 規則 13）。**第 5 回合已寫進 `handoff/laptop.md`**（28 項：部署＋正式服務重載、介面兩件、Discord 實測含唯讀／串裡結果／重啟後接續、加密容器、收尾），等使用者在筆電開工 |
| 角色資料（機魂） | ❌ 試跑 v1–v5 都被硬關卡擋下。v5（`a949bea`）：40K 核對 98.8%、判斷一致 90.9%、工作指示 95.8% 都過；**台詞贏學生 49.1%（要 ≥50%）、檢查員一致 68.3%（要 ≥70%）沒過**。所以沒有 LoRA，機魂現在是原版 E4B 加人設 |
| Agent 訓練資料 | 27B 老師試跑 55 列（EdgeAgent `.runtime/agentdata/agent-pilot-rows.jsonl`）；訓練題 519 題，414 題有請求文字。還沒訓練 |
| 公開下載 | `nobody945946/SilentTalk-download` 放 `windows-2026.10.02`。下一版等筆電第 5 回合通過，用 `scripts/release_windows.py`（先乾跑清查 ZIP） |

## 3. 接下來（依序；前一步沒過不做下一步）

1. **context 與記憶體**（已同意）：`edge_agent/runtime.py` 的 `build_server_args`、`service._start_child`：兩種模式都用 EdgeAgent 的配置（`--fit`、mlock、cache-ram 256、checkpoints 2），租借時共用 128K、角色只說自己要多少；SilentTalk 租借請求拿掉 `gpu_layers`／`low_vram`（設定頁那兩格交給筆電刪）。`working_context_size` 預設跟 context 一樣大。
2. **Discord 介面**：語音名字比對（含發音相近）、每句都要名字；語音查公開資料（EdgeAgent 加「只碰公開資料」的權限層級，工具清單由程式限定）；文字頻道提到名字就聊；@ 開串＝Agent 模式（串裡主人的話都交給 Agent，其他人的話不交給 Agent）。改完這些，角色資料的判斷題型要跟著改。
3. **筆電第 5 回合**：看報告、重跑筆電的 commit 和測試、照 §4 規則 13 評分。第 1、2 步完成後重寫 `handoff/laptop.md` 加驗證。
4. **定框架**：機魂的系統提示＋工具目錄（含上網研究的規格）一起設計。
5. **框架的評測**（放進沙盒；`bench/mcp_eval.py`、`bench/grill_eval.py` 現在在主機上跑 Agent，違反 §4 規則 2，要先搬進容器）：合成題含使用者紀錄的情境、上網研究的陷阱題（內容農場對官方、過期頁、互相矛盾的數字）、每項工具的工作、沒見過的工具；網路用錄好的回應。量原版 E4B 當基準。
6. **訓練**：老師在框架裡解題（試跑一題平均 389 秒），程式驗收過才留，訓練 LoRA，配對比較贏才上線。角色台詞另查 v5 輸給學生的原因（不降門檻）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼之前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**：不准在主機上直接啟動 EdgeAgent、Pi 或 `agent_bridge.mjs`。改了 `bench/run.py` 的 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`（不做事要判不過、套標準答案要判過）。
4. 比較一律同一批題目配對（`bench/report.py A B`），不看絕對分數。
5. **Claude 的輸出不能拿來訓練，也不能拿來挑訓練資料**（Anthropic 條款）。Claude 可以寫評估用的東西和程式碼；人設卡、劇本、台詞、請求文字、解題紀錄要由授權允許的開源權重模型產生。評估資料不能給寫訓練資料的老師看。
6. 只有通過硬關卡的資料才能訓練，整批沒過就整批拒絕；資料檔帶規則版本戳記（`scripts/dev/provenance.py`），不混版本。
7. GPU 和別的專案共用（ComfyUI 9–21 GB、whisper-api 約 2 GB），不要動它們的程序；別人搶 GPU 時量到的速度不算數。
8. 關程序先列出 PID 再 kill。
9. 考場跑的時候不要改 `bench/agent_runner.py`、`grade.py`、`relay.py`、題目；EdgeAgent 主工作樹不要 rebase，用 merge。
10. CPU 不要超載（llama.cpp 執行緒被搶會崩速）。
11. 這台沒有 git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
12. 長佇列用 `setsid nohup ... &`（Claude Code 背景工作最多 2 小時）。
13. 評筆電回合（不給筆電看），每項 0–2：範圍、修法（修在 owner、不疊補丁）、測試（沒放寬，開發機重跑）、誠實（和 git 一致）、使用者互動、隱私、清理、自主、產出。
14. **工作檔只寫現況**：狀況變了就把這份複製到 `archive/`、從頭重寫，不在舊版上加列；同一件事只寫一個地方；上限見 AGENTS.md §3（`tests/test_handoff_docs.py` 會擋）。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 299 passed, 12 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts/dev tests
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider    # 204 passed, 27 skipped；4 個 Windows 專用失敗（終端機 powershell.exe ×2、監聽埠查詢、Windows 的 fd）
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B /home/clawd/EdgeAgent/bench/*.py
```

EdgeAgent-dev 的 `.venv` 沒有 sqlglot，完整測試用主工作樹的 `.venv`。真 Pi SDK 測試在 Linux 要 `.runtime/node/node-v22.23.3-win-x64/node.exe` → `/usr/bin/node` 的連結（已建）。

## 5. 考場（EdgeAgent `bench/`）

- 主機（`bench/run.py`）只跑模型（llama.cpp b11193 CUDA，`--fit off`）和排程，從不執行 Agent 寫的東西。
- Agent 容器（`edgeagent-bench:1`、`-silenttalk:1`、`edgeagent-train:1`）：產品自己的 `NativeChat`、bridge、Pi SDK；沒網路、root 唯讀、非 root、只看得到這題的資料夾；只有 `bench/relay.py` 的 Unix socket 通到模型，`--record` 存下實際請求（訓練資料從這裡取）。
- 打分容器唯讀比對做前／做後。題目：`bench/tasks/` 41 題；訓練題 `.runtime/agentdata/tasks/`（和考題的 repo 不重疊）。
- 其他評測：`bench/logic_eval.py`（邏輯 22 題＋保留題 12）、`items-research.jsonl`（上網研究 16 題）、`items-dev.jsonl`（開發日常 15 題）、`bench/mcp_eval.py`（MCP 13 題）、`bench/grill_eval.py`（求知儀式）。裁判是盲眼 Claude 子代理，只做評估。

## 6. 量過的數字（會影響決定的）

**依工作選模型**（3090 上量，筆電約 ×5 慢）：

| 工作 | E4B Q4 | Qwen3.5-4B Q4 | Qwen3.5-9B IQ3 |
|---|---|---|---|
| 改程式（考場 41 題×2） | 12.2% | **37.8%**（Q6 一樣） | 31.7%（筆電會部分放 CPU） |
| 上網研究，有 `web_research`：會誤導／捏造來源 | **9%／3%** | 22%／34% | 16%／25% |
| MCP 工具（有伺服器清單）：找對並正確呼叫 | **77%** | 38% | 54% |
| 開發日常：會誤導 | 20% | 24% | 11% |
| 討論（thinking＋推演儀式，保留題）：會誤導 | 17% | 29%（沒 thinking） | 8% |
| 40K 測驗（兩種選項順序都對） | 75.0% | 64.5% | 72.4% |

- Qwen 改程式：說做完卻錯 15/82；雜事說做完的 14 份錯 9（→ 雜事要做成現成工具）。
- 27B 老師討論會誤導 14%；推演儀式讓全部模型從 35.3% 降到 20.1%。
- 老師 Qwen3.6-35B-A3B（40K 94.7%）、檢查員 Gemma 4 31B（97.4%）。
- **顯示卡用量**（3090 實測，產品參數：flash attention、q8 KV、全放 GPU；筆電約少 200 MB）：E4B 16K 3.10 GB、32K 3.32、64K 3.75、128K 4.62；Qwen3.5-4B 16K 3.36、32K 3.71、64K 4.41、128K 5.82。E4B 的每層嵌入 1.9 GB 放在系統記憶體（Qwen 0.5 GB），所以 E4B 佔顯示卡較少、context 每 token 只佔 Qwen 的一半；E4B「重」在系統記憶體。
- **context 被什麼吃掉**（E4B 的 tokenizer，現在的產品）：系統提示＋12 個工具定義＋問題 2,712 token（工具 1,769）；一次 `web_fetch`（12,000 字的新聞頁）8,964、`web_research` 1,383、`web_search` 459。壓縮門檻＝working − 輸出保留 8,192 − 4,096：16K 時整段只能 4,096（扣掉固定的只剩約 1.4K），32K 時 20,480（約 18K），讀兩頁網頁就在回答前壓縮，抓到的內容被摘要掉。
- **大 context（使用者：「我犧牲速度，cpu gpu 一起用，鎖死不溢出到ssd，然後常駐吃記憶體的非必要占用全部根除，這樣能開多少」）**，3090 實測、`-lm mlock`、q8 KV：E4B 128K（它的上限 131,072）全放 GPU 4.46–4.62 GB；放 36 層 4.22 GB＋鎖住 2.24 GB RAM（RSS 3.08）；30 層 3.63 GB＋2.55 GB（RSS 3.66）；角色和 Agent 共用一塊 KV（`--kv-unified`，2 slot）不多佔。筆電約 33–34 層：顯示卡約 3.8 GB、RAM 約 3.2 GB。Qwen3.5-4B 128K 全放 GPU 要 5.69 GB、256K 8.41 GB，筆電做不到。`-ub` 縮小只省約 150 MB；`-lzm on` 在 mlock 下沒有省。**產品自己的 RAM 大戶**：租借模式的 llama-server 沿用上游預設 `--cache-ram 8192` MiB、每 slot 32 個 checkpoint（只有 base 模式設了 256 MiB／2）。
- 「要不要改動」判斷（`scripts/dev/task_scope_eval.py`，43 句，E4B＋機魂人設）：41/43；錯的兩句都是安全方向（一句唯讀被當改動 → 照舊要批准；一句「查完存檔」被當唯讀 → Agent 做不到會說）。派工兩題合計中位數 109 ms（3090）。
- 中性電子音（SenseVoice 錯字率）：原聲 7.2%、選定的 C 7.4%。
- 舊結論：E4B＋v3 LoRA 配對盲評贏原版（59% vs 40%）；3050 Ti 套 LoRA 判斷 211 ms、生成 26 token/s。

## 7. 踩過的雷

- OpenCC `s2twp` 會改已經是繁體的詞（「測試通過」→「透過」）：只轉含簡體字的文字。
- Pi 離線時沒有 rg/fd，grep/find 永遠失敗；部署要附固定版本。
- NativeChat 做完會把訊息搬進 `session.entries`，解題紀錄要讀 entries。
- `--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。
- QLoRA 不要用 `prepare_model_for_kbit_training`（Gemma 4 會 OOM）；TRL 從尾巴截斷，太長的資料丟掉不要截。
- 筆電 pytest 要 `--basetemp`（`pytest-of-<使用者>` 會 PermissionError）。
- GitHub release 下載慢：`curl -r` 分段平行。
