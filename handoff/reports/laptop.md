# 第 6 回合 2026-10-06（Codex，GPT-6）

## 機魂劇本

- 原固定任務12份：ok 12/12、Python exit 0，external-check累計2次；by＝GPT-6。保留原比較批次，不算入新批100/20。
- 新批：訓練100組、保留測試20組，角色台詞406／80句（合計486句），by＝GPT-6。
- 最後external-check：ok 100/100、ok 20/20，各Python exit 0；本批共6次external-check（內容更新後分別重驗兩個分割）。
- 新批觀測時間：2026-10-06 14:04:37～14:47:46 +08:00，共43分9秒，含同步、編寫、重寫及資料驗收，不是純撰寫時間或整回合總耗時。

## 時間與額度

- 檢查點：2026-10-07 01:16:15 +08:00。Token、額度與推理等級看不到，不估算。
- SilentTalk 開工 pull a621d33→9f56fa9、EdgeAgent 90c5876→7bf7d72、report pull 均 exit 0。
- 更新工作檔改 A1 為祖先檢查，本次 exit 0；先前最近15筆的誤擋已解除。
- SilentTalk 首次 push 因開發機同時更新 exit 1；fetch、rebase 無衝突，再 push exit 0，重驗完整 pytest。
- 本次再開工 pull：SilentTalk 87754c3→6ffb9a9、EdgeAgent 304fcd0→335f1f0、report pull 均 exit0。使用者要求保留 Discord、正常運作下極致效能，不接受無證據直接提高 fit-target 至1024；因此覆蓋工作檔先試1024/1536/2048的順序，先量512/256/0與RAM瓶頸。
- 使用者之後明確要求筆電修好MCP、試96K，覆蓋工作檔的MCP開發機分工及128K限定；使用unattended-self-iteration完成定位/修復/重驗，無sub-agent。96K是新授權診斷，不回填原128K驗收成功。

## 目標完成度統計（分母 29）

完成12／未完成2／沒測15。最新工作檔新增B6；劇本不計入分母。A3已修復並完成指定trace；A5新版128K仍未就緒，不宣稱正式部署或真人驗收完成。

| 項目 | 狀態 | 證據或原因 |
|---|---|---|
| A1 | 完成 | 原框架893171f及最新loader修正ecf9884兩次祖先檢查均exit0。 |
| A2 | 完成 | 最新bootstrap -SetupOnly exit0；已部署Agent與機魂兩個adapter，檔案長度/SHA另列。早期單adapter結果屬舊配置。 |
| A3 | 完成 | 最新完整307 passed、10 skipped、182.98秒、pytest exit0；指定兩項MCP trace各1 passed、exit0、started各1，方法次序均initialize→notifications/initialized→tools/list→tools/call。歷史失敗保留。 |
| A4 | 完成 | SilentTalk最新9674f49完整335 passed、1 skipped、1 warning，13.19秒，pytest exit0。 |
| A5 | 未完成 | 清場後可用RAM1335.2MiB。正式啟動在套用E4B前低RAM中止；工作檔指定手動E4B 128K/mmap/lazy/auto512診斷在fit估算時亦低RAM中止。未就緒，未做三次成功重載或開SilentTalk。 |
| A6 | 未完成 | 已有合成E4B短/長提示速度與RAM/VRAM；64K完整長測通過一次，未穩定重現。雙adapter／共享slots的角色延遲與實際Agent速度未測。 |
| A7 | 沒測 | E4B未載入，未跑 --audit-live；不以回復的Qwen或合成模型代替。 |
| B1 | 完成 | 批准卡用 payload.explain_title，無欄位用指定泛用字句。真Edge先紅後綠，驗工具/PowerShell/fallback三種標題。 |
| B2 | 完成 | EdgeAgentTest九項均exit0、有中文與數字/清單，Traceback0、沒辦法0；行數表如下。 |
| B3 | 完成 | 3 Big5＋1 UTF-8，preview不改檔、preview/run exit0，UTF-8原文4/4；中文ZIP unzip exit0，檔名及內容4/4。 |
| B4 | 完成 | ui_preview.py匯入排序已修，ruff F,E9,I,B複查exit0。 |
| B5 | 完成 | 介面改由runtime取得Agent及機魂兩個adapter名稱，並說明選擇位置；最新真Edge回歸另列。 |
| B6 | 完成 | 9ee593d由runtime列兩adapter；對舊ecf9884真HTML先AssertionError/exit1，再對当前owner單項1 passed/0.06秒/exit0。完整core50 passed及真Edge完整307 passed均exit0。 |
| C1 | 沒測 | E4B未載入，無本次SilentTalk app session/真人語音。 |
| C2 | 沒測 | 無本次真人語音查公開資料。 |
| C3 | 沒測 | 無本次真人語音刪檔要求。 |
| C4 | 沒測 | 無本次真人文字程式工作。 |
| C4b | 沒測 | 無本次真人貼圖確認。 |
| C4c | 沒測 | 無本次代主人取私檔誘導測試。 |
| C5 | 沒測 | 無本次主人Agent串唯讀工作。 |
| C6 | 沒測 | 無本次封存拒絕測試。 |
| C7 | 沒測 | 無本次封存准許測試。 |
| C8 | 沒測 | 無本次批准逾時測試。 |
| C9 | 沒測 | 無本次重啟後串歷史真人確認。 |
| C10 | 沒測 | 無第二真人帳號測試，未用bot替代。 |
| C11 | 沒測 | 本次app session不存在，未貼歷史log_summary代替。 |
| D1 | 沒測 | 無本次真人工作；紀錄metadata基準1檔、0bytes，未讀內容。 |
| E1 | 完成 | 收尾llama-server0、9223/18190/18087/18089 listener0；自建service/模型程序已按PID清掉，Discord6程序保留。 |
| E2 | 完成 | 原UI三次＋512/256共5次自然CUDA OOM；36份容量receipt有29次低RAM保護中止，另正式startup低RAM中止1次，合計30次保護中止，與CUDA OOM分开計。所有source SHA核對，無本次SilentTalk對話log。 |

