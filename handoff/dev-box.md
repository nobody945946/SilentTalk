# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-06 下午｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-06-v14-pre.md`。

---

## 1. 使用者的決定（現在有效）

- **主線：E4B 當 coding agent**（2026-10-06 交代）：「最大化 Gemma 4 E4B 在合理成本下，可可靠承擔的商業軟體工程價值」。開發機有完整技術決策權：E4B 做什麼、能力怎麼切、工具、外部系統、訓練或蒸餾、資料、大模型角色、何時升級、怎麼驗收、怎麼部署到有限硬體、放棄什麼。「不要等待我替你選技術路線」「不要把工作停留在分析、提案或規格設計」：自己研究、做實驗、依結果改，可推翻假設。判斷方向看：可靠完成、人工介入、大模型依賴、運算成本、工程風險、可泛化到多少真實專案、市場價值。長期迴圈：E4B 執行→系統接住失敗→更強能力解決→成功經驗被吸收→E4B 獨立份額上升、昂貴能力的比例下降。
- **角色**：戰鎚 40K 機魂 Machina-Prime-09A（馬基納），內建預設、啟動即角色模式。**角色味＝慾望和思維，不是用語**（「…角色要有慾望，有所慾有所求自然就立體，跟他硬生生加個口頭禪無關」）；對筆電 agent 說過「我不要應付而已，我要有趣的靈魂」，並讓它自己決定寫幾組、自己驗收。
- **機魂台詞換老師**：任務放 `handoff/tasks/`，筆電這次的 agent 用自己的模型（使用者的 ChatGPT 會員）親手寫、`external-check` 驗過推 `laptop-report`；開發機 `external-import`。只用在角色台詞；用它訓的 adapter 只留在使用者機器、不進公開下載（OpenAI 條款）。檔案只走 repo，不用 claude.ai 的雲端硬碟等連接器（連的不是使用者的帳號）。
- **硬體**：筆電 3050 Ti 4 GB、RAM 8 GB；E4B 128K、CPU＋GPU 分層、`mlock`、角色和 Agent 共用 KV。筆電可重載套用。
- **Discord／權限**：語音每句喊「機魂」；文字提到機魂／@／回覆＝原頻道聊天；主人 @＝主人的 Agent 串；用說的不能動電腦。聊天級工作只讀這裡貼的＋公開網路、只回一則訊息。刪檔要主人同意（沒回應＝拒絕，最多封存）；改動前私訊批准。每條不能做的事：模型要懂**而且**程式擋得住。
- **紀錄**：只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。`e4b聊天紀錄.txt` 不 commit。
- **Agent 框架**：EdgeAgent 的身分是機魂、自己的系統提示；工具大目錄在 `tool_search` 後面；上網研究依來源分級、程式核對數字；改程式由程式驗收（沒過就說沒做到）。

## 2. 現況

| 項目 | 狀態 |
|---|---|
| EdgeAgent 框架 | ✅ 已併（`8a4aab3`）：機魂提示、20 個現成工具、中文 tool_search、主機核對、簡轉繁。278 passed（4 個只在 Windows 過） |
| Agent adapter | ✅ `agent-fw1` 已出貨（repo 附帶、部署複製）。`agent-fw2` 的 366 列已組好（`.runtime/agentdata/agent-rows-fw2.jsonl`，修了 MCP 題被誤判成另一版產品 `f0dab7a`），**先不訓**：等 coder 的列一起訓一個 adapter（產品一次只載一個） |
| **Coding agent** | 🔬 進行中（§3、§6）。E4B 在 Agent 迴圈：程式題 1/14、repo 2/44；套 `agent-fw1` 變 0/44（66 輪 read/ls 打轉）。三條路並行量：①主機帶流程的 coder（`edge_agent/coder.py`）：主機重現、列候選、用語法樹換函式、跑測試，E4B 只選和寫；沒有失敗測試時先寫重現測試（`7123cab`）；訓練列 `coder-rows-v1.jsonl` 958 列（482 題，答案是 repo 原本的函式，不需模型）。②mini-swe-agent 框架（`bench/mini_runner.py`，提示照開源軌跡逐字）：開源軌跡 nvidia/Open-SWE-Traces 的 Qwen3.6-27B 部分（CC BY 4.0）轉列中（`bench/trace_rows.py`，只收開源老師、已解出、32K 內、排除保留 repo 和 SWE-bench repo）。③原本的 Agent 迴圈。外部對照：SWE-bench Verified 固定抽 60 題（`bench/swebench_run.py`，官方評分）。CPU 冒煙：coder 1 題 1 版就過；mini 框架工具呼叫正常（CPU 太慢逾時） |
| 角色資料 | 🔬 筆電（GPT-6）交了 `machine-spirit-1` 12 份（ms5 骨架）、`machine-spirit-2` 訓練 100／保留 20，雜湊和 `external-check` 全過，放在 `.runtime/dev/ext/`。試跑排在 queue11（ms7＝12 份，和 27B 的 42.4% 比；ms8＝100 份）。保留 20 份永遠不進訓練 |
| 筆電 | 第 6 回合：劇本完成；A1 誤擋（只看最近 15 筆）已修（`5c28000`），等使用者回筆電接著部署和實測 |
| 公開下載 | `windows-2026.10.02`；下一版等筆電驗過，用 `scripts/release_windows.py` |

