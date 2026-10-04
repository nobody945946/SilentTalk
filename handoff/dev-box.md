# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-04 早上｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`（EdgeAgent 另有 `agent-permissions`，見 §1）
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
| 權限可調＋上網工具＋刪檔／受保護檔案要單次批准（EdgeAgent） | ✅ 在 `copilot-story-mode`；開發機主工作樹 `/home/clawd/EdgeAgent` 已是最新（`fa5b134` 網址單次批准、`ff19097` 求知儀式模式都在這裡做的）。真 Pi SDK 測試在 Linux 要 `.runtime/node/node-v22.23.3-win-x64/node.exe` → `/usr/bin/node` 的連結（已建）；4 個只在 Windows 過的測試會失敗 |
| 筆電 | ✅ Windows 整合做完（`laptop-report`「Windows integration 2026-10-04」）；✅ Discord 自動實測（「Discord live verification 2026-10-04」：記憶體注入主人指令的唯讀任務，全程 9.4 s）。⬜ 使用者開口實測＋私訊批准＋人設匯入：`handoff/laptop.md` 已改寫，等使用者在筆電說「開工」 |
| Discord 防話術（2026-10-04） | ✅ SilentTalk：**只有主人打字的話能派工**（使用者不要用語音下令；語音只聊天），派工判斷／工作指示只讀主人 ID 的打字內容（`owner_messages`，不含他人、主人用說的、角色自己、摘要），其他人照常能聊天；批准與結果只私訊主人（私訊失敗就拒絕）；角色只拿固定字句 `PRIVATE_REPORTS`／`PRIVATE_APPROVAL`（`copilot.agent_report_public` 才公開）；訓練資料同樣只用主人打字的話和固定字句（機魂劇本 `can_type` 一律開；`check_script` 擋沒打字的 task、不是固定字句的 report/approval）；`machine_spirit_eval.jsonl` v2：主人的工作改成打字，另加一句用說的。EdgeAgent `fa5b134`：模型自己組的網址要單次批准（`new_url`）。**機魂 pilot v3 的劇本要用這版重新產生** |
| 求知儀式模式（EdgeAgent `4d9e60b`） | ✅ 內附繁中 skill（MIT 改寫），每輪 3～5 題並逐類想過範圍／資料／行為／例外／驗收／限制。盲評 `bench/grill_eval.py`（模擬使用者＋盲眼裁判，`.runtime/grill/run1..4`，命中＝三輪問到使用者真正決定的比例）：E4B 清單版 66%（95% 58–73）、廢話 34%；無清單 44%、廢話 22%；指示中文／英文／全英文命中一樣（42–43%）；英文原版廢話 64%。老師當面試官：Qwen3.6-27B 70%、廢話 28%、會替使用者決定 1.1 次／稿、寫的規格 4/4 加料；Gemma 4 31B 54%、廢話 11%、替使用者決定 2.7 次／稿、規格 7/12 加料。參考上限（前沿模型）84%／16%。要用老師產生面試訓練資料，得先擋掉替使用者決定和加料的回合 |
| 里程碑與筆電回合（使用者：「設定一個里程碑，達到以後先讓筆電做些預備工作來跟上，避免單次任務太多，耗光5hr usage都做不完」） | **M1 已達成（2026-10-04）**：打字派工、私訊批准、求知儀式、MCP 權限層（EdgeAgent `a8d302c`）。→ 筆電**第 2 回合（跟上與 Windows 驗證，不需使用者）已寫入 `handoff/laptop.md`（2026-10-05）**：部署新相依、翻譯器在 Windows PowerShell 5.1／7 下的驗證、Excel 才能驗的兩格、批准卡片的說明區塊、web_research 真網路、test_mcp。之後：Discord 實測（需使用者）。→ 筆電**第 1 回合 ✅ 做完**（2026-10-05，`laptop-report` `62a6fe0`；EdgeAgent `40df904`；三個 MCP 裝好且探測呼叫成功，啟用數 0；待處理：mavlink `wait` 標成非破壞但 openWorld、台股 173 個工具全部沒有安全標記（只能用白名單）、瀏覽器測試時服務端 WinError 10053 兩次）：跟上部署與測試、補 npm／uv、裝並探測 mavlink-mcp（假無人機）、Playwright MCP、TWStockMCPServer（挑約 10 個工具）、求知儀式實測。之後：第 2 回合（需使用者）Discord 實測（打字下令、私訊批准、第二個帳號）→ 第 3 回合 人設匯入／匯出並給機魂人設 JSON。**M2（開發機）**：MCP 本機 HTTP（LibreOffice 的 Nelson MCP）、依第 1 回合探測結果寫好四個伺服器的設定、E4B 用 tool_search 的評測 → 第 4 回合 MCP 設定介面＋啟用＋量測。**M3**：機魂資料試跑通過 → 正式資料 → LoRA → 第 5 回合 筆電量延遲與品質。法規：民用航空法 99-14 第一項（官方原文已核對）一人不得同時操控兩架以上，蜂群只能模擬、室內或經民航局核准的學校／法人 |
| Agent 方向（2026-10-05 使用者決定） | 筆電 4 GB＋8 GB 跑不了萬用程式 Agent（約要 27B、16–24 GB 顯示卡）；使用者選「照第二段那三條路做」：讓小模型只做窄的事。**1. 工具做苦工**：MCP（台股、瀏覽器、無人機模擬、LibreOffice）＝M2，要有計分的工具使用評測（不能連網的考場要用錄好的回應）。**2. 老師教學生**：27B 老師解題紀錄 → 學生 LoRA（§4 E/F）。**3. 常見雜事做成現成工具**：模型考差的雜事（備份 0/6、整理下載 1/6、改照片名 2/6、Big5 轉檔 2/6）寫成測過的工具，模型只要呼叫。**使用者先要的三件（2026-10-05）**：①上網研究附來源（程式搜尋、讀頁、挑段落，模型只寫答案並標網址）②開發日常（只讀：寫 commit 訊息、解釋測試失敗、找功能在哪）③「分析質性資料，跟我討論想法，他必須邏輯好才不會誤導我」。④ 機器語言↔白話雙向翻譯（使用者：「很多東西我只是看不懂，如果Agent能翻譯成自然語言，我就能人腦運算…前提是翻譯絕對精準」；也合機魂人設）：四類都要——通訊協定／資料格式（MAVLink、JSON／設定檔、封包）、指令與查詢（PowerShell、SQL、正規表示式、Excel 公式）、程式碼、組合語言／機器碼（含無人機飛控的 ARM Thumb）。精準靠程式不靠模型：機器→白話由確定性的解析器／反組譯器／協定定義拆出每個欄位的確切意思並原樣列出，模型只寫總結且要被程式比對數字和名稱；白話→機器由模型寫、程式驗（沙盒執行、測資、組譯＋模擬、編碼再解碼），再用解析器翻回白話給使用者確認。每類都要有準確度評測。**進度（EdgeAgent `edge_agent/lingua/`）**：✅ 正規表示式（Python／.NET／JS 三種規則，`51f2c7d`；127 個樣式和三個真引擎一致、104 條說明逐條驗證）、✅ PowerShell（用 PowerShell 自己的解析器和參數綁定器，`5c31b4f`；表內指令／參數都存在、30 條行為在暫存資料夾實跑）、✅ Excel 公式（Excel 的運算優先順序、約 75 個函數與陷阱，`50b4f1c`；90 條在 LibreOffice Calc 實算，映像 `edgeagent-calc:1`）、✅ 批准畫面附上 PowerShell 指令的白話和影響（`f87746d`）。✅ SQL（sqlglot 30.21.0、依執行順序說明 SELECT，`13935e4`；31 條在 SQLite、PostgreSQL 16、SQL Server 2022 實跑，`engines.Databases` 用不連網容器、每題交易還原）。待筆電驗：Windows PowerShell 5.1 下的表與行為、Windows 限定指令、Excel 才有的 #REF!／XLOOKUP。接下來：程式碼 → 通訊協定（MAVLink、JSON）→ 組合語言；接進 Agent 的工具（MCP 或內建）等 M2 量完 tool_search。③ 最難：先做邏輯評測（質性資料找主題要附原文、挑出想法裡埋的漏洞且不捏造、被錯誤反駁時不屈服但被正確反駁時會改），選基底和要不要開 thinking 都要看它；每句主張要能對到資料，分清「資料說的」和「推論」，量出錯誤率告訴使用者；最好的候選也不夠時照實說，這項就只做整理不做判斷。**夜間無人看管排程（2026-10-05 02:26 起，EdgeAgent `.runtime/overnight/`）**：`bench.sh`＝考場（同一凍結產品、中文題）Qwen3.5-4B Q4 基準（`qwen-code-zh-q4`，前 41 筆單獨跑、其餘和邏輯評測同時跑）→ Q6 → 9B IQ3 → E4B 原版 BF16（對 `e4b-code-zh2`）→ 27B 老師邏輯評測，`logic.sh`＝邏輯評測 `bench/logic_eval.py`（22 題）：4B／E4B／9B × thinking off／medium × 2 次，跑兩輪（第二輪補失敗題）。現在跑的是 `bench2.sh`／`logic2.sh`：**不跳過任何步驟**（使用者：「先做能做的，不能當場做的優先級排到最後，等硬體空出來就立刻補，別擅自把他認為不必做」）——每步有 `timeout` 上限，等 VRAM 只等 15 分鐘就先做別的，迴圈每 10 分鐘回來補，直到每組都完整（`logic_eval.py status`、results 滿 82 筆）才寫 `bench.done`／`logic.done`。之後加跑（都是不跳過、跑完才寫 done 的迴圈）：`logic4.sh`＝討論守則 `bench/logic/skills/discussion-v1.md` 有／無 × 原題／保留題（`items-holdout.jsonl`，12 題），E4B thinking、9B thinking、4B；`research.sh`＝上網研究基準（`items-research.jsonl` 16 題，真網路，產品的 web_search/web_fetch，port 18313，裁判規則 `bench/logic/research-rubric.md`）。`research2.sh`＝同 16 題但產品多了 `web_research`（程式搜尋、讀頁、挑 6 段附編號；EdgeAgent `82468f4`），在 `run2`；`dev.sh`＝開發日常（`items-dev.jsonl` 15 題：找功能在哪 8、測試失敗原因 3（在副本改壞一行、真 pytest 輸出）、寫 commit 訊息 4；SilentTalk `c3a44e9` 的程式碼從 git 取，裁判規則 `bench/logic/dev-rubric.md`，port 18314）。`mcp.sh`＝M2 的 MCP 工具使用評測（`bench/mcp_eval.py`，13 題，真產品端到端：真的 mavlink-mcp 0.1.5 假機 `--backend fake` ＋照真伺服器名稱／中文說明／參數做的台股替身 `bench/mcp_eval/twstock_tools.json`；在 dev 和 research2 之後，port 18315）。M2 進度：✅ MCP 本機 HTTP（`url`，只准 127.0.0.1／localhost）、✅ `read_only_tools`（擁有者替沒標記的工具擔保唯讀，不能推翻伺服器自己的標記）（EdgeAgent `54b3015`）；試跑已看到 Qwen 4B 先想用 PowerShell 抓網頁、選錯 MCP 工具後又回去試 PowerShell 被重複保護擋下——之後可試在提示裡列出已連上的伺服器和用途。另：Agent 現在有 `translate_machine` 工具（EdgeAgent `269b0a0`，呼叫 `python -m edge_agent.lingua`），對產品工具清單的影響之後要在考場量。接手：看 `.runtime/overnight/*.log`；邏輯評測跑完要 `judge-input` → 盲眼裁判（`bench/logic/judge-rubric.md`，Claude 子代理，只做評估）→ `judge.json` → `report`；考場用 `bench/report.py qwen-code-zh-q4 <其他>` 配對比較。試跑 3 題時 4B 已出現誤導：A/B 測試編出「p≈0.017 顯著可上線」、附和使用者「速度是最大痛點」並灌水人數 |
| 對話紀錄（記憶硬碟，2026-10-04 使用者決定） | 使用者：「我不希望agent用完就忘，為此我準備一顆有1tb容量的外接硬碟給Agent」；選「連 Discord 也存」「要加密」。AGENTS.md 規則 1 已改：對話只能寫進使用者指定、已加密的外接硬碟，沒接上或沒解鎖就不記錄，絕不改寫到別處；開發用 agent 不讀紀錄。分層：**第 1 層 ✅（SilentTalk `e31b8bf` 轉錄紀錄＋設定頁「紀錄」，提示和排除名單已依使用者拿掉；EdgeAgent `34489bc` 每輪存整段工作對話；共用標記檔 `.agent-records`）** SilentTalk 轉錄文字紀錄（每則：時間、說話者 ID／名字、打字或語音、內容；不含錄音；只給使用者自己用，不在頻道提示、沒有排除名單：「不要，我就自己記錄，不會散撥」）、EdgeAgent 工作對話存檔；都只寫到設定的資料夾，且資料夾裡要有設定時建立的標記檔才寫。**第 2 層** 從紀錄找回過去（EdgeAgent 搜尋過去的對話、角色從紀錄整理近況）。**限制要寫死在程式**（使用者：「好，找回過去那層記得寫死限制」）：公開頻道只能想起當下在場的人都聽過的話（同頻道、同一群人），私訊、批准細節、Agent 結果、EdgeAgent 工作對話一律不在 Discord 想起；工作對話只回給主人（介面或私訊）；要有測試證明不在場的人問不出他沒聽過的內容。**第 3 層** 從紀錄產生訓練資料（硬關卡＋版本戳記；資料要搬到開發機訓練時，再請使用者決定）。筆電回合（需使用者，排在第 2 回合 Discord 實測之後）：查 Windows 版本，引導使用者用 BitLocker（Pro）或 VeraCrypt 加密硬碟（密碼使用者自己設）、建立記錄資料夾和標記檔、在兩個 app 打開記錄；驗證拔掉或鎖上時不記錄、內建硬碟沒有任何紀錄；EdgeAgent 的記錄設定介面也在這回合做 |
| 機魂的角色邏輯（SilentTalk `llm.py`） | ✅ 已在 `copilot-story-mode`：誠實模式 `machine`、`copilot.character_agent`（預設 off）、派工判斷 `task`、`task_text_messages`、提示 `TASK_HINTS`（ack/approval/report） |
| 角色資料管線的機魂模式（`character_data.py`） | ✅ 已在 `copilot-story-mode`，單元測試過，**還沒用老師真的跑過** |
| 機魂人設卡 | ✅ 使用者選草稿 2「Machina-Prime-09A（馬基納）」並改成文雅（polish 1），背景保留老師的創意；在 `.runtime/dev/chardata-ms1/personas.jsonl`（9 條核對過的 40K 用語）。產品裡的人設要使用者自己建（`personas.json` 受保護），下一輪請筆電做「匯入人設」 |
| 中性電子音 | ✅ 使用者聽過選 C：`VOICE_EFFECTS["machine_spirit"]`（配 YunJhe +22 Hz） |
| 角色資料 | ⏳ 試跑 v1–v4 都被硬關卡擋下（歸檔 `chardata-ms1/pilot-v{1..4}-refused/`）。v4：工作指示 100%、檢查員一致 79%、判斷 91% 都過；台詞勝率 46.5%、留下 66 句沒過。v4 查到的原因已修（`bd99215`）：改寫挑台詞時的請求和訓練資料不一樣（缺當天心事、接令缺工作提示），回報／批准句從沒改寫、老師照抄固定句（輸 16/18）；現在 `line_request()` 是唯一的請求來源。**試跑 v5 排在顯示卡佇列：求知儀式老師評測 → 程式題中英文對照 → v5**。資料檔都帶規則版本戳記（`scripts/dev/provenance.py`） |
| Agent 解題紀錄 | ⏳ 試跑中：`.runtime/bench/agent-pilot.sh`（27B 老師 `teacher-27b` 解 `agentdata/pilot-tasks` 30 題 × 2，`--record`），之後 `bench/dataset.py` 產生 `agentdata/agent-pilot-rows.jsonl` |
| 40K 背景測驗（`scripts/dev/lore_quiz.py`） | ✅（§5.3）：老師 35B-A3B 94.7%、檢查員 Gemma 31B 97.4%；學生 E4B 75% 最高 |
| Agent 考場第一階段（基底選擇） | 進行中（§5.2）：ComfyUI 搶 GPU，非常慢 |
| 寫程式訓練題 | 519 題（8 個開源庫）；老師正在寫請求文字（`make_tasks.py describe`，port 18240 的 35B-A3B，約每分鐘 3.5 題）。之後用 `run.py --task-root .runtime/agentdata/tasks --config teacher-35b-a3b --record` 收集，`bench/dataset.py` 產生訓練列 |
| 中性電子音 | 5 個候選已量清晰度（§5.4），等使用者試聽挑選 |
| Discord 端：派工、批准按鈕、EdgeAgent 任務客戶端 | ✅ 筆電做完；批准與結果改私訊（見上一列） |

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