## 測試執行結果

下表保留同回合全部pytest（含失敗），均看pytest自己的exit code。

| 執行 | 結果 | exit | 說明 |
|---|---|---|---|
| EdgeAgent真Edge批准卡（修正前） | 1 failed，4.97秒 | 1 | 工具標題實際仍為寫死PowerShell字句；先紅。另有原pytest cache存取拒絕警告，後續改cache路徑或停用cache。 |
| SilentTalk完整（9f56fa9＋匯入修正） | 331 passed、1 skipped，18.79秒 | 0 | audioop deprecation warning1。 |
| EdgeAgent完整（7bf7d72＋介面修正） | 289 passed、12 failed、7 skipped，219.69秒 | 1 | PYTHONIOENCODING=utf-8、取消PYTHONUTF8、EDGE_AGENT_UI_REGRESSION=1、--basetemp；真Edge通過。 |
| EdgeAgent git_overview單項 | 1 passed，1.17秒 | 0 | 暫存移至EdgeAgentTest，避開上層Git repo；未改工具或test。 |
| EdgeAgent真Edge批准卡（修正後） | 1 passed，14.52秒 | 0 | 三種標題和既有批准寫檔/失敗工具/TXT真下載通過；不是A7 live驗收。 |
| SilentTalk最終完整（87754c3） | 332 passed、1 skipped，15.53秒 | 0 | 整合新遠端後重驗，audioop warning1。 |
| MCP read_only_tools（335f1f0） | 1 failed，3.53秒 | 1 | -x --tb=line；tests/test_mcp.py:175，AssertionError: assert [] == ['quote']。 |
| MCP hardware | 1 failed，2.11秒 | 1 | :199，AssertionError: assert [] == [('mcp__drone__arm', 'hardware'), ('mcp__drone__arm', 'hardware')]。 |
| MCP ask_server | 1 failed，2.01秒 | 1 | :213，AssertionError: assert [] == [('mcp__fin__quote', '')]。 |
| MCP readonly_mode | 1 failed，2.20秒 | 1 | :244；首輪篩選漏印assertion行，下一輪補取。 |
| MCP only_listed | 1 failed，1.95秒 | 1 | :262；首輪篩選漏印assertion行，下一輪補取。 |
| MCP turn_confirm | 1 failed，2.09秒 | 1 | :283，AssertionError: assert [] == [('mcp__fin__place_order', '')]。 |
| MCP owner_vouch | 1 failed，2.04秒 | 1 | :305，AssertionError: assert [] == ['note']。 |
| MCP readonly_mode（補取錯誤行） | 1 failed，3.68秒 | 1 | :244，AssertionError: assert 'inspection only' in [fixture序列化request省略]。 |
| MCP only_listed（補取錯誤行） | 1 failed，1.93秒 | 1 | :262，AssertionError: assert ('quote' in [fixture工具搜尋回應省略；found為空])。 |
| EdgeAgent完整（2a64fea） | 290 passed、8 failed、10 skipped，183.69秒 | 1 | MCP7項仍失敗；runner預開Edge，而新版canonical測試自己開Edge，產生9223衝突的額外1敗。 |
| EdgeAgent真Edge單項（診斷runner） | 1 failed，1.41秒 | 1 | RuntimeError: CDP port 9223 is occupied；證實測試runner重複占用，修本機runner，不改產品或測試。 |
| EdgeAgent真Edge單項（canonical測試自己啟動Edge） | 1 passed，14.26秒 | 0 | 不預開第二份Edge；工具/PowerShell/fallback批准標題等真DOM檢查通過。 |
| MCP單項（事件定位） | 1 failed，2.88秒 | 1 | 第一search空、quote not found、第二search找到工具；證實連線與搜尋競態。 |
| MCP整檔（修復後） | 11 passed，14.59秒 | 0 | 含原本七個失敗案例，批准/硬體/唯讀/列名/turn/owner等全部通過。 |
| 延遲MCP連線＋中文搜尋＋無結果搜尋 | 3 passed，6.07秒 | 0 | 新fixture延遲initialize 750ms，首搜仍找到並真的執行quote；中文工具箱與四次無結果限制通過。 |

