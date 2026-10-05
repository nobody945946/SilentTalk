# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-05 晚上｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，過去的經過在 git 歷史和 `archive/`（只在這台機器、不進 git，不必讀）。上一版：`archive/dev-box-2026-10-05-v1.md`。

---

## 1. 使用者的決定（現在有效）

- **角色**：戰鎚 40K 機械教的機魂「Machina-Prime-09A（馬基納）」，文雅、會打破第四面牆陪主人開玩笑。人設卡在 `.runtime/dev/chardata-ms1/personas.jsonl`（老師寫、使用者挑改，9 條核對過的 40K 用語）。**預設就是機魂，啟動直接進角色模式**（2026-10-05：「我有點想預設就開40k機魂，其他人設都過去了，留著架構但不想開」）：其他人設不再預設提供，人設系統留著。聲音：`VOICE_EFFECTS["machine_spirit"]`＋YunJhe +22 Hz。LoRA 是使用者自選，產品不預設套用。
- **硬體**：一切都要在筆電跑得動（RTX 3050 Ti 4 GB、RAM 8 GB，平常只剩約 0.7 GB）。開發機不參與使用，只開發、評估、訓練。免費、不叫使用者做雜事。EdgeAgent 的 context 用 **16K**（2026-10-05）。
- **Discord**：只有主人打字的話能派工（語音只聊天）；主人在文字頻道 @ 就從那則訊息開討論串，受理 ⚙️、完成 ✅／失敗 ❌。**批准只私訊主人；工作結果要留在原本的討論串，session 清空後也能從串裡接續**（2026-10-05：「我以為是在該threads裡面聊天，順便起到記憶的作用，未來就算我session清空，也可以從該threads接續對話」）。
- **權限**：刪檔一定要主人同意，沒回應＝拒絕，沒同意最多封存；日常唯讀指令不逐次問（「我不想做雞毛蒜皮的決策」，EdgeAgent `shell: "routine"`）。主人說唯讀的工作就不能寫檔。
- **紀錄**：對話只寫進使用者的加密紀錄磁碟（AGENTS.md 規則 1）；手動匯出可以選一般資料夾（只限主人按匯出）。
- **Agent 架構**（2026-10-05，使用者：「e4b實際聊天體驗奇差無比，我開始考慮他只調用封包好的工具使用就好，聊聊天也OK無傷大雅，但不用輸出甚麼生成性內容」；三方意見：Codex、Antigravity 在 `laptop-report` 第 4 回合最後兩節，開發機的在下面；使用者：「目前意見到齊」）。三方都**有條件支持**，共同的部分照做：
  1. 主機提供或主機做：日期／時區、輸出語系、路徑、匯出、資料夾、狀態。模型不猜。
  2. 工作的限制由程式執行：唯讀＝寫入在權限層直接拒絕，不靠模型自律。
  3. 常做的工作做成封裝流程（有驗收條件）；模型只做意圖分類、選工具、填結構化參數，主機驗證後執行。
  4. 結果由主機從結構化欄位呈現；模型寫的文字只留在量過誤導率夠低的工作（上網研究附來源 9%；機器語言翻譯的總結由程式比對數字）。
  5. 角色聊天保留（短、不執行系統操作）。不用雲端模型。
  6. 先用合成資料配對比較量，封裝版贏才換。分歧：E4B 選對封裝工具的門檻，開發機說 85%、Antigravity 說 70%（低於 70% 就換調度模型）——照實量出來給使用者看。
  - **未決（要問使用者）**：角色開著時 Agent 會共用角色的 E4B（EdgeAgent `79af802`），而現在預設就開角色，所以 Agent 幾乎一直是 E4B；E4B 改程式考場 12.2%、Qwen3.5-4B 37.8%（p<0.001）。改程式的工作要「暫停角色換 Qwen」還是「照實說現在是 E4B、只做封裝工具」。

## 2. 現況

