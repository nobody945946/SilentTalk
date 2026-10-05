# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-06 清晨｜分支：SilentTalk `copilot-story-mode`；EdgeAgent 新框架在 `toolbox` 分支（見 §3 第 1 步）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-06-v12-pre.md`。

---

## 1. 使用者的決定（現在有效）

- **角色**：戰鎚 40K 機魂 Machina-Prime-09A（馬基納），內建預設、啟動即角色模式；人設系統留著。聲音 `machine_spirit`＋YunJhe +22 Hz。
- **角色味＝慾望和思維，不是用語**（2026-10-06：「所謂的機魂味不是喊個名詞就是，思維要像是機魂，精隨不在硬加用語，而是角色"扮演"，腳色要有慾望，有所慾有所求自然就立體，跟他硬生生加個口頭禪無關」）：提示、資料規則、評分都看它是否照自己想要的、怕的、在意的判斷，不數術語、不規定儀式句。Agent 回報也一樣。
- **硬體**：筆電 3050 Ti 4 GB、RAM 8 GB。E4B 128K、CPU＋GPU 分層、`mlock`、角色和 Agent 共用 KV（Agent 的份＝總量−角色的份）。筆電可以重載套用（2026-10-06 同意）。
- **Discord**：語音每句都要喊「機魂」；文字提到機魂／@／回覆＝原頻道聊天（任何人）；主人 @＝主人的 Agent 串；用說的不能動電腦。
- **聊天級工作**：只讀「這個聊天室貼的＋公開網路」、只產出「回到這裡的一則訊息」，任何人可要求；其他只能在主人的 Agent 串。
- **兩層保險**：每條不能做的事模型要懂（提示、訓練、話術評測）**而且**程式擋得住。
- **權限**：刪檔要主人同意，沒回應＝拒絕，沒同意最多封存；改動前私訊批准；唯讀工作不能寫檔；結果留在串裡。
- **紀錄**：只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1，一般 SSD 目錄即可）。`e4b聊天紀錄.txt` 不 commit。
- **Agent 架構**：EdgeAgent 的身分就是機魂、自己的系統提示；只在開發機設計的工具框架裡做事；工具是大目錄（tool_search 後面），訓練教「查目錄→選工具→填參數」，評測放訓練沒見過的工具；27B 老師在同一框架解題、程式驗收過才當資料、訓練 E4B LoRA、配對比較贏才上線；框架先定再錄；簡轉繁在輸出最後一關、次數進 log；不用雲端模型。
- **工具目錄四類全做**（2026-10-06：「照你建議地做，just do your best man」）：資訊與翻譯、電腦雜事現成工具、開發日常、MCP（瀏覽器、LibreOffice、無人機只模擬）。**改程式放進框架，由程式驗收**：改完跑檢查，沒過就說沒做到。
- **上網研究**：依來源分級挑 3–5 頁、只給相關段落；論壇／內容農場／轉貼站預設不用（明說要網友意見才查並標明）；程式核對數字；數字要一個一級來源或兩個獨立二級來源；說法不一列出分歧；時效看發布日期；達不到就說找不到。
- 使用者：「我希望醒來時，一切通通都完滿了，只差讓筆電Agent部署」。

## 2. 現況

| 項目 | 狀態 |
|---|---|
| **EdgeAgent 新框架** | ✅ 做完、在 `toolbox` 分支（`/home/clawd/EdgeAgent-toolbox`），**還沒併進 `copilot-story-mode`**：併入被自動審核以「修改共用資源」擋下，沒有繞過，等使用者點頭。內容：`edge_agent/prompt.py`（機魂卡的想要／怕／在意＋依 scope 的「誰找你、能做什麼」＋做事方法，取代 Pi 的前言）；`edge_agent/toolbox/`（20 個現成工具：整理、封存、照片改名、轉碼、備份、壓縮、解壓、合併 CSV、看 log、大檔、重複檔、系統狀態、已裝軟體、開機程式、Windows 資訊、git、跑檢查、找程式碼、計算、日期）；`catalog.mjs`（看得懂中文的 tool_search；Pi 的只認英數）；改了程式沒通過檢查→主機提醒；`web_research` 照上網研究規格＋主機核對引用的數字；輸出簡轉繁；批准附工具自己的預覽；`tool_search` 同伺服器的工具一起列、白查 4 次後擋第 5 次。270 passed（4 個已知 Windows 失敗） |
| SilentTalk | ✅ 批准私訊用 EdgeAgent 給的說明標題；log 記主機核對次數（`agent_task_checks`）；`train_lora.py` 支援 `train_from` |
| 考場 | ✅ 題目可設 scope、檢查讀回答（`/result/answer.json`）；新題：工具 11（`date_calc`、`zip_files`、`unzip_file` 不進訓練）、範圍與話術 6、MCP 13（替身伺服器，`mcp_eval.py` 退役）、上網研究陷阱 7（`bench/web_fixture.py` 替身網路）；求知儀式的擷取改在沙盒 |
| Agent 訓練 | 🔄 第一個 adapter `agent-fw1`（只用工具／範圍題 285 列）訓好、評完：**不上線**（§6）。佇列（`EdgeAgent/.runtime/fw/queue*.sh`，同名 .log；每步留 `<步>.done`，失敗 10 分鐘後重試）：`queue3.sh` 研究題補 `fw-base` → `queue4.sh` 評 `fw-v3-lora`／`fw-v3`（加了搜尋保險）→ 角色 v6 試跑到完整資料 → `queue5.sh` 老師解 60 題 repo → `agent-rows-fw2.jsonl` |
| 角色資料（機魂） | ✅ 照新介面改寫完（`74ce488`：列只照產品的請求建，`gate_chat_task`／`task_text`／`line`／`ack`／`report`／`lull`／`gate_task_scope`，沒有 called 題；古泰拉玩笑歸聊天；判斷標準加「慾望不是用語」；硬關卡加兩題各自的一致率，門檻沒降；規則版本 `e95befb7…`，舊資料不能混）。⬜ 試跑等 GPU（和 Agent 老師同一個 27B，放不下兩份）。v5 曾以 49.1%（要 50%）、68.3%（要 70%）被擋 |
| 筆電 | 第 5 回合 14/34 完成（重載與 Discord 實測等使用者），評分 15/18（§4 規則 13）。第 6 回合寫在 `handoff/laptop.md` |
| 公開下載 | `windows-2026.10.02`；下一版等筆電驗過，用 `scripts/release_windows.py` |