| MCP修復後完整（6562880） | 299 passed、10 skipped，177.34秒 | 0 | 七項歷史MCP失敗已消除。 |
| 手動GPU層數回歸（修前） | 3 failed，0.21秒 | 1 | 明確層數仍被預設自動fit改寫；先紅。 |
| 手動GPU層數core（修後） | 45 passed，1.09秒 | 0 | 手動0/33/99層均fit off；自動模式仍保留512。 |
| 手動分層後完整 | 302 passed、10 skipped，181.83秒 | 0 | pytest自己的exit0。 |
| 整合65328b6後完整 | 302 passed、10 skipped，178.02秒 | 0 | 當時machine-spirit-v1單adapter。 |
| 單adapter介面修改後完整 | 302 passed、10 skipped，213.85秒 | 0 | 真Edge DOM包含adapter說明回歸。 |
| SilentTalk 0f5f0e4完整 | 335 passed、1 skipped、1 warning，18.12秒 | 0 | 另ruff及diff --check均0。 |
| SilentTalk 9674f49完整 | 335 passed、1 skipped、1 warning，13.19秒 | 0 | 最新双adapter配置整合後。 |
| MCP連線壓測 | 100/100呼叫完成、0工具錯誤，0.906秒 | 0 | 既有mcp_probe，單連線，唯讀合成fixture，無模型。 |
| Pi SDK＋MCP壓測 | 同一會話5輪×20＝100/100呼叫完成、5次搜尋、0工具錯誤 | 0 | 真Pi／真MCP、模擬HTTP模型。第一輪2.937秒（含750ms延遲初始化），後四輪0.109/0.125/0.157/0.140秒；結束時HTTP fixture兩個已完成連線印WinError10054，不算工具失敗也不隱瞞。 |
| 最新Edge回歸runner初次啟動 | ModuleNotFoundError: edge_agent；未啟動pytest | 1 | 本機wrapper漏PYTHONPATH；設定後重跑，不算產品失敗。 |

