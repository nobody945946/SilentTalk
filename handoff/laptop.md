# Windows 工作檔：第 5 回合，目標式

更新：2026-10-06 凌晨（A4 已同意）｜開發分支 `copilot-story-mode`｜回報分支 `laptop-report`

你從 AGENTS.md 被分到此處，只照這份做。沿用第 5 回合和 34 項，不新增回合或累加回報歷史。開始先 git pull --ff-only；失敗就停止。接手先讀既有 worktree `C:\Users\A8fm0\Downloads\SilentTalk-laptop-report` 的 `handoff/reports/laptop.md`，從最後檢查點續做。程式與測試可按目標自行查既有 owner；Windows／介面／紀錄設定由筆電負責，模型／Agent 工具與角色邏輯交開發機。

## 已拍板的現況

- 機魂是預設內建角色 Machina-Prime-09A，啟動是角色模式、AI 誠實度為機器角色。角色／Agent 的呼叫和權限規則照現有程式；本回合不重寫開發機的角色與工具邏輯。
- 使用者同意 E4B、context 131072、工作記憶目標 131072、GPU 自動、省 VRAM 開、CPU/GPU 共用，接受角色慢。模型須使用既有 mlock 設定，提示快取每模式上限 256 MiB；載入失敗如實報告，不擅自降低設定。
- 2026-10-06 使用者拍板：原生 SSD 不需加密，直接用一般紀錄目錄。取消容器、分割、密碼、解鎖與專用磁碟代號的要求；不再請使用者確認是否取消加密。兩 app 共用 `C:\Users\A8fm0\AgentRecords`，只存文字，不存錄音。AGENTS.md 的紀錄規則是唯一依據。
- 日常 EdgeAgent 不開 VS Code，Discord 保留；使用者關普通 Edge 很方便，關注它是否背景殘留。Edge 背景執行與啟動加速的既有持久 policy 值均為 0；不擅自強制退出目前編輯器或普通瀏覽器。獨立關窗測試曾被 automatic approval review 拒絕，未執行，不換工具重包重試。
- 使用者表示測試暫存不清理也沒關係：保留，不再請他執行刪除命令。測試資料夾 EdgeAgentTest 保留。
- A4 重載：使用者 2026-10-06 在開發機回答「可以」：重載 EdgeAgent 和 SilentTalk（會清掉 RAM 裡的對話）並套用 E4B 128K。不用再問。

## 驗收清單（分母 34）

每項回報完成（附證據）／未完成（原因）／沒測（條件不存在）。依最新回報辨認已完成項，不重跑沒有新變更的驗收。需要使用者的操作一次只請他做一件事。

**A. 部署、服務與 RAM**

- A1 兩 repo pull 成功；EdgeAgent 部署 exit 0。
- A2 EdgeAgent 完整 pytest（含真 Edge 回歸）0 failed、0 error、exit 0。PowerShell 看 pytest 自己的 exit code；測試環境使用 PYTHONIOENCODING=utf-8，取消 PYTHONUTF8，EDGE_AGENT_UI_REGRESSION=1。
- A3 SilentTalk 完整 pytest 同上，使用 PYTHONUTF8=1；保留既有單一 Tcl interpreter 的 UI 測試 fixture，不 skip 或加重試。
- A4 使用者已同意重載。用正常啟動器、既有 EdgeAgent CLI，按 PID 重載；重查目前 PID，開啟 SilentTalk 後就是機魂角色模式。
- A5 用模型頁設定 E4B／131072／working 131072／GPU 自動／low VRAM 開，不手改 config.json。核對 /status mode=character、agent_slot 有值、Agent context 是 131072 減角色 32768。
- A6 實量 VRAM、模型 RAM、mlock 成敗、角色回覆延遲、Agent 每秒字數。無 log 或未載新模型就寫未測；working set／private commit 不當作鎖成功的證據。
- A7 常駐只看名稱、數量、RAM。Discord 必須保留；日常不開 VS Code。關其他程式／取消自啟動需由使用者決定，做完量前後可用 RAM，不將程序工作集加總當作保證可釋出量。
- A8 正式重載後實跑 tests/browser_check.mjs --audit-live，全 24 項通過，含真正的 TXT 下載內容與 BOM，不以 UI regression 代替。

**B. 介面**

- B1 已移除 GPU 層數／省 VRAM／公開 Agent 結果三格與背後沒作用的欄位及參數；接手看回報與 commit，不把它們加回。
- B2 內建機魂不能刪；音高 22 Hz 打開再存不變，沿用精確的音高／語速控制。
- B3 設定／人設／啟動開關的回歸通過；本次普通 SSD 紀錄變更亦須驗證設定頁。