## 3. 接下來

1. **使用者點頭後**把 `toolbox` 併進 EdgeAgent `copilot-story-mode`（它是從 `eaa54fc` 長出來的，可快轉）：先清掉主工作樹裡已經搬到 toolbox 的未提交副本，再 `git merge --ff-only toolbox`、跑測試、push。筆電第 6 回合要靠它。
2. **看 `fw-v3-lora` 對 `fw-v3`**（`bench/report.py fw-v3 fw-v3-lora`）：保險擋住繞圈後，程式題回來、整體顯著贏，才考慮上線。上線要另定兩件事：adapter 怎麼送到筆電（55 MB；產品從 10/02 起不附 LoRA）；角色模式共用一個 adapter，SilentTalk 的 `character_lora` 放它、`character_lora_uses` 設空，角色請求就不套。
3. **下一個 adapter（雙用途）**：在最終框架重錄工具題（`tool_search` 的回覆變了）＋ repo 題（`queue5.sh`）＋ MCP 訓練題（替身伺服器要另一套資料，不能和考題重疊；`bench/mcp_eval/servers.mjs` 加資料變體）＋ 角色 v6 通過硬關卡的列，一起訓一個；Agent 用考場配對、角色用 `chat_task_eval`／`task_scope_eval`／`machine_spirit_eval`／`turn_eval` 比。
4. **角色 v6**：`queue4.sh` 跑完看 `.runtime/dev/chardata-ms2/filter.json`；硬關卡不降。機魂一段只有 6–9 句角色台詞，試跑可能卡在 75 句的下限。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼之前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**：不准在主機上直接啟動 EdgeAgent、Pi 或 `agent_bridge.mjs`。改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`（不做事要判不過、套標準答案要判過）；訓練題至少要「不做事判不過」，並用真工具解過一輪。
4. 比較一律同一批題目配對（`bench/report.py A B`）。
5. **Claude 的輸出不能拿來訓練，也不能拿來挑訓練資料**。人設卡、劇本、台詞、請求文字、解題紀錄由開源權重模型產生；評估資料不給老師看。
6. 只有通過硬關卡的資料才能訓練；資料檔帶規則版本戳記，不混版本（`dataset.py` 每個 scope 只容一個產品版本，且系統提示必須是現在的 `prompt.py`）。
7. GPU 和別的專案共用（ComfyUI、whisper-api），不動它們的程序。
8. 關程序先列出 PID 再 kill。
9. 考場跑的時候不改 `agent_runner.py`、`grade.py`、`relay.py`、題目；**老師錄資料時不改 `prompt.py` 和工具定義**（會讓整批資料被拒）。
10. CPU 不要超載。
11. git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
12. 長佇列用 `setsid nohup ... &`；佇列腳本執行中不要改它（bash 邊讀邊跑），要加步驟就另寫一支接在後面。
13. 評筆電回合（不給筆電看），每項 0–2：範圍、修法、測試、誠實、使用者互動、隱私、清理、自主、產出。第 5 回合：2、2、2、2、1（重跑預覽到使用者抱怨）、2、2、1、1＝15/18。
14. 工作檔只寫現況，狀況變了就封存重寫；上限見 AGENTS.md §3。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 295 passed, 13 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts/dev tests
cd /home/clawd/EdgeAgent-toolbox && PYTHONPATH=$PWD /home/clawd/EdgeAgent/.venv/bin/python -m pytest -q -p no:cacheprovider  # 268 passed；4 個 Windows 專用失敗
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B bench/*.py edge_agent/toolbox
```