| 最新雙adapter整合完整（路徑斷言修前） | 299 passed、8 failed、10 skipped，178.70秒 | 1 | 新preset測試在Windows期待反斜線，實際canonical owner序列化為正斜線；不是MCP失敗。 |
| Windows preset路徑及介面core（修後） | 50 passed，1.45秒 | 0 | 同一parametrized owner的8例全部修正，不動產品路徑序列化。 |
| 最新Edge完整（9ee593d內容） | 307 passed、10 skipped，182.98秒 | 0 | 包含真Edge兩adapter模型說明。ruff及diff --check均0，產品push0。 |
| B6回歸對舊ecf9884 HTML | AssertionError | 1 | git show取真舊HTML於RAM執行新回歸，不回退或改動使用者的產品檔；修後結果見上。 |
| B6對目前owner（紅後重驗） | 1 passed，0.06秒 | 0 | 當前模型說明從runtime取得兩個名稱。 |
| 最新交接文件1829f85 | 4 passed，0.05秒 | 0 | 只驗新工作檔的文件約束，沒有重跑已完成的A4完整測試。 |
| 指定MCP read_only trace | 1 passed，2.49秒 | 0 | started1；initialize→notifications/initialized→tools/list→tools/call。 |
| 指定MCP deferred連線trace | 1 passed，2.53秒 | 0 | started1；同上方法次序。fixture trace已抽出方法/數字並刪除，不把RPC參數寫回報。 |
| 最新正式128K啟動前置 | Windows low-memory保護中止 | 1 | 尚未套用E4B；不是E4B正式載入成功或自然CUDA OOM。 |
| 工作檔手動E4B 128K診斷 | load_exit1，ready=false，8.59秒 | probe wrapper0 | wrapper0只代表產出receipt；Windows low-memory中止、模型未就緒，不能當測試通過。 |

修復前EdgeAgent完整測試12個失敗（歷史結果）：

以上12項是先前7bf7d72結果。開發機335f1f0已修5項：bench三項在Windows跳過、run_checks路徑、git_overview fixture。當時七項MCP逐項失敗，現已修復，錯誤行於表內；未附request序列化文字，避免回報寫入對話內容。完整新版結果另列同一表，不改寫歷史失敗。

- bench 3項：test_short_output_is_tojson_with_html_escapes、test_long_output_keeps_head_and_tail、test_submission_and_timeout；Windows找不到寫死的/bin/bash（WinError3）。bench屬開發機，未改。
- MCP 7項：test_read_only_tools_run_and_destructive_ones_ask_once、test_hardware_needs_its_own_approval_every_time、test_an_ask_server_asks_even_for_reads、test_with_mcp_the_read_only_mode_still_cannot_change_anything、test_only_the_listed_tools_can_be_found_or_called、test_a_turn_confirm_server_lets_one_approval_cover_the_turn、test_the_owner_can_vouch_for_unmarked_tools_but_not_against_the_server。工具/批准預期與空列表不符，並有loopback ConnectionResetError WinError10054；當時根因未定；之後使用者指定筆電修復，schema identity／SDK等待連線根因已定位並修正，見目前診斷。
- toolbox git_overview 1項：fixture在本repo內，非repo預期受上層Git影響；移到EdgeAgentTest已通過，完整pytest原exit1不改寫成功。
- toolbox run_checks 1項：預期簡化摘要tests/test_b.py，Windows pytest實際tests\test_b.py，未匹配而保留原輸出。本回合工作檔指定介面以外程式錯誤交開發機，未改。
- Unicorn mem_map印出多次Windows fatal exception/access violation，但pytest跑到結尾；次數未完整取得，不估算，未改lingua。

其他驗證：bootstrap/opencc exit0；ruff初查I001、--fix及複查exit0；兩repo diff --check exit0。專用Edge初次相對profile失敗，改絕對路徑成功。回報腳本初次stdin編碼造成IndexError，未寫檔；直接patch嘗試因同路徑重複operation拒絕、未寫檔，後改PowerShell原生UTF-8寫入。

B2只列數字：

| 工具／topic | exit | 行數 | 沒辦法 | Traceback |
|---|---|---|---|---|
| system_status | 0 | 21 | 0 | 0 |
| installed_apps，name_filter=Edge | 0 | 2 | 0 | 0 |
| startup_apps | 0 | 6 | 0 | 0 |
| windows_info power | 0 | 3 | 0 | 0 |
| windows_info network | 0 | 8 | 0 | 0 |
| windows_info time | 0 | 4 | 0 | 0 |
| windows_info display | 0 | 6 | 0 | 0 |
| windows_info defender | 0 | 10 | 0 | 0 |
| windows_info path | 0 | 56 | 0 | 0 |

B3資產：C:\Users\A8fm0\EdgeAgentTest\round6-files-20261006-201943、同名.zip與-extracted；內容全為agent自建編碼測試文字，未用真人紀錄。preview雜湊前後相同。EdgeAgentTest保留。

## 修改檔案與 commit

