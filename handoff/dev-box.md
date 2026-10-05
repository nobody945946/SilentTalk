# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-05 深夜｜分支：SilentTalk、EdgeAgent 都用 `copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，過去的經過在 git 歷史和 `archive/`（只在這台機器、不進 git，不必讀）。上一版：`archive/dev-box-2026-10-05-v4.md`。

---

## 1. 使用者的決定（現在有效）

- **角色**：戰鎚 40K 機械教的機魂「Machina-Prime-09A（馬基納）」，文雅、會打破第四面牆陪主人開玩笑。人設卡在 `.runtime/dev/chardata-ms1/personas.jsonl`（老師寫、使用者挑改，9 條核對過的 40K 用語）。**預設就是機魂，啟動直接進角色模式**（2026-10-05：「我有點想預設就開40k機魂，其他人設都過去了，留著架構但不想開」）：其他人設不再預設提供，人設系統留著。聲音：`VOICE_EFFECTS["machine_spirit"]`＋YunJhe +22 Hz。LoRA 是使用者自選，產品不預設套用。
- **硬體**：一切都要在筆電跑得動（RTX 3050 Ti 4 GB、RAM 8 GB，平常只剩約 0.7 GB）。開發機不參與使用，只開發、評估、訓練。免費、不叫使用者做雜事。EdgeAgent 的 context：使用者照開發機的建議選了 16K，**但那個建議錯了**：Agent 先保留 8,192 輸出＋4,096 餘量才給歷史，16K 只剩約 4K（比系統提示加工具定義還小），幾乎每輪都壓縮（使用者：「我聊沒幾則他就開始compact」）。32K 有約 20K 歷史，兩個模型在筆電都放得下（§6）。**待使用者決定改 32K**。
- **Discord**：只有主人打字的話能派工（語音只聊天）；主人在文字頻道 @ 就從那則訊息開討論串，受理 ⚙️、完成 ✅／失敗 ❌。**批准只私訊主人；工作結果留在原本的討論串，session 清空後也能從串裡接續**（2026-10-05：「我以為是在該threads裡面聊天，順便起到記憶的作用，未來就算我session清空，也可以從該threads接續對話」；討論串是公開的，頻道裡的人看得到結果）。
- **權限**：刪檔一定要主人同意，沒回應＝拒絕，沒同意最多封存；日常唯讀指令不逐次問（「我不想做雞毛蒜皮的決策」，EdgeAgent `shell: "routine"`）。主人說唯讀的工作就不能寫檔。
- **紀錄**：對話只寫進使用者的加密紀錄磁碟（AGENTS.md 規則 1）；手動匯出可以選一般資料夾（只限主人按匯出）。
- **Agent 架構**（2026-10-05）。使用者看了自己和 E4B 的對話（`e4b聊天紀錄.txt`，簡單測試、無個資；在 repo 資料夾但**不 commit**）後的決定：「直接套機魂沒錯！訓練完整以後，幫機魂做出完善工具組，不讓他自由發揮，在你設定好的框架下活動」「轉換器還是需要，保險」。
  1. **EdgeAgent 的身分就是機魂**：換掉 Pi 的「expert coding assistant in pi」，由 EdgeAgent 擁有完整的系統提示（身分、看得到和看不到什麼、一律台灣繁體、先查再講、做不到就說）。
  2. **框架**：機魂只在開發機設計的工具組裡做事（每項工作有驗收條件，主機驗證後才交給主人），不自由發揮。主機給日期、唯讀由權限層擋、匯出是介面按鈕、新聞和事實由工具抓。
  3. **訓練**：27B 老師在**同一個框架**（同一份系統提示、同一組工具定義）裡解題，程式驗收過的才當資料，訓練 E4B 的 LoRA，和原版配對比較贏才上線。框架必須先定、再錄資料：訓練用的提示和工具定義要和實際使用一字不差，先訓練再改工具，訓練就白做。
  4. **簡體轉繁體轉換器**：當保險留著，放在輸出最後一關，每次觸發都記一次（看模型語言跑掉的次數，訓練後應該下降）。它不是修法；語言的修法在系統提示和訓練。
  5. 本質的弱點（沒查就講、沒交差、猜路徑）由提示和訓練修，不用一洞一補。不用雲端模型。
  - **機魂其實還沒訓練出來**：角色資料 v1–v5 全被擋，Agent 資料只有 55 列試跑。之前的狀態報告沒把這件事講清楚。
  - **未決（要問使用者）**：第一版工具組的內容（§3 第 2 步的清單）；改程式的工作（E4B 考場 12.2%、Qwen3.5-4B 37.8%）要不要放進機魂的框架；EdgeAgent context 改 32K。

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

1. **筆電第 5 回合**：看 `laptop-report` 的報告，重跑筆電的 commit 和測試，照 §4 規則 13 評分。
2. **定框架**：機魂的工具組（使用者確認清單）和它的系統提示一起設計。候選：新聞整理（今天、N 則、附時間和連結）、上網研究附來源、檔案查詢（唯讀）、檔案整理（預覽→批准→執行→驗證，刪除只封存）、開發日常唯讀（找功能、解釋測試失敗、寫 commit 訊息：要可證明唯讀的 git）、機器語言翻譯、MCP（台股、無人機模擬、LibreOffice、瀏覽器）、推演儀式。
3. **框架的評測**（放進沙盒；現在 `bench/mcp_eval.py`、`bench/grill_eval.py` 在主機上跑 Agent，違反 §4 規則 2，要先搬進容器）：合成題含使用者紀錄裡的情境（自我介紹、今天 N 則新聞、匯出要求、先查再講、簡體輸出）和每項工具的工作；網路用錄好的回應。量原版 E4B 當基準。
4. **訓練**：老師在框架裡解題（試跑一題平均 389 秒；414 題各跑一次約 45 小時），程式驗收過才留，訓練 LoRA，配對比較贏才上線。角色台詞另查 v5 輸給學生的原因（不降門檻）；有 LoRA 套在 `task` 時重量 `scripts/dev/task_scope_eval.py`。
5. **轉換器**：輸出最後一關的簡轉繁（只轉含簡體字的段落，程式碼不動），觸發次數進 log 和評測。

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