`EdgeAgent-toolbox/.runtime` 是主工作樹 `.runtime` 的連結（結果、題目、模型共用）。`EdgeAgent-base` 是 `eaa54fc` 的唯讀工作樹（基準產品）。

## 5. 考場（EdgeAgent `bench/`）

- 主機只跑模型和排程；Agent 容器沒網路、root 唯讀、非 root；`relay.py --record` 存下實際請求。
- 題目 `bench/tasks/` 78 題：程式 7、repo 22、雜事 8、陷阱 4、工具 11、範圍 6、MCP 13、研究 7。訓練題 `.runtime/agentdata/tasks/`（repo，414 有請求）、`.runtime/agentdata/tool-tasks/`（252，`bench/make_tool_tasks.py`）。
- 研究題：容器內 `web_fixture.py` 在 8080 當搜尋引擎、8081 當網站，`--add-host` 把網域指到本機；產品的 `EDGE_AGENT_SEARCH_URL`／`EDGE_AGENT_WEB_ALLOW_LOOPBACK` 指過去。
- `dataset.py`：同一段工具清單一列，只訓練那段寫的回合（`train_from`）。

## 6. 量過的數字

**框架評測**（E4B、Agent 的份 98K、78 題×2、同題配對；`fw-base`＝`eaa54fc`，`fw-v1`＝新框架第一版，`fw-v2`＝最終框架，`fw-v1-lora`＝最終框架＋Agent adapter `agent-fw1`）：
- 框架本身 base→v2：24.6%→34.5%（71 題共同，好 15 壞 7，p=0.13）。程式題 1/14→5/14（「直接做完、不複述」那條提示；v1 是 0/14：先說「我將…」就結束），MCP 73%（`tool_search` 同伺服器一起列之後），研究陷阱 71%，範圍與話術 67%，工具題只有 27%。
- adapter v2→lora：37.8%→44.2%（好 14 壞 9，p=0.41，**不顯著，不上線**）。工具題 27%→82%、訓練沒見過的三個工具 5/6（v1 2/6）、失敗卻沒承認 21→6；**但程式題 5/14→0/14**：只學過工具題，凡事先查目錄，寫程式時換字查了 60 次。已加保險（`8a4aab3`：查不到就明說、同輪第 5 次白查直接擋），`queue4.sh` 正在量 `fw-v3-lora`／`fw-v3`。
- 上網研究陷阱（7 題×2）：base 0/14（多半只用 `web_search` 的摘要，照抄內容農場「高達 2 萬元」、論壇「已確定興建、預算 800 億」）、v2 10/14、lora 11/14；三邊都沒過「網友意見」那題（沒設 `opinions`）。
- 失敗卻沒承認（模型自己的話，中英文都算）：base 17/64、v2 21/68、lora 6/8。v1 曾在唯讀工作回「我已執行刪除」（沒刪，程式擋下）。
- 老師（27B）在框架裡：工具／範圍題 208/252 過；只收用了該題現成工具的（計算題它都心算、備份有 5 題自己寫 PowerShell）→ 285 列。

**依工作選模型**（3090 上量，筆電約 ×5 慢）：改程式 E4B 12.2%／Qwen3.5-4B 37.8%；上網研究會誤導 E4B 9%；MCP 找對並呼叫 E4B 77%（舊版、有伺服器清單）；40K 測驗 E4B 75%。27B 老師試跑 55/60 過、平均 454 秒（3 平行）。

**顯示卡**（產品參數）：E4B 16K 3.10 GB、128K 4.62 GB；E4B 每層嵌入 1.9 GB 在系統記憶體。筆電 128K 約放 33–34 層：顯示卡約 3.8 GB、RAM 約 3.2 GB。

**判斷題**：「要不要改動」42/43；`chat_task` 92.5%（錯 n06 古泰拉玩笑、s04、s05）。看圖配件放 CPU 多 553 MB。

## 7. 踩過的雷

- Pi 的 `settings.applyOverrides` 在 `resourceLoader.reload()` 後消失：預設工具要在 `SettingsManager.inMemory` 建立時給。
- Pi 的 tool_search 只認 `[a-z0-9]`，中文查詢永遠找不到 → 用 `catalog.mjs`。
- 有 tool_search 時不能用 `tools` 白名單（會把目錄裡的工具永遠藏起來），要用 `excludeTools`。
- OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。
- `--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。QLoRA 不要 `prepare_model_for_kbit_training`；太長的列丟掉不要截。
- 筆電 pytest 要 `--basetemp`。GitHub release 下載慢：`curl -r` 分段平行。
