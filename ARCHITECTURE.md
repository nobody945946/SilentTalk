# SilentTalk 架構

本文件維護 SilentTalk 的責任邊界、資料流與測試入口。安裝與使用見 [README.md](README.md)；EdgeAgent 的模型管理、Agent 實作與驗證由 [EdgeAgent 文件](https://github.com/nobody945946/EdgeAgent/blob/copilot-story-mode/README.md)維護。

## 產品邊界

SilentTalk 是 Discord 角色與回覆建議玩具。EdgeAgent 是獨立編程 Agent，擁有 Pi 工具迴圈、模型管理、llama.cpp router 與推論子程序。SilentTalk 不 import Agent 套件，也不啟動自己的 llama-server，只透過 localhost 租借服務。

```text
啟動 SilentTalk.cmd
  → scripts/bootstrap.ps1
      ├─ SilentTalk：獨立 venv、FFmpeg、STT
      └─ EdgeAgent 安裝器：獨立 venv、Pi SDK、引擎、公開模型

SilentTalk copilot/llm.py
  → agent_lease.py → EdgeAgent 控制 API :18087
      → 角色模型 → 回傳的推論 API :18089
      → 歸還 → 原 Agent 配置

EdgeAgent UI → Pi SDK → 批准後執行工具 → 同一推論 API
```

router 最多載入一個完整模型。租借角色與 Agent 設定使用相同基底及相同 LoRA 時，可共用同一推論服務；不同時拒絕 Agent 工作。Agent 工作或角色租借中禁止切換模型。附帶的 Agent adapter（`agent-fw1`，給預設 E4B）由 EdgeAgent 部署放進 `models`；租借預設帶上它，角色的請求依 `character_lora_uses`（預設空）決定套不套。自己的 adapter 也放同一個 `models`。

## 責任地圖

| 功能 | 唯一責任位置 | 相關邊界 |
|---|---|---|
| 程式組裝、命令列入口 | `app.py` | Controller、UI、smoke |
| UI 操作與頁面 | `silenttalk/ui.py` | `chat_ui.py`、`story_ui.py`、`persona_ui.py` |
| 快捷鍵與輸入法 | `hotkeys.py`、`ime.py` | thread-safe UIAction queue |
| 字型、尺寸、控制項 | `theme.py`、`widgets.py` | Tkinter main thread |
| UI 與 async 後端協調 | `controller.py` | TTS／Voice／Copilot 組裝 |
| 文字驗證 | `text.py` | normalization → SpeechQueue |
| 播放排序、取消、暫存清理 | `speech_queue.py` | TTSEngine／AudioPlayer 契約 |
| TTS 抽象與目前實作 | `tts/base.py`、`tts/edge.py` | EdgeTTS 外部服務 |
| Discord 跟隨、播放與接收 | `discord_voice.py` | Owner routing、DAVE、文字聊天 |
| STT | `copilot/stt.py`、`copilot/stt_offline.py` | 每位真人獨立 stream／VAD |
| 會話 context | `copilot/context.py` | RAM、候選不進歷史 |
| 角色請求與回覆選項 | `copilot/llm.py` | 租借推論端點、LoRA 請求分流 |
| 角色模式排程 | `copilot/runtime.py` | 時機、冷場、過期回覆、取消 |
| 人設與角色狀態 | `copilot/persona.py`、`copilot/character_state.py` | 使用者檔案；不保存對話原文 |
| 推論租借與重啟交接 | `agent_lease.py` | localhost client；無引擎所有權 |
| Discord Agent 任務傳輸 | `agent_tasks.py` | Controller 擁有；SSE、單次批准、取消；權限由 EdgeAgent 執行 |
| 設定載入與驗證 | `config.py` | TOML＋使用者差異 |
| 設定頁項目與保存 | `settings_schema.py`、`settings_store.py`、`settings_ui.py` | schema 驅動 UI |
| 初次 Discord 授權 | `credentials.py` | Windows 認證管理員；沿用既有 env |
| 快捷句與 UI 偏好 | `phrases.py`、`preferences.py` | 使用者持久資料 |
| 事件 log | `logging_setup.py` | 事件與數字；不含對話原文 |
| 首次部署與修復 | `scripts/bootstrap.ps1` | 完成紀錄、沿用 EdgeAgent 安裝器 |
| STT 資產與租借驗收 | `scripts/setup_copilot.py` | speech load、acquire／release |
| 發行來源與雜湊 | `scripts/edge-agent-distribution.json` | 最低版本、來源 ZIP |
| 玩家 ZIP | `scripts/package_windows.py` | Git allowlist、拒絕個人與不安全資產 |
| 唯一實例重啟 | `scripts/restart_silenttalk.ps1` | 按 PID 關閉舊實例 |

上表的 `app.py` 位於根目錄；其他未加前綴的 Python 路徑位於 `silenttalk/`。編程工具迴圈、模型下載或切換問題需在 EdgeAgent 對應 owner 修正，不能讓 SilentTalk 補償引擎缺陷。

## 資料流

### 手動 TTS 與快捷句

```text
F8／快捷句
  → UI callback → AppController.submit
  → text normalization／validation → SpeechQueue
  → EdgeTTSEngine → 暫存音訊 → DiscordAudioPlayer
  → Owner 所在 Voice Channel → 完成後刪除音訊
```

FIFO 使用單一 worker。F9 取消 pending 與目前工作，以 generation 使尚未播放的舊合成失效，並停止 player。已開始卻中斷的句子不自動重播，避免回音。手打與快捷句都走同一個 submit／queue 流程。

### 語音、角色與選項

```text
Discord 真人 PCM（含 Owner，排除 Bot）
  → DAVE 就緒檢查 → STT queue
  → 每位 speaker 的 STT → 台灣繁體轉換
  → RAM context → 單一生成 worker → 租借模型
      ├─ 選項：最多四種不同回覆 → 使用者選擇
      └─ 角色：判斷是否接話 → 回覆／冷場話題
  → Controller → 原 SpeechQueue／TTS／Discord
```

receive callback 不做推理，只複製 PCM 到 queue。生成期間新句子只更新下一次 trigger，不各自排隊生成；少於兩字的句子只進 context。角色正在說話時不追加下一句，過期生成會丟棄。語音播放成功後才記錄 self turn，未採用候選不進 context。自動壓縮濃縮早期內容，保留近期原文。

文字聊天啟用時，接收 Bot 所在語音頻道的內建文字聊天，以及 Bot 開的討論串，排除其他 Bot；Owner 在其他文字頻道 @ Bot（角色模式）時，從那則訊息開討論串（Discord 語音頻道的聊天室不能開串）。每句話帶著所在位置（`place`：`VOICE_ROOM` 或討論串 ID）。每個位置各有自己的 context、壓縮與「最新一句優先」的待答；語音頻道的文字與語音共用同一個 context。回覆送回原位置：討論串打字，語音頻道依來源用文字或語音；文字送出成功後才在該位置記錄 self turn。沉默開話題只看語音頻道；角色狀態更新讀所有位置。討論串最多保留 16 個，最久沒說話的先忘。派工的那則訊息由 `discord_voice.mark_task` 標記：受理 ⚙️，完成 ✅，失敗或取消 ❌。語音頻道的派工另有角色的接令與回報；討論串只在標記說不出的情況（工作仍在進行、私訊送不出去、公開結果）打一句。逐字稿紀錄附 `place`。

角色 LoRA 的套用請求由 `character_lora_uses` 決定。EdgeAgent 在角色有 LoRA 時分兩個 slot，區分套用與未套用的 cache；其他情況角色用一個 slot。基底與 LoRA 相同時另加 Agent 專用 slot，角色請求固定 slot 0／1，Agent 使用下一個 slot。每個 slot 的 context 保留兩個用戶端要求的較大容量。slot 數不代表完整模型數。

`character_agent` 開啟時，主人的 Agent 討論串只把主人的打字訊息交給 Agent。唯讀工作直接以唯讀 scope 執行；需要改動時，批准只私訊主人，私訊失敗或逾時就拒絕操作。工作結果貼回原聊天室或討論串，語音頻道另用聲音報重點。任何人叫機魂查資料、寫文章、翻譯或讀聊天室附件等工作時，Agent 使用 `scope: public`，只取得公開網路、翻譯器和該則訊息的附件，產出回到同一聊天室；語音永遠不能操作電腦。結果位置由這些路由決定，設定頁不再提供公開結果的開關。`discord_voice.py` 的批准 View 驗證主人 ID、禁止重複決定並在逾時拒絕。所有工作內容與 SSE 資料只在 RAM；自動紀錄只寫進使用者指定並設有標記的資料夾；原生 SSD 的一般目錄也可用，資料夾不可用時暫停，不改寫到別處。

### 租借生命週期

`agent_lease.py` 查詢／啟動 EdgeAgent 控制服務，提交包含 owner PID 與角色配置的 `/character` 請求；LLM client 使用租借回傳的推論端點。結束或切回時呼叫 `/base` 歸還。重啟交接沿用同一租借協定，不能另開模型子程序。

原 Agent 模型與配置由 EdgeAgent 保管，歸還後恢復；切換失敗由它回報與恢復。控制與推論回應都不能以「有程序」取代 ready 驗證。

## 執行緒與設定

Tkinter widget 只由 main thread 更新。全域快捷鍵 thread 將 UIAction 放入 thread-safe queue；Controller 的獨立 asyncio thread 處理 Discord、TTS、播放與 Copilot。STT receive 的工作透過自己的 queue 分離，不能阻塞 Discord 音訊 thread。

`config.toml` 保存預設值與註解，`settings.json` 保存使用者差異；`load_settings()` 合併後轉成 Settings／CopilotConfig 等 dataclass。`settings_schema.PAGES` 是設定頁清單 owner；restart 項目下次啟動生效，其他項目由 Controller 套用。

Bot Token 與 Owner ID 優先沿用既有 `.env`，缺少時讀 Windows 認證管理員。首次授權寫入認證管理員，安裝器不改使用者 env 或個人設定。

## 部署與發行

1. 從玩家 ZIP 快取取得 manifest 驗證過的 EdgeAgent 來源；符合最低版本的安裝沿用，過舊的目錄保留並另裝。
2. 檢查部署來源／元件 metadata、完成紀錄與 Python／Pi import。就緒則直接啟動；缺損或變動由原安裝流程修復。
3. 沿用 EdgeAgent 安裝器部署 Agent runtime 與公開角色基底。SilentTalk 自己部署 venv、FFmpeg 與 STT。
4. 檢查 pip、source 編譯、實際 STT 載入與角色租借／歸還，成功後原子寫入完成紀錄。
5. 取得 Discord 授權後，按 PID 重啟唯一 SilentTalk 實例。

`--setup-only` 只部署；SilentTalk `--check` 強制完整驗收，不連 Discord。EdgeAgent 啟動器的 `--check` 是元件部署／檢查，不能當成角色租借驗收。

`package_windows.py` 從指定 Git commit 的 allowlist 打包，驗證 EdgeAgent 來源 ZIP，拒絕不安全路徑與個人資產。不從工作目錄收集模型或使用者檔案。新 runtime 要重新驗證工具、協定與租借，不能只改版本字串。

## 保存與信任邊界

| 資料／服務 | 邊界 |
|---|---|
| STT 資產 | SilentTalk `.runtime/models/`；本機 CPU |
| Agent／角色 GGUF、adapter | EdgeAgent `models/` |
| 推論引擎、Node／Pi | EdgeAgent `.runtime/` |
| 對話、轉錄、候選、摘要 | RAM；不寫 session JSONL／歷史檔。例外：開啟「記錄對話」時，轉錄文字（不含錄音）由 `records.py` 只寫進使用者設定、含標記檔 `.agent-records` 的加密外接硬碟資料夾，硬碟不在就不寫 |
| 合成音訊 | 暫存播放檔；結束清除 |
| 人設、設定、快捷句、偏好 | 使用者持久資料；不進發行包 |
| 選用角色自身狀態 | 可保存近況與心情；不保存人的原話 |
| Discord／EdgeTTS | 外部網路服務；合成文字會送到 EdgeTTS |
| Agent 批准 | 是操作批准，不是 OS 沙盒 |

`quick_phrases.json` 每筆含 text 與 voice_style，仍支援舊版字串陣列；語速等偏好在 `ui_preferences.json`。這是有效資料格式相容，不是第二條執行流程。

## 驗證入口

| 測試／runner | 保護的邊界 |
|---|---|
| `test_config.py`、`test_discord_config.py` | 設定、憑證與必要 intents |
| `test_owner_routing.py`、`test_player.py`、Voice 相關測試 | 跟隨、重連、播放、停止 |
| `test_voice_receive.py` | Owner 與真人接收、排除 Bot、DAVE |
| `test_copilot_context.py`、`test_copilot_llm.py` | RAM context、回覆選項、角色請求與 LoRA 分流 |
| `test_copilot_runtime.py` | 角色時機、冷場與過期回覆 |
| `test_agent_lease.py` | API client、租借／歸還與重啟交接 |
| `test_agent_tasks.py` | 離線 SSE、Owner 批准、拒絕／逾時、背景派工及失敗回報、只認 Owner ID、批准與結果只走私訊 |
| `test_package_windows.py` | Git 來源、雜湊、拒絕個人／不安全檔案 |
| `app.py --voice-smoke`／`--tts-smoke` | 真實 Discord 播放；需要授權與頻道 |
| `啟動 SilentTalk.cmd --check` | 部署、STT load、實際租借與歸還，不連 Discord |
| EdgeAgent `tests/browser_check.mjs` | 真實 Edge 的模型管理與 Agent UI |

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

看 pytest 本身 exit code；驗證事件與數字寫到指定報告分支，不保存 prompt、轉錄或真人對話。歷史通過與最新失敗需分別記錄，不以舊結果代替本輪狀態。