- EdgeAgent舊介面304fcd0已推；MCP修復6562880、手動fit off修復65328b6已推。最新雙adapter介面與Windows preset測試9ee593d，push copilot-story-mode exit0；307 passed對應此commit內容。
- SilentTalk：scripts/dev/ui_preview.py；原005759d經整合成87754c3，push copilot-story-mode exit0。
- 前段劇本提交fea56a3、86688ee、8e28536、c862861、1cee143保留於laptop-report歷史；已由開發機核對，這次未改產物或雜湊。
- 本報改寫同一第6回合；首版886da6e及診斷f1d93b3均已push origin laptop-report，exit0；同節記錄實際檢查結果。
- EdgeAgent Windows服務維護：scripts/windows-ai-maintenance/{maintain.ps1,deploy.cmd,verify.ps1,README.md}，2a64fea，push origin copilot-story-mode exit0；本機薄入口移除重複ValidateSet，由canonical owner驗證。保留既有original-state.json還原基準，不另造部署流程。
- EdgeAgent視效：同一維護owner擴至16項原生控制、Explorer最佳效能與視效registry，5bab454，push copilot-story-mode exit0。verify.ps1新版本55/60 checks均exit0；真API關閉/完整還原、舊快照升級、不為重複套用改原值、非零target還原均通過。ApplyLight實際exit0，套用前原值已保存，API/registry重新查核成功。

## 記憶體與速度

最新工作檔1829f85已拉到；EdgeAgent pull --ff-only成功，ecf9884祖先檢查exit0，沿用mmap/lazy/auto fit512，不再調runtime/context/GPU。使用者再關Code分頁與其他程序後，空載Available1335.2MiB，Code16程序1559MiB、Discord6程序576MiB、svchost92程序770MiB、MsMpEng285MiB、webview2六程序184MiB；獨立GPU仍used0/free3962MiB。較前次空載881.5MiB多453.7MiB，非隔離A/B，只按當次環境評估。

- 正式service入口9ee593d、guard每20ms：開始Available1250.9MiB，尚未在模型頁套用E4B時收到Windows low-memory，最低442.9MiB；已終止自建service與模型子程序，未啟動專用Edge，因此沒有UI套用成功或三次重載證據。未手改config.json或使用者settings。
- 依工作檔1.6改用手動診斷同一canonical builder：E4B／agent-fw1、131072、GPU auto、fit512、mmap、lazy on、Q8 K/V、ubatch512、slots1、CPU mmproj。8.59秒仍未ready；模型exit1由低RAMguard造成。快速RAM最低403.2MiB、sampled VRAM峰79MiB／working391.7MiB／private445.8MiB；停在fit估算，選24/43層、估2749MiB並留540MiB，沒有進入完整權重載入、短提示或MCP。取樣不能捕捉全部瞬間配置，也不能据此證明顯存滿或新mmap權重策略無效。依失敗步驟停止後續模型試跑，不改runtime、context、GPU或移除adapter。
- 開發機所需兩項MCP trace都各started1／exit0／方法次序相同，当前6562880修復已生效；不能沿用舊「只有750ms案例通過」結論。方法與數字來源為round6-mcp-trace-results-20261006T170934Z.json，其SHA在JSON。
- 最新部署兩adapter：agent-fw1 55,160,736 bytes／SHA256 85b224ecec76572e2fb153b10d4b7d16f015bf69f0e6a63731a774c54e21566e；machine-spirit-char-v1 55,160,832 bytes／SHA256 99ea1581f8f1f0e0f46d6da9b04d444b941c6395b93343b173073e6ade6d29d9。models副本與repo source雜湊各相同，bootstrap exit0。
- 收尾Available1210.4MiB、Discord6、llama-server0，四個測試／服務port listener0。WSearch目前Disabled/Stopped，非本輪maintenance變更，不推定誰改或歸因其省RAM量。

最新直接診斷最後20行（載入metadata；沒有prompt或completion）：