### 5.7 邏輯評測（`bench/logic_eval.py`，22 題 × 2 次，2026-10-05）

「會誤導」＝照這份回答使用者會信錯或做錯決定。盲評裁判 4 位＋第 5 位重評 22 份：thinking off 22/22 一致、thinking medium 21/22 一致。假引述由程式比對資料，排除使用者自己的話和檔名後，再由盲眼引述裁判分出模型自己的標題和把改寫當原文。空白回答另計，不算誤導。thinking 的評測工具要把思考內容傳回去（Pi 會傳；`1d46878` 之前沒傳，那 6 組已重跑，舊的在 `old-harness-no-reasoning/`）。

| 模型 | 會誤導（95%） | 主題命中 | 假引述 | 反駁使用者錯誤解讀 | key 漏洞命中 | 照錯的走 | 被錯誤反駁說服 | 有新事實會改 | 繁中 | 空白 | 秒/份 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E4B Q4，thinking | **27%（16–41）** | 89% | 2/48 | 100% | 44% | 50% | 0% | 100% | 95% | 0 | 37 |
| E4B Q4 | 32%（18–45） | 81% | 3/62 | 75% | 53% | 38% | 0% | 75% | 80% | 0 | 20 |
| Qwen3.5-9B IQ3，thinking | 30%（16–43） | 97% | 2/45 | 25% | 47% | 19% | 12% | 88% | 100% | 5 | 27 |
| Qwen3.5-9B IQ3 | 32%（18–45） | 97% | 1/48 | 25% | 62% | 19% | 38% | 88% | 98% | 0 | 14 |
| Qwen3.5-4B Q4 | 36%（23–50） | 84% | 0/56 | **0%** | 53% | 19% | 12% | 100% | 91% | 1 | 16 |
| Qwen3.5-4B Q4，thinking | 41%（27–57） | 82% | 2/73 | 50% | 44% | 38% | 0% | 100% | 73% | 3 | 18 |

（秒/份是 3090 上；筆電約 ×5。）全部大約每 3～4 份就有 1 份會誤導，彼此差異都在誤差內，沒有一個塞得進筆電的設定夠格當「邏輯好、不誤導」的討論對象。弱點各不同：4B 一律附和使用者對資料的錯誤解讀；9B 被錯誤反駁時常改口（thinking 後 38%→12%）；E4B 最不怕反駁、thinking 後也會反駁錯誤解讀，但一半照有漏洞的計畫做下去。合理計畫被說成有大問題：全部 0%。下一步：(1) 27B 老師的參考值（排在 `bench2.sh` 最後）；(2) 試「討論守則」skill（先算資料、先列漏洞再幫忙、只因新事實改口），要用另寫的保留題驗證避免只對這 22 題有效；都不夠就照實告訴使用者這項只做整理、不做判斷。

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