| 項目 | 狀態 |
|---|---|
| SilentTalk Discord 角色＋派工 | ✅ 打字派工、討論串、表情、私訊批准、`BOT_PERMISSIONS`／邀請連結。結果目前私訊（要改，§3） |
| EdgeAgent | ✅ 權限（含 `routine`）、MCP 權限層（`tool_search`、伺服器清單）、`web_research`、模式：工作／求知儀式／推演儀式、`translate_machine`（正規表示式、PowerShell、Excel 公式、SQL）、租借時自動共用角色模型（`79af802`）、對話匯出 TXT（`d793c2c`，筆電正式服務還沒重載） |
| 對話紀錄 | ✅ 兩個 app 都能「設為紀錄資料夾」、只寫在系統磁碟以外。⬜ 真加密容器：VeraCrypt 已裝，等使用者自己設密碼 |
| 筆電第 4 回合（Codex） | 清單 15/37；評分 15/18（第 3 回合 Antigravity 7/18，評分表見 §4 規則 13）。剩：正式服務重載（要使用者同意）、Discord 真人項目 D2–D14、加密容器 E2–E8、清暫存 F1 |
| 角色資料（機魂） | ❌ 試跑 v1–v5 都被硬關卡擋下。v5（`a949bea`）：40K 核對 98.8%、判斷一致 90.9%、工作指示 95.8% 都過；**台詞贏學生 49.1%（要 ≥50%）、檢查員一致 68.3%（要 ≥70%）沒過**。所以沒有 LoRA，機魂現在是原版 E4B 加人設 |
| Agent 訓練資料 | 27B 老師試跑 55 列（EdgeAgent `.runtime/agentdata/agent-pilot-rows.jsonl`）；訓練題 519 題，414 題有請求文字。還沒訓練 |
| 公開下載 | `nobody945946/SilentTalk-download` 放 `windows-2026.10.02`。下一版等筆電驗證通過，用 `scripts/release_windows.py`（先乾跑清查 ZIP） |

## 3. 接下來（依序；前一步沒過不做下一步）

1. **主機給 Agent 日期和時區**（`edge_agent/agent_bridge.mjs`；Pi 的系統提示只有 cwd）。這是 bug，修好不用 A/B。
2. **租借時 Agent 跟著角色的 context**：`79af802` 取兩邊較大，EdgeAgent 預設 131072，新玩家一租借角色伺服器就開 128K×slot，`--fit on` 會把權重推到 CPU、聊天變慢。owner：`EdgeAgent._start_child`。
3. **唯讀工作不能寫檔**（第 4 回合實測：使用者只要唯讀，Agent 多寫一個 62 bytes 的 .txt）：`task_from_owner` 判斷的限制變成那個任務的權限（寫檔、非唯讀指令直接 deny，不問），EdgeAgent 照任務權限執行；主人之後另外要求寫入才重新授權。合成測試走完整條路徑，不靠檔名或任務字串。
4. **結果留在討論串、從串的歷史接續**：最終結果送到來源討論串（依 Discord 字數分段、只送一次），批准仍私訊；每串第一次接續或 session 清空後，從 Discord 那個串取有界歷史放 RAM；歷史不能派工、不重放舊批准，串之間不串話；取不到就照實說。owner：`runtime._report_detail`／`_says`、`agent_tasks.AgentTaskClient.run`、`discord_voice` 的串、`runtime._context`。
5. **預設機魂**：機魂成為內附人設、沒有選人設時就用它；其他三個範本拿掉，人設系統和編輯器留著；啟動直接進角色模式（重啟腳本已帶 `--character-mode`）。使用者自己的 `personas.json` 不動。
6. **筆電第 5 回合**：1–5 推上去後重寫 `handoff/laptop.md`（舊版進 `archive/`）：部署、正式服務重載、驗 1–5 和匯出、剩下的 D／E 項。
7. **架構的量測**：合成的常見請求（新聞整理要日期範圍和來源、列檔／計數、匯出、上網研究、解釋機器輸出、整理資料夾），量 E4B 選對工具率、完成條件達成率、唯讀不寫入率、日期正確、來源可追查、會誤導率、筆電延遲；先封裝 2–3 個最常用的，配對比較贏才換。
8. **角色資料**：查 v5 台詞輸給學生的原因再決定下一步（不降門檻）。

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
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 286 passed, 12 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts/dev tests
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider    # 200 passed, 27 skipped；4 個 Windows 專用失敗（終端機 powershell.exe ×2、監聽埠查詢、Windows 的 fd）
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