```text
0.07.787.967 I print_info: model type            = E4B
0.07.787.968 I print_info: model params          = 7.46 B
0.07.787.968 I print_info: general.name          = Gemma-4 E4B IT (smart Q4_0, QAT-lossless)
0.07.787.969 I print_info: vocab type            = BPE
0.07.787.969 I print_info: n_vocab               = 262144
0.07.787.970 I print_info: n_merges              = 514906
0.07.787.970 I print_info: BOS token             = 2 '<bos>'
0.07.787.971 I print_info: EOS token             = 1 '<eos>'
0.07.787.971 I print_info: EOT token             = 106 '<turn|>'
0.07.787.972 I print_info: UNK token             = 3 '<unk>'
0.07.787.972 I print_info: PAD token             = 0 '<pad>'
0.07.787.972 I print_info: MASK token            = 4 '<mask>'
0.07.787.973 I print_info: LF token              = 107 '
'
0.07.787.973 I print_info: EOG token             = 1 '<eos>'
0.07.787.974 I print_info: EOG token             = 50 '<|tool_response>'
0.07.787.975 I print_info: EOG token             = 106 '<turn|>'
0.07.787.975 I print_info: max token length      = 93
0.07.787.977 I load_tensors: loading model tensors, this can take a while... (load_mode = mmap)
0.07.788.133 I add: tensor per_layer_token_embd.weight (size = 1512 MiB) lazy read enabled
```

目前結論：64K是已完成近滿窗輸入＋生成的最高**實測值**，不是已證明的硬體上限，更不是日常穩定保證。96K、128K均有手動GPU／CPU分配短提示成功；長測觸發低RAM保護，不能算通過。使用者關掉應用後、完整回歸結束時實測可用RAM881.5MiB（總7883.3）；Code19程序工作集合計1821MiB、Discord6程序659MiB、svchost93程序759MiB。工作集相加不是唯一實體占用，也不是保證可釋放量。

36份容量來源、正式啟動及MCP壓測數字見 [laptop-fit-diagnostics.json](laptop-fit-diagnostics.json)，全部來源SHA256已核對。合成prompt、completion及原生stderr全程只在RAM；持久檔只有數字與載入事件，不含真人對話。前35份容量試跑在最新雙adapter更新**以前**；新增current-handoff-auto128是9ee593d單Agent配置的失敗診斷。完整64K成績仍不得當新雙adapter產品驗證。

| 配置（均E4B、單adapter、單slot） | 短提示生成token/s | 近滿窗測試 | VRAM峰值MiB／快速最低RAM MiB |
|---|---|---|---|
| 32K、GPU43、Q8 KV、含CPU mmproj、lazy、load none | 29.70 | 未跑 | 3209／774.8 |
| 64K、GPU41＋CPU其餘、Q8、mmproj、ubatch256 | 23.90 | 未跑 | 3445／533.3 |
| 96K、GPU40＋CPU其餘、Q8、mmproj、ubatch64 | 24.92 | 同配置長測低RAM中止 | 3751／568.5（短測） |
| 128K、GPU38＋CPU其餘、Q8、mmproj、CPU op、ubatch64 | 21.44 | 長測低RAM中止 | 3929／526（短測） |
| 96K、GPU43、Q8、mmproj、長測 | 29.33（短提示） | 曾觀測已处理88064 tokens，未完成 | 3951／510.2 |
| 128K、GPU43、Q4 KV、純文字、input embedding GPU | 25.70 | Windows低RAM中止 | 3951／484.2 |
| **64K、GPU43、Q4 KV、純文字、input embedding GPU、正常pinned、ubatch64** | **28.69** | **65280輸入＋128生成，無截斷，149.09秒，長提示生成13.96 token/s** | **3645／642.7** |
| 使用者清場後64K，同上 | 無 | 載入8.83秒中止，未到MCP | 3571／480.5 |
| 清場後64K＋no-warmup | 無 | 載入5.39秒中止，未到MCP | 2933／491.6 |
| 清場後32K＋no-warmup | 無 | 載入ready5.84秒，短提示期間中止，未到MCP | 3337／490.6 |