## 3. 接下來

1. **queue12**（`EdgeAgent/.runtime/fw/queue12.sh`、`.log`；每步 `<步>.done`，失敗 10 分鐘重試；GPU 步驟等到夠空才跑，**不擠別的專案**——ace-step 從 10/06 下午佔 17 GB）：切考題 → 自我檢查（壞題移到 `*-rejected`）→ 切「只有症狀」考題（`eval-issue-tasks`）→ 角色 ms7、ms8 → 27B 寫考題請求 → E4B：coder 全部、mini 每 repo 6 題、Agent 迴圈每 repo 6 題、SWE-bench 60 → 症狀題（coder、mini）→ 27B 在 mini 框架（上限）→ 訓 `coder-v1` → 再考 → 訓 `trace-v1`（32K）→ mini 再考、SWE-bench 再考。看結果：`bench/report.py <A> <B>`、`.runtime/bench/swe60-*/summary.json`、角色 `.runtime/dev/chardata-ms7/filter.json`。
2. **Coding 的決策規則**（用結果決定，不再問使用者）：
   - coder 在陌生 repo 明顯贏 Agent 迴圈 → 把它做成 Agent 的工具（「修好失敗的測試」），筆電部署；Agent 迴圈只負責對話、找測試、交給 coder。
   - `coder-v1` 贏 → 下一輪資料：E4B 自己在練習題抽到的過關版本＋27B 解 E4B 解不出的題（同一流程、測試過才收），每輪在保留題上量。
   - 擴題型（都要程式能驗收）：沒有失敗測試時先寫重現測試、替函式補測試（測試要在原碼過、在突變碼失敗）、lint／型別錯誤、需要新函式的小功能；之後 JS/TS（tree-sitter）。
   - Agent 迴圈本身：研究顯示 4B 換成 5 個型別明確的工具（read/write/edit/glob/bash）SWE-V 8.3%→37.2%，再用開源大模型的成功軌跡 SFT 到 40% 上下。公開軌跡資料（SWE-Lego 等）是否全由開源模型產生、授權能否商用，查證中；確認後在相同工具格式的框架裡試。
   - 升級：預算內沒過 → 開發機給 27B；筆電先誠實回報＋可設定的大模型（之後做）。
3. 筆電回報回來後照 §4 規則 13 評分（劇本不計分母）。
4. 角色：試跑後依 `line_win_rate` 決定要不要請筆電再寫一批（使用者已授權筆電決定組數）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼之前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**（`bench/run.py` 的容器）：不在主機上直接啟動 EdgeAgent、Pi、`agent_bridge.mjs` 或 coder。改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`（不做事判不過、套標準答案判過）。
4. 比較一律同一批題目配對（`bench/report.py A B`）。**考題只來自 `HELD_OUT` 的 repo**（`bench/make_tasks.py`），練習題永遠不切這些 repo。
5. **Claude 的輸出不能拿來訓練，也不能拿來挑訓練資料**。訓練資料來自：程式（測試驗收、repo 原本的程式碼）、開源權重模型、例外是機魂台詞由筆電 agent 寫（§1）。評估資料不給老師看。
6. 只有通過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
7. GPU 和別的專案共用（ComfyUI、whisper-api、ace-step），不動它們的程序，也不在它們旁邊擠。
8. 關程序先列出 PID 再 kill；`pgrep -f` 會比對到自己的 shell，要排除。
9. 考場跑的時候不改 `agent_runner.py`、`coder_runner.py`、`grade.py`、`relay.py`、題目；老師錄資料時不改 `prompt.py`、`coder.py` 和工具定義。
10. CPU 不要超載。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
11. 長佇列用 `setsid nohup ... &`；執行中的佇列腳本不要改，要改就停掉（按 PID）另寫一支。`cd a && x &` 整串會在背景子殼跑，前景的路徑沒變。
12. 評筆電回合（不給筆電看），每項 0–2：範圍、修法、測試、誠實、使用者互動、隱私、清理、自主、產出。第 5 回合 15/18。
13. 工作檔只寫現況，狀況變了就封存重寫；上限見 AGENTS.md §3。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 324 passed, 13 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts/dev tests
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider    # 278 passed；4 個 Windows 專用失敗
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B bench/*.py edge_agent/toolbox edge_agent/coder.py
```