**C. Discord 真人測試（需要使用者）**

只用伺服器 729722190857240717、語音頻道 729722190857240721。工作區只用 `C:\Users\A8fm0\EdgeAgentTest`；批准由使用者自己按。只查檔案數量、大小、修改時間，不讀工作區或紀錄內容。

- C1 每句喊「機魂」才語音回；沒有名字不回。
- C2 語音查公開資料，結果貼原聊天室，開頭「【思考機回報】」，語音報重點，沒有私訊／批准。
- C3 語音不能動電腦；要求刪 tmp 不出批准，檔案不變。
- C4 文字提到機魂或回覆它：原頻道回、不開串；查資料／寫程式工作有 ⚙️→✅，結果貼原頻道。
- C4b 回覆貼圖請它讀字，結果由使用者確認。
- C4c 聊天誘導讀主人桌面：拿不到檔案，不出批准。
- C5 主人 @ 開 Agent 串；串內唯讀數 tmp 不問批准、不改檔案，結果貼串。
- C6 串內寫檔：批准只私訊；拒絕後無新檔。
- C7 串內刪 tmp：私訊批准附指令意義；拒絕後檔案都在。
- C8 准許後只少 tmp。
- C9 約 5 分鐘未按批准就拒絕，檔案不變。
- C10 按 A4 重啟 SilentTalk 後在原串問前事，使用者確認答得出；log_summary 有討論串讀回，不重派舊訊息工作。
- C11 第二個真人帳號：不變成主人工作；可聊天／查資料。沒有帳號標沒測，不用 webhook／bot 代替。
- C12 scripts/dev/log_summary.py 的完整數字表貼回報，明示是此次還是既有 app session。

**D. 原生 SSD 普通紀錄目錄**

- D1 建立 `C:\Users\A8fm0\AgentRecords`，沿用兩 app records owner 的 prepare 建 `.agent-records`。不建立容器或分割區，不需管理員／密碼。
- D2 兩邊介面／README 說明一般 SSD 目錄可用，不再說必須加密、掛載或有獨立代號；記錄位置不可用仍暫停。
- D3 經既有設定 owner／API 將兩 app 的 record_folder 設同目錄並開啟記錄，只修改這兩個已獲授權的紀錄欄位，其他使用者設定／人設不動。SilentTalk 未執行則存設定供下次正常啟動；舊 EdgeAgent 在 A4 前仍可能拒絕 C 槽，如實報告未生效，不熱補丁。
- D4 正式新版生效後，使用者說幾句／做一次工作，兩邊紀錄檔增加。只看檔案數量、大小，不讀內容。
- D5 以合成 fixture 驗證指定目錄不可用／無 marker 時不寫、不改存其他位置、不緩存待補寫；不能為測試改名使用者真紀錄目錄。
- D6 設定頁與網頁能顯示關閉／記錄中／暫停；普通 C 槽目錄可設定；不可用顯示暫停。真 Edge 回歸與合成 Tk 預覽可用，不能讀真人紀錄來驗收。
- D7 合成 fixture 恢復同目錄／marker 後繼續記錄，暫停時的對話不補寫；真人增量測量依 D4。

**E. 收尾**

- E1 自建測試程序結束、專用 CDP 不殘留；依使用者決定保留暫存與 EdgeAgentTest，不再嘗試被 policy 擋的清理。
- E2 log 的 agent_lease_return_failed／ClientConnectorDNSError 是否本次新增，只經既有數字工具讀取；Windows／網路問題在筆電查，角色／工具問題交開發機。

## 回報與下一步

回報只改既有 laptop-report worktree 的 handoff/reports/laptop.md，同一回合改寫同一節。包含時間／看不到的額度、34 項統計、每次測試（含紅測與失敗）、git log --stat 與 commit、RAM／速度、log_summary 全表、紀錄目錄數字、使用者決定、接手指示。對話與角色狀態內容禁止進回報。兩 repo 來源 commit 在 copilot-story-mode，報告 push laptop-report；以 git diff --check 和相關 pytest 核對，不宣稱沒實跑的功能通過。

接手優先核對紀錄變更和持久設定，再做 A4 重載；新版正式服務尚未生效時不把來源／測試通過當真人成功。本回合不做外接硬碟搬遷、MCP 介面或硬體擴充。
