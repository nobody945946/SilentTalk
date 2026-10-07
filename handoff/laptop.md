# Windows 工作檔：第 6 回合（續）

更新：2026-10-07｜程式 copilot-story-mode｜回報 laptop-report

## 最新使用者要求與停止點

使用者原意是主要 Agent 可用完整64K，只有 Agent 閒置時才把同一模型借給 Discord 角色；不是永久切成角色16K×2＋Agent32K。先前固定切分的決策已撤回。AI保持啟用、失敗自行恢復；Discord連線與手動打字發聲獨立；compact後同任務續跑，不重做工具。巨檔從責任所在拆開，不加parent引用或legacy re-export。

使用者最後說token快用完：停止非必要工作，告訴他如何手動操作，agent只完成必要修正、驗證與完整交接push。**本次不再替使用者重啟，不再壓測。** 下一次須依他最新指示接續；不重新執行舊128K驗收。

## 開始與有效來源

同機只開一agent；先在SilentTalk `git pull --ff-only`，失敗停止回報；再在 `C:\Users\A8fm0\EdgeAgent` 做同一指令。讀AGENTS與本檔即可。需要完整證據時讀既有report worktree `C:\Users\A8fm0\Downloads\SilentTalk-laptop-report\handoff\reports\laptop.md` 與同目錄laptop-fit-diagnostics.json；不讀另一台機器工作檔或任何使用者對話。

最新程式：SilentTalk7355d68；EdgeAgent285a30b為排程版本，另有最新「Name the model in router cache erase requests」修正commit，核對Git HEAD。此修正**尚未載入現行服務，未完成修正後實機HTTP驗證**。舊9bb3714／4694e29及固定切分證據在Git，不能當目前設計。

## 現況與必要錯誤

- 64K同一模型、1個實體slot，Agent slot0、context65536；GPU41、mmap/lazy/low_vram、雙adapter。角色要求的context值是借用時的prompt上限，不永久占用KV。
- 新InferenceGateway位於控制服務18087，Agent與SilentTalk都走它；上游模型router18089。角色借用者以owner PID表明租約；Agent由服務提供RAM內api key，不輸出key。
- Agent整個任務（含工具／批准／compact）持有推論租約。新工作先預約，等目前短角色生成結束；其後角色不可插隊。角色收到423 inference_busy保留最新pending、等待idle，不視為掉線；角色心事／摘要等待或保留再試。交接只擦除記憶體KV，不寫cache檔、不重載模型、不重啟Discord。
- 實機剛發現 cache erase POST的JSON缺少model，router回400「model name is missing from the request」。已在唯一owner edge_agent/inference.py改成 `{"model":"local"}`，回歸fixture強制檢查此欄。現在/status ready只是模型載入完成，**不能稱目前AI推論可用**；須重啟服務載入此修正，再做最小合成HTTP檢查。
- 當次snapshot：SilentTalk wrapper27176／app18912，建立UTC2026-10-07T02:16:29.5793390Z；Edge服務2020、router8644、model child21024。這是snapshot，接手關程序前必須重新核對PID、名稱及父子關係，禁止照抄過時PID殺程序。
- 此回正常bootstrap exit0，app載入7355d68。曾用/base歸還租約後/shutdown遭409：活著的SilentTalk自行重新租用；不能假裝服務關閉成功。程序樹動態強制重啟指令被工具安全檢查拒絕；改成核對後只停確定的服務PID成功，上游/models/unload成功。CLI start最後409是它試圖要求base、當時SilentTalk已租回character；實際新服務ready、1slot／Agent64K。但新服務仍是cache erase修正前版本。

## 使用者手動操作

使用者已決定自己操作。最後提供的立即操作是PowerShell：停掉此次核對過的Edge服務／router／model child，然後用 `edge_agent.api.ensure_service()`啟動；保留SilentTalk程序與Discord。不要用CLI start的request_base碰撞活角色租約，不停用AI，不修改四個使用者檔案。若不是本次即時操作，先重新查18087／18089 listener與llama child，核對歸屬後才用PID。

啟動指令（在EdgeAgent目錄）：

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent
.\.venv\Scripts\python.exe -c "from edge_agent.api import ensure_service; ensure_service()"
```

預期：/status mode character、ready true、owner_pid為仍活著的SilentTalk app、context_size65536、agent_slot0、inference_slots1、error空；router /props?model=local total_slots1／n_ctx65536。SilentTalk會自行重新取得租約。這只能驗模型與租約；修正後推論仍須實機驗證。

## 驗證與下一步

- SilentTalk完整361 passed、1 skipped、1 warning、14.76秒，exit0。
- EdgeAgent排程版完整323 passed、9 skipped、180.62秒，exit0；Unicorn mem_map仍印多次原生access violation，歸開發機，不在Windows改lingua。
- 真Pi SDK＋合成模型：32K直連與64K經gateway兩個參數均成功，2 passed／25.93秒；overflow→compact→同任務第二工具，各寫一次。
- 最後cache erase修正後，gateway／context／core目標63 passed／2.85秒，exit0；沒有重跑全套，因只改router POST model欄位，已由fixture覆蓋。
- 實機最小租用probe兩次失敗（各command exit1）：Agent開始時角色423符合預期，但Agent cache erase400；沒有生成成功或完成交還的實機證據。Probe只用新合成session／EdgeAgentTest，不讀使用者紀錄。
- 如使用者之後要求接續：先確認他已手動重啟、服務是否載入最新commit。必要時在 `.test-tmp/rental-smoke.py` 跑一次最小合成測試（腳本已在忽略目錄；若不在，照上面HTTP流程重建合成fixture，不讀紀錄）。預期Agent done1／error0、忙時角色423、結束後角色200，app與model PID不變。失敗從inference owner定位，不再試設定排列、全視窗壓測或下游補丁。
- 128K／目前64K近滿視窗性能未驗收；C1～C10及D1真人條件未確認；不得以SDK fixture、短prompt或/status ready冒充真人／滿context成功。現有29項分母仍13完成／2未完成／14没測。

## 架構與資料規則

五巨檔已拆，另把714行widgets.py拆成小元件；silenttalk應用Python沒有超過600行。Runtime排程另有reply_worker；中立conversation／persona／ai_options避免基礎UI／語音依賴AI。EdgeAgent service／chat及開發腳本仍有巨檔技術債，交開發機，不稱全repo已清完。

本次使用者授權覆蓋舊laptop檔對lifecycle／context／必要caller遷移限制。模型訓練／角色policy／lingua仍屬開發機。回報固定十節只改第6回合現況；每次pytest（含失敗）保留，commit／push兩程式到copilot-story-mode，回報到laptop-report；不可main commit。

不手改.env、settings.json、personas.json、character_state.json。紀錄只用 C:\Users\A8fm0\AgentRecords，只查數量／大小／時間，永不讀內容、不將對話或角色心事寫進回報。不增加root agent入口、備份或隱藏恢復hook。