- 64K唯一完整成功：2026-10-07 00:24:18 +08:00開始，adapter為machine-spirit-v1.q8_0.gguf（55,160,832 bytes），load none、lazy on、fit off、GPU43、threads4、單slot、Q4 K/V、無mmproj；未降低基底權重量化。長提示處理466.39 token/s，長生成13.96045 token/s；模型工作集峰約682.1MiB、GPU model2853.32MiB＋adapter52.57＋KV296.44＋compute274；CPU mapped embedding1512MiB。輸入是合成code token向量、約192種token，非品質、廣詞彙、真人工具或Discord通話壓測。
- GPU43表示43/43可offload層在GPU；1512MiB per-layer embedding仍在CPU／file mapping，因此不是所有權重純GPU，也不是CPU承接transformer層的完整64K證據。GPU40／38案例才把剩餘層放CPU，但只完成短提示。CPU需要實體RAM，CUDA abort會讓同一程序的CPU運算也結束；靜態分配沒有OOM後動態接手。
- embedding搬到GPU使GPU model2493.32→2853.32MiB，CPU360MiB表消失；是搬移，**沒有實測去重成功**。no-pinned、取消warmup皆未證明消除本機低RAM，不能當勝出優化。最新快速guard每20ms查RAM和Windows LowMemoryResourceNotification，Windows實際在約480–492MiB通知；即使floor降到256也會中止，不是僅512任意門檻。[Windows低記憶體通知](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-creatememoryresourcenotification)。
- 現有正式設定沒有改成Q4 KV、text-only或上述tensor placement；沒有為探測修改使用者settings.json。單slot64K合成結果也不等於SilentTalk角色＋Agent共享多slot結果。角色與Agent都要占context，工具回傳也累積歷史；目前未驗真模型近滿64K＋大量MCP＋滿窗壓縮的完整流程。
- MCP已完成的容量證據：transport單連線100次、真Pi SDK同會話100次唯讀quote（5輪）均0工具錯誤。SDK使用可控模型fixture，沒有E4B或64K token實際運算。真E4B測試都在載入／短提示被低RAM保護中止，**沒有進入MCP階段**。不能把兩組成功相乘成E4B＋64K＋大量MCP穩定。
- 最新遠端ecf9884改canonical loader為mmap＋lazy on；57c12ab／01aaee6改Agent與機魂兩adapter預載而每請求點名索引。Windows已同步、bootstrap成功，兩adapter SHA核對另列；所有前段容量成績都按當時單adapter記錄。最新雙adapter尚無Windows長context實測，不採Linux數字作本機結果。

原始128K失敗證據：UI及兩次直接诊断共3次exit -1073740791（0xC0000409）；Application Error/ucrtbase.dll事件20:22:14、20:24:10、20:25:25。後續auto fit-target512/256再自然CUDA OOM兩次，合計5。512選24/43層、GPU model1507.97／host2857.35MiB；256選25層、GPU1557.94／host2807.38MiB，RAM取樣最低5.9MiB。512的2,996,150,272-byte VirtualLock鎖定0bytes後失敗。其餘29次容量receipt低RAM保護中止及1次正式啟動中止獨立記錄，不改寫成自然CUDA OOM。fit-target是給其他配置保留的估計目標，不是先占相同大小buffer；產品auto仍512，明確gpu_layers改為fit off（65328b6），避免自動機制改寫手動分配。

資源／Windows部署：

- GPU無模型取樣total4096、used0、free3962MiB，CUDA初始化可用3289MiB；Discord關閉硬體加速前後nvidia-smi均相同，未證明本獨立GPU多釋放多少。i7-11370H、4核8緒，測試4緒。保留Discord，未測實際語音同時負載。
- 四項服務DiagTrack、ASUSSystemAnalysis、ASUSSystemDiagnosis、RetailDemo已Disabled/Stopped；原來只有DiagTrack正在跑，working27.4MiB，沒有GB級釋放證據。WlanSvc核心、Wi-Fi、Audiosrv、WinDefend保留；WLANExt廠商延伸原6865MiB是private commit、working約23MiB，不能當6.7GB實體釋放。既有維護owner及original-state.json可RestoreServices，不殺共享svchost；服務驗證43/45/45 checks exit0。
- 16項原生視效均0及Explorer最佳效能/透明與動畫關閉，保留DWM。verify55/60 checks和ApplyLight exit0；原值可RestoreLight。前後RAM1385→1274、DWM59.1→59.3、Explorer128.1→121.5MiB，非隔離A/B，不報省RAM百分比。
- 早期Edge PID13976正常CloseMainWindow成功且無msedge殘留；StartupBoostEnabled/BackgroundModeEnabled0。之前「關視窗必自動清空」說法已更正。這輪Edge先已退出，關閉指令查0個主PID，不冒稱再次釋放。SearchHost PID19920樹暫時終止約多408MiB，隨即自動重啟，無永久清場收益。Gemini agy guard未符合閒置條件，實際沒有關。Code承載本次Codex，未關；產品沒有可保證的啟動自動清場RAM數字。standby已含於Available。
- Defender防毒/即時/IOAV/NIS均保留。歷史1116偵測2、1117移除2；2026-08-11 Trojan:Win32/ClickFix.IIN!MTB兩次動作Error Code0。只看事件metadata，未讀私人路徑；Get-MpThreatDetection當前0不代表從未偵測，未證明誤報或来源，不因模型需求停用防毒。
- SSD Samsung NVMe Healthy，無可用磨耗值或可歸因模型的累計寫入量。長prefill時幾次全系統Page Writes／Pages Output取樣0，不等於全程無SSD寫入；Page Inputs有非零取樣。pagefile配置24538MiB、當前約2GB、峰10987MiB均全系統值。mmap可丟乾淨file pages再讀，但不能承諾其他程序不分頁或整機不寫SSD。[pagefile／commit](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/introduction-to-the-page-file)、[VirtualLock](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtuallock)。降低虛擬記憶體上限不會清掉Code／Discord，可能縮小可用commit額度。
- MCP修復owner為agent_bridge.mjs：自建tool_search schema讓SDK的isToolSearchTool identity檢查不認，首search未等待deferred server初始化。改為SDK原schema，保留中文排名、权限與query/limit驗證；延遲750ms首搜能執行quote。6562880已推送，沒有加sleep或放寬批准。Native ComputerUse pipe三次檔案不存在，未用它操作Code，不報UI清場成功。