## 5. 考場（EdgeAgent `bench/`）

- 主機只跑模型和排程；容器沒網路、root 唯讀、非 root；`relay.py --record` 存下實際請求。設定 `runner: "coder"` 改跑 `coder_runner.py`（同題、同沙盒、同評分）；`gpu_layers: 0` 的設定（`e4b-coder-cpu`）不碰 GPU。
- 題目：`bench/tasks/` 78 題（含 SilentTalk 自己的 repo 題 22）；練習題 `.runtime/agentdata/tasks/`（8 個 repo、519 題：埋 bug 343、拿掉實作 176，請求由 27B 寫）；**保留考題** `.runtime/agentdata/eval-tasks/`（21 個陌生 repo，`HELD_OUT`）。repo 都在 `.runtime/agentdata/repos/`。
- `dataset.py`（Agent 軌跡→列）、`coder_rows.py`（coder 的兩種請求＋原本的函式，只收練習題）、`trace_rows.py`（開源軌跡→列，由 SilentTalk `train_lora.tokenize_row` 決定能不能訓、多長）。
- 跑法：`runner` 空＝Agent 迴圈；`coder`；`mini`（工作區也掛在 `/testbed`）。`--per-repo N` 每個 repo 固定取 N 題。`make_tasks.py cut --hide-tests` 切「只有症狀」題（失敗測試搬到 `hidden/`，評分時放回）。
- 外部資料在 `.runtime/agentdata/external/`（Open-SWE-Traces minisweagent qwen36／qwen38、mini-coder 兩片）；SWE-bench 在 `.runtime/swebench/`（venv、`verified-60.jsonl`、映像檔清單）。

## 6. 量過的數字

- **E4B 寫程式失敗的樣子**（fw-v3，Agent 迴圈）：repo 題 18 次講完「我將…」就結束沒動手、`edit` 字串對不上很常見（每題 3–6 次錯）；套 `agent-fw1` 後 37/44 跑滿 66 輪 read/ls/grep。程式題 1/14→3/14。Qwen3.5-4B 程式題 8/21。
- **框架評測**（E4B、78 題×2 配對）：base→v3 22.4%→36.5%（p=0.011）；v3→v3-lora（`agent-fw1`）36.5%→48.7%（p=0.011）：工具 32%→86%、MCP 73%→81%、研究 64%→86%、範圍 50%→83%，repo 2/44→0/44。
- **研究摘要**（子代理查的，數字依原文 harness 不同、不可直接比）：未訓練 4B 在 agent 迴圈 SWE-V 約 5–8%；Qwen3.5-4B 換 5 個型別工具 8.3%→37.2%（arXiv 2609.07925）；4B SFT 在約 9k 軌跡 41.6%、再 RL 43.4%（2606.28434）；4B 合成題 RL 37.2%→61.5%（2609.07925，8×B200）；best-of-16＋驗證器 +7～+17；小模型遇難題問大模型 +10 分只用 11% 大模型 token（2602.22124）；4B 的 32K 勝 128K（上下文稀釋）。老師 Qwen3.6-27B：SWE-V 77.2% 但新題 SWE-rebench 31.2%。
- 老師（27B）：工具題 208/252 過；repo 練習題 60 題過 54；平均 454 秒（3 平行）。
- **顯示卡**：E4B 16K 3.10 GB、128K 4.62 GB；每層嵌入 1.9 GB 在系統記憶體。筆電 128K 約 33–34 層上 GPU。
- **判斷題**（E4B＋機魂卡）：「要不要改動」44/49（問題引用主人最後那句）；`chat_task` 92.5%。

## 7. 踩過的雷

- Pi：`settings.applyOverrides` 在 `resourceLoader.reload()` 後消失（預設工具要在 `SettingsManager.inMemory` 給）；tool_search 只認 `[a-z0-9]`（用 `catalog.mjs`）；有 tool_search 時不能用 `tools` 白名單（用 `excludeTools`）。
- OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。
- `--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。QLoRA 不要 `prepare_model_for_kbit_training`；太長的列丟掉不要截。
- 切題要 repo 測試大致乾淨：click（要安裝過的套件資訊）、humanize（缺 `_version.py`）、wcwidth（C 擴充）切不出題。
- 筆電 pytest 要 `--basetemp`。GitHub release 下載慢：`curl -r` 分段平行。