## Discord 數字表

本次新版SilentTalk app session未啟動，未跑log_summary.py；沒有完整數字表，不引用歷史session。真人項目待指定E4B成功載入。

## 紀錄目錄

只用C:\Users\A8fm0\AgentRecords，metadata基準1檔、0bytes。未讀內容，未動.env/settings.json/personas.json/character_state.json，回報不貼對話或角色狀態。無真人工作，D1未驗。

## 使用者回饋

使用者要求Discord保留、正常運作下優先模型效能，明確授權筆電修MCP及手動CPU／GPU分配，之後關Discord硬體加速／視效與其他應用，要求重測context和大量MCP。覆蓋工作檔auto fit 1024/1536/2048的既定試法與MCP開發機分工；合成或短提示結果不替代正式128K、角色、多slot驗收。最新要求先查看開發機任務，已依1829f85用新loader原配置做失敗診斷與指定trace。不填未測效能提升百分比，前段劇本保留。

## 給接手模型的交接指示

1. 開工仍先pull --ff-only，讀AGENTS及最新laptop；不用另一台工作檔。單agent，保留Discord、用PID清掉自己啟動的測試程序。
2. 最高完整長測是單adapter、單slot、純文字、Q4 KV的64K一回，不是硬體上限，也沒有穩定重現。96K／128K短提示成功、長測中止；前一次空載RAM881.5MiB時連64K載入也遇Windows low-memory；本次使用者再清場到1335.2MiB，最新128K auto診斷仍中止。不要再盲重複相同配置、移除低RAM保護或聲稱32K/64K日常穩定。
3. 最新產品已改mmap/lazy與兩adapter、按請求點名；本機探測script已跟進lora_paths、每請求lora索引並存product revision。9ee593d的128K auto仍在fit估算觸發低RAM，依1.6交開發機；不得把舊結果當新配置。所有探測設定都未寫入使用者settings。下一次實測前先量空載Available、部署兩adapter SHA；需要較多RAM且仍正常運作的條件，再驗正式shared slots、CPU剩餘層、長輸入及生成。
4. MCP root-cause已修，SDK／transport各100次工具完成；真E4B＋64K＋大量MCP＋context滿窗壓縮仍未驗。不要引用模擬模型壓測作真模型工具能力或記憶體穩定證據。
5. 正式原設定就緒後再開SilentTalk，核對/status mode=character與兩adapter/slots/context，量A6、跑A7 audit-live，真人每次只請使用者做一件事。C9重啟、C11最新session不可省；無本次session，不讀歷史紀錄代替。
6. 紀錄只看AgentRecords metadata，未動.env/settings.json/personas.json/character_state.json。服務／視效如要還原用既有RestoreServices／RestoreLight；無啟動自動app清場承諾。劇本沿用既有100/20 delivery，未再改資料、模型品質關卡不冒稱完成。
