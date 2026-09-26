# SilentTalk Architecture

> 這份文件回答兩個問題：**「功能在哪裡？」**以及**「資料怎麼流？」**  
> 如果只是要安裝、啟動或使用 SilentTalk，先看 [README.md](README.md)。

## 1. 一分鐘理解整個專案

SilentTalk 是一個 Windows 本機桌面程式：

1. 使用者按全域快捷鍵開啟輸入框。
2. UI 把文字交給 Controller。
3. Controller 驗證文字並送進 FIFO 語音佇列。
4. TTS 把文字合成暫存音訊。
5. Discord Voice 模組找到 Owner 目前所在的語音頻道。
6. FFmpeg / discord.py 播放音訊。
7. 播放完成後刪除暫存音訊。

核心資料流：

```text
使用者
  │
  │ F8 / F9
  ▼
hotkeys.py
  │
  ▼
ui.py
  │ submit(text)
  ▼
controller.py
  │
  ├── text.py              文字正規化與驗證
  │
  ▼
speech_queue.py            FIFO / cancel / job lifecycle
  │
  ├── tts/edge.py          文字 → MP3
  │
  └── discord_voice.py     MP3 → Discord Voice
```

## 2. 想改什麼，先去哪裡

| 想修改的功能 | 先看 | 通常還會碰到 |
|---|---|---|
| F8 輸入框、按鈕、視窗行為 | `silenttalk/ui.py` | `app.py` |
| F8 / F9 全域快捷鍵實作 | `silenttalk/hotkeys.py` | `config.toml`, `silenttalk/config.py` |
| 新增快捷句、UI 內操作 | `silenttalk/ui.py` | `silenttalk/phrases.py` |
| AI 劇情模式畫面、WASD 操作 | `silenttalk/story_ui.py` | `silenttalk/ui.py`, `silenttalk/ime.py` |
| 角色模式何時開口（冷卻、點名、問句） | `silenttalk/copilot/character.py` | `copilot/runtime.py`, `config.toml` |
| 人設欄位、預設人設 | `silenttalk/copilot/persona.py` | `silenttalk/persona_ui.py` |
| 回覆方向（同意／追問／反對／玩笑）與按鍵對應 | `silenttalk/copilot/types.py` 的 `REPLY_LANES` | `silenttalk/copilot/llm.py` prompt |
| Copilot 模型檔、GPU layers | `config.toml` `[copilot]` | `scripts/setup_copilot.py` |
| 文字長度、空白、換行規則 | `silenttalk/text.py` | `silenttalk/config.py` |
| TTS 聲音、速度、音高、音量 | `config.toml` | `silenttalk/tts/edge.py` |
| 換另一個 TTS 引擎 | `silenttalk/tts/base.py` | `silenttalk/tts/edge.py`, `controller.py`, `config.py` |
| 播放順序、排隊、取消 | `silenttalk/speech_queue.py` | `controller.py` |
| Bot 跟隨 Owner 的邏輯 | `silenttalk/discord_voice.py` | `config.py` |
| Discord 連線 / 重連 / 換頻道 | `silenttalk/discord_voice.py` | `controller.py` |
| Bot Token / Owner ID | `.env` | `silenttalk/config.py` |
| 一般可調參數 | `config.toml` | `silenttalk/config.py` |
| 程式啟動與元件組裝 | `app.py` | `controller.py` |
| Windows 第一次安裝流程 | `啟動 SilentTalk.cmd` | `requirements.txt` |
| 啟動 / TTS / Voice 實機檢查 | `silenttalk/smoke.py` | `app.py` |
| Log 格式與寫入位置 | `silenttalk/logging_setup.py` | 各模組的 `logging` 呼叫 |
| App 狀態名稱 | `silenttalk/state.py` | UI / queue / Discord 模組 |

## 3. Repository 結構

```text
SilentTalk/
├─ app.py                       # Composition root / 程式入口
├─ config.toml                  # 非敏感、可調整設定
├─ .env.example                 # Bot Token / Owner ID 範本
├─ requirements.txt             # Runtime dependencies
├─ requirements-dev.txt         # Test / lint dependencies
├─ 啟動 SilentTalk.cmd           # Windows bootstrap / launcher
├─ README.md                    # 使用方式
│
├─ silenttalk/
│  ├─ __init__.py
│  ├─ config.py                 # 設定模型、載入與驗證
│  ├─ controller.py             # UI 與 async backend 的協調層
│  ├─ discord_voice.py          # Discord Voice routing + playback
│  ├─ hotkeys.py                # Win32 global hotkeys
│  ├─ ime.py                    # 劇情模式時暫停 Windows IME
│  ├─ logging_setup.py          # JSON file logging
│  ├─ phrases.py                # 快捷句 persistence / CRUD
│  ├─ copilot/                  # Discord receive → STT → context → local LLM
│  │  ├─ context.py
│  │  ├─ llm.py
│  │  ├─ runtime.py
│  │  ├─ script.py              # 簡體 → 台灣繁體（OpenCC s2twp）
│  │  ├─ smoke.py               # app.py --copilot-smoke；scripts/dev/ 共用
│  │  ├─ stt.py
│  │  └─ types.py
│  ├─ smoke.py                  # Voice / TTS 實機 smoke gates
│  ├─ speech_queue.py           # FIFO jobs + cancel lifecycle
│  ├─ state.py                  # AppState
│  ├─ story_ui.py               # AI 劇情模式分頁（WASD 選項）
│  ├─ text.py                   # 文字 normalization / validation
│  ├─ ui.py                     # Tkinter UI
│  └─ tts/
│     ├─ __init__.py
│     ├─ base.py                # TTSEngine protocol + AudioResult
│     └─ edge.py                # EdgeTTS implementation
│
└─ tests/
   ├─ test_config.py
   ├─ test_discord_config.py
   ├─ test_edge_integration.py
   ├─ test_owner_routing.py
   ├─ test_player.py
   ├─ test_queue.py
   ├─ test_smoke.py
   ├─ test_text.py
   ├─ test_voice_config.py
   └─ test_voice_monitor.py
```

## 4. 元件責任

### `app.py` — Composition Root

`app.py` 不負責真正的 TTS 或 Discord 邏輯，主要做「組裝」：

- 設定 logging。
- 呼叫 `load_settings()`。
- 處理 `--voice-smoke` / `--tts-smoke`。
- 建立 `AppController`。
- 建立 `SilentTalkUI`。
- 把 Controller 的方法當 callback 傳給 UI。
- 啟動 Controller，再進入 Tkinter main loop。

重要 wiring：

```text
SilentTalkUI.submit
      │
      └────────► AppController.submit

SilentTalkUI.stop
      │
      └────────► AppController.stop_playback

SilentTalkUI.shutdown
      │
      └────────► AppController.shutdown
```

因此 UI 不需要知道 TTS、Discord 或 queue 的實作。

---

### `silenttalk/ui.py` — Tkinter UI

責任：

- 建立置頂輸入 popup。
- Enter 送出文字。
- Shift+Enter 換行。
- Esc 收起並清空未送出文字。
- 顯示狀態。
- 提供停止播放與退出按鈕。
- 接收 GlobalHotkeys 產生的 UI action。
- 用 `ttk.Notebook` 分成「手動輸入」與「AI 劇情模式」兩個分頁；上次使用的分頁記在 `ui_preferences.json` 的 `ui_mode`。
- 劇情模式時，popup 層級的 `<KeyPress>` 轉交 `StoryPanel.handle_key()`；手動模式完全不攔截按鍵，所以打字不受 WASD 影響。

UI 透過 callback 與 backend 溝通：

```python
submit: Callable[[str], None]
stop_playback: Callable[[], None]
shutdown: Callable[[], None]
```

這個邊界很重要：**UI 不直接 import 或操作 Discord / TTS。**

若新增「快捷句」，最自然的入口就是這裡；快捷句最後仍應走原本的 `submit(text)`，不要繞過 Controller。

---

### `silenttalk/hotkeys.py` — Windows 全域快捷鍵

使用 Win32 API：

- `RegisterHotKey`
- `GetMessageW`
- `UnregisterHotKey`

目前只接受 F1–F12 類型的按鍵名稱。

它自己有一條背景 thread，因此不直接改 Tkinter widget。Hotkey callback 只把 `UIAction` 丟進 UI 的 thread-safe queue，再由 Tkinter thread 處理。

---

### `silenttalk/controller.py` — 協調層

Controller 是 UI 與 async backend 之間的橋。

它建立：

- 一條專用 asyncio event loop。
- 一條 `silenttalk-async` daemon thread。
- 一個暫存資料夾。
- `DiscordVoiceClient`。
- `EdgeTTSEngine`。
- `SpeechQueue`。
- `DiscordAudioPlayer`。

送出文字時：

```text
AppController.submit(raw_text)
  │
  ├─ normalize_text(...)
  │
  └─ schedule SpeechQueue.enqueue(text)
```

Controller 也是目前真正選擇「使用 EdgeTTS」的地方。雖然 TTS 已有 Protocol 抽象，但目前仍由 Controller 直接建構 `EdgeTTSEngine`，因此若要讓 TTS engine 可插拔，還需要把建構策略抽出來。

---

### `silenttalk/copilot/` — 本機 Discord 對話 Copilot

Copilot 與原本 TTS pipeline 是旁路關係，不把 STT / LLM 邏輯塞進 `discord_voice.py` 或 `speech_queue.py`：

```text
Discord VoiceRecvClient
        │ per-user PCM
        ▼
copilot/stt.py
Streaming Paraformer INT8 / CPU
（0.66 s tail padding；endpoint rule2 0.8 s 處理開放式麥克風；s2twp 轉台灣繁體）
        │ final transcript
        ▼
copilot/context.py
bounded session context
        │
        ▼
copilot/llm.py
Gemma 4 E2B（config 可換）/ persistent llama-server
        │
        ▼
ReplySuggestions（欄位與按鍵由 REPLY_LANES 定義）
  ├─ W 同意
  ├─ A 追問
  ├─ D 反對
  └─ S 玩笑／打圓場（可 SKIP）
        │
        ▼
ui.py / story_ui.py
手動分頁：Tab 填入 / Enter 送出
劇情分頁：WASD 選擇，同鍵再按或 Enter 說出
        │
        ▼
原本 Controller → SpeechQueue → EdgeTTS → Discord
```

**角色模式（`copilot/character.py`）**：同一條 STT → context → LLM 管線，但 Bot 自己就是人設角色。`CopilotRuntime.set_character_mode(True)` 之後：

```text
final transcript（含 Owner 自己的麥克風）
  → character.should_reply()   叫到名字一定回；否則冷卻＋（問句 或 別人講了 N 句）
  → LocalReplyModel.character_reply()   一句話或 SKIP；記住最近 4 句，避免口頭禪重複
  → 生成期間對話又走了 ≥2 句且不是被點名 → 丟掉
  → Controller._speak_as_character()   SpeechQueue 不閒置就丟掉（不搶話）
  → SpeechQueue → EdgeTTS → Discord；播放完成才 record_self（以角色名顯示）
```

角色模式的 system prompt 允許角色承認自己是 AI（Copilot 模式則相反：說話的是真人，不能說自己是 AI）。

重要邊界：

- Discord receive callback 只複製 PCM 丟給 STT queue，不能在 voice receive thread 做推理。
- 每位 Discord speaker 有獨立的 streaming STT stream，不需要額外 diarization。
- 未採用的 AI 候選不進 context。
- 同一時間只有一個 LLM 生成（`_suggestion_worker`）；生成期間新進的句子只保留最新一句作為下一個 trigger。llama-server 以 `--parallel 1` 啟動，不讓多個 slot 分掉 4 GB GPU 的 context。
- 少於 2 個字的句子（「嗯」「好」）只進 context，不觸發生成。
- 啟動前先跑 `llama-server --list-devices`，把看到的 GPU 記成 `copilot_llm_devices`（沒有裝置＝CPU 模式）。llama-server 的 stderr 只留在記憶體尾端 40 行，只有含 error／failed／out of memory 的行寫入 `silenttalk.log`；不提高 verbosity，避免 prompt 內容落地。
- Streaming Paraformer 每約 0.6 s 才吐一次字；句尾若只補 0.2 s 靜音，最後 1–3 字會掉（實測 CER 14.7% → 補 0.66 s 後 7.1%）。
- DAVE（Discord 語音 E2EE）握手完成前收到的封包仍是密文，解出來是雜訊，`discord_voice.py` 會直接丟掉；沒有 `dave_session` 的連線（例如 Stage 頻道）不啟動接收，避免 voice_recv fork 的 decoder 崩潰後觸發重連迴圈。
- 使用者按送出後也不立刻寫成 self turn；只有 SpeechQueue 完成 Discord playback 後，`on_done` 才記錄「你真的說過這句」。
- session transcript / PCM 不落地；context 只存在 RAM。
- Copilot 啟動失敗時 Controller 會停掉部分 Copilot 並把 PCM callback 清掉，原有手動 TTS 仍可使用。

### `silenttalk/text.py` — 純文字規則

只做 deterministic、meaning-preserving normalization：

- CRLF / CR → LF。
- Unicode NFC normalization。
- 壓縮行內多餘空白。
- 最多保留兩個連續換行。
- 拒絕空字串。
- 拒絕超過 `max_text_length`。

這一層不碰 UI、不碰 TTS、不碰 Discord，因此很容易單元測試。

---

### `silenttalk/speech_queue.py` — 語音工作佇列

核心物件：

- `SpeechJob`
- `JobState`
- `SpeechQueue`
- `AudioPlayer` Protocol

Job 狀態：

```text
QUEUED
  ↓
SYNTHESIZING
  ↓
PLAYING
  ↓
DONE
```

另外可能進入：

```text
FAILED
CANCELLED
```

Queue 是單 worker FIFO：一次只合成 / 播放一個 job。

取消不是只清 pending queue。它用 `generation` 使「正在合成、但尚未播放」的舊工作失效，並呼叫 player.stop() 停止目前播放。

音訊使用完會在 `finally` 裡刪除。

---

### `silenttalk/tts/base.py` — TTS 抽象邊界

`TTSEngine` Protocol 定義：

```python
initialize()
synthesize(text) -> AudioResult
shutdown()
```

`AudioResult` 是 TTS 與播放器之間的資料契約。

好處是 `SpeechQueue` 不需要知道底下是 EdgeTTS、其他雲端 TTS 或本機模型。

目前限制：`config.py` 與 `controller.py` 還明確限定 EdgeTTS，所以抽象層已存在，但尚未做到 runtime plugin 化。

---

### `silenttalk/tts/edge.py` — EdgeTTS Adapter

責任：

- 若沒指定 voice，查詢 zh-TW voices。
- 優先選 Female zh-TW voice。
- 使用 rate / volume / pitch。
- 把結果寫到暫存 MP3。
- timeout / 空檔案視為失敗。
- 失敗時清除暫存檔。

這層會把文字送給 `edge-tts` 所使用的外部服務；程式本身則不把輸入全文寫入 SilentTalk log。

---

### `silenttalk/discord_voice.py` — Discord Voice

分成兩個主要角色：

#### `DiscordVoiceClient`

負責：

- Discord Gateway 連線。
- 只開啟 `guilds` 與 `voice_states` intents。
- 尋找 `OWNER_USER_ID` 所在的語音頻道。
- Owner 換頻道時跟隨。
- Owner 跨 Server 時斷舊連新。
- Owner 離開時依設定斷線。
- 清理 stale VoiceClient。
- 低頻 voice monitor / reconnect backoff。

它沒有寫死 Guild ID 或 Voice Channel ID。

#### `DiscordAudioPlayer`

負責：

- 播放 `AudioResult`。
- 使用 `discord.FFmpegOpusAudio`。
- 每次播放前重新確認 Owner voice routing。
- 播放中若 transport 失敗，不重播同一句，避免回音。
- `stop()` 停止目前音訊。

---

### `silenttalk/config.py` — 設定邊界

敏感資料來自 `.env`：

```dotenv
DISCORD_BOT_TOKEN=
OWNER_USER_ID=
```

一般設定來自 `config.toml`：

- `[app]`
- `[tts]`
- `[discord]`
- `[audio]`

最後轉成 immutable dataclass：

```text
Settings
├─ AppConfig
├─ TTSConfig
├─ DiscordConfig
└─ AudioConfig
```

`Settings.validate_runtime()` 目前主要檢查 FFmpeg。

---

### `silenttalk/phrases.py` — 快捷句資料層

`QuickPhraseStore` 負責本機快捷句的 persistence 與 CRUD：

- `load()`
- `add(text)`
- `update(index, text)`
- `delete(index)`

資料存在 repo 根目錄的 `quick_phrases.json`，使用 UTF-8 JSON 字串陣列。寫入時先寫 `.tmp` 再 replace，避免一般寫入途中留下半份 JSON。

`ui.py` 只負責「怎麼顯示、怎麼操作」，不自己處理 JSON。快捷句送出時仍呼叫原有 submit callback，因此 Controller / Queue / TTS / Discord 不需要知道文字來源。

前九句在 F8 popup 中對應 `Ctrl+1`～`Ctrl+9`；雙擊列表項目也可直接送出。

---

### `silenttalk/state.py` — UI / Runtime 狀態契約

`AppState` 是跨模組共用的狀態名稱：

```text
STARTING
READY
OWNER_NOT_IN_VOICE
VOICE_CONNECTED
SYNTHESIZING
SPEAKING
ERROR
SHUTTING_DOWN
```

Queue、Discord、Controller 可以回報狀態，但 UI 負責呈現。

---

### `silenttalk/logging_setup.py` — Log

寫入：

```text
silenttalk.log
```

每行為 JSON，包含：

- timestamp
- level
- logger
- event
- exception（有例外時）

現有核心流程記錄 job id、字數、延遲、錯誤類型等資訊，而不是把使用者輸入全文當一般 log 寫入。

---

### `silenttalk/smoke.py` — 實機 Gate

提供兩條不經一般 UI 的驗證路徑：

```text
--voice-smoke
固定 440 Hz WAV
→ Discord Voice
```

```text
--tts-smoke
固定文字
→ EdgeTTS
→ Discord Voice
```

用途是把問題切開：先證明 Discord Voice 可播放，再證明 TTS → Discord 整條鏈可用。

## 5. 執行緒與 Async 模型

SilentTalk 同時有三種主要執行上下文：

```text
┌──────────────────────────────┐
│ Tkinter / Main Thread        │
│ ui.py                        │
│ 所有 widget 更新             │
└──────────────┬───────────────┘
               │ UIAction queue
               ▲
┌──────────────┴───────────────┐
│ Global Hotkey Thread         │
│ hotkeys.py                   │
│ Win32 message loop           │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Async Backend Thread         │
│ controller.py                │
│ asyncio event loop           │
│                              │
│ SpeechQueue                  │
│ EdgeTTS                      │
│ Discord Client / Voice       │
└──────────────────────────────┘
```

設計原則：

- Tkinter widget 只在 Tkinter thread 操作。
- Hotkey thread 不直接操作 UI。
- UI 的同步 callback 透過 Controller 排程 async coroutine。
- Discord / TTS / queue 的 async 工作集中在 backend event loop。

若新增功能，應避免從 backend thread 直接修改 Tkinter widget。

## 6. 主要 Runtime Flow

### 6.1 一般送出文字

```mermaid
sequenceDiagram
    participant U as User
    participant H as GlobalHotkeys
    participant UI as SilentTalkUI
    participant C as AppController
    participant Q as SpeechQueue
    participant T as EdgeTTSEngine
    participant D as DiscordAudioPlayer
    participant V as DiscordVoiceClient

    U->>H: F8
    H->>UI: UIAction("show")
    UI-->>U: 顯示輸入框
    U->>UI: Enter
    UI->>C: submit(raw_text)
    C->>C: normalize_text()
    C->>Q: enqueue(text)
    Q->>T: synthesize(text)
    T-->>Q: AudioResult(mp3)
    Q->>D: play(audio)
    D->>V: sync_owner_voice()
    V-->>D: active VoiceClient
    D-->>Q: playback complete
    Q->>Q: delete temp audio
```

### 6.2 F9 停止

```text
F9
→ GlobalHotkeys
→ UIAction("stop")
→ UI._poll_actions()
→ AppController.stop_playback()
→ SpeechQueue.cancel_all()
→ pending jobs = CANCELLED
→ current job = CANCELLED
→ DiscordAudioPlayer.stop()
```

### 6.3 Owner 換語音頻道

```text
Discord voice_state_update
→ DiscordVoiceClient
→ 確認事件是否為 Owner / Bot
→ 等待 cache 短暫 settle
→ sync_owner_voice()
→ 找 Owner 現在所在 channel

同 Server：
move_to(new_channel)

跨 Server：
disconnect old
→ connect new
```

## 7. 啟動流程

一般 Windows 使用者從：

```text
啟動 SilentTalk.cmd
```

開始。

Launcher 目前負責：

1. 檢查 `config.toml`。
2. 第一次使用時從 `.env.example` 建立 `.env` 並開記事本。
3. 尋找 Python 3.12；必要時用 winget 安裝。
4. 建立 `.venv`。
5. 安裝 `requirements.txt`。
6. 尋找 FFmpeg；必要時用 winget 安裝。
7. 用 `load_settings()` 驗證設定。
8. Copilot 啟用時安裝/找到 llama.cpp，並以 `scripts/setup_copilot.py` 準備本機 STT/LLM 模型。
9. 以 `compileall` 做輕量 source gate。
10. `restart_silenttalk.ps1` 清掉舊 SilentTalk 與遺留的專用 llama-server，再以 `pythonw.exe app.py` 啟動 GUI。

`--check` 可只驗證 launcher 前置條件而不開 GUI。

## 8. 外部依賴與信任邊界

Runtime dependencies：

```text
discord.py[voice]        2.7.1
edge-tts                 7.2.8
python-dotenv            1.1.1
sherpa-onnx              1.13.8
numpy                    >=1.26,<3
discord-ext-voice-recv   pinned DAVE-compatible commit
llama.cpp                WinGet portable runtime
```

Copilot models are not committed to Git. The launcher downloads them into `.runtime/models/` and validates the pinned hashes/sizes.

外部系統：

```text
SilentTalk
├─ Discord Gateway / Voice
├─ EdgeTTS 所使用的外部語音服務
└─ FFmpeg executable
```

本機敏感資料：

- Discord Bot Token
- Owner Discord User ID

Token 應只存在本機 `.env`，且 `.env` 必須維持在 Git ignore 範圍內。

## 9. 測試如何對應架構

| Test | 主要保護的邊界 |
|---|---|
| `test_config.py` | env / TOML 載入、驗證、錯誤條件 |
| `test_discord_config.py` | Discord intents 最小化 |
| `test_edge_integration.py` | 真實 EdgeTTS synthesis |
| `test_owner_routing.py` | 同 Server / 跨 Server / stale voice routing |
| `test_player.py` | Voice connection reuse、播放失敗不重播 |
| `test_phrases.py` | 快捷句 JSON persistence、CRUD、驗證 |
| `test_queue.py` | FIFO、cancel、暫存音訊清理 |
| `test_smoke.py` | 固定測試 WAV |
| `test_text.py` | 文字 normalization / validation |
| `test_voice_config.py` | voice reconnect 參數 |
| `test_voice_monitor.py` | monitor task shutdown |
| `test_voice_receive.py` | Discord receive 過濾 Owner / bot，只轉真人 PCM |
| `test_copilot_context.py` | bounded context 與較早 self turns |
| `test_copilot_llm.py` | 固定三槽 parser、HUMOR SKIP、長度限制 |

執行：

```powershell
.\.venv\Scripts\python -m pytest -q
```

## 10. 架構原則

目前程式值得維持的幾個邊界：

1. **UI 不直接操作 Discord / TTS。**
2. **文字都先經過 Controller / text normalization 再進 queue。**
3. **SpeechQueue 只依賴 TTS / AudioPlayer 契約，不綁 UI。**
4. **Discord routing 與 TTS synthesis 分離。**
5. **Hotkey thread 不直接操作 Tkinter widget。**
6. **Bot Token 不進 `config.toml` 或版控。**
7. **已開始但中途失敗的語句不自動重播，避免 Discord 回音。**
8. **Owner routing 不寫死 Guild / Channel ID。**

## 11. 新功能應該放哪裡

### 可編輯快捷句

目前已實作：

```text
quick_phrases.json
       │
       ▼
silenttalk/phrases.py
       │ load / add / update / delete
       ▼
silenttalk/ui.py
       │
       ├─ 列表 / 新增 / 載入 / 更新 / 刪除
       ├─ Ctrl+1～Ctrl+9
       └─ submit(selected_text)
              │
              ▼
        原本完整 pipeline
```

邊界保持不變：

- `ui.py`：呈現與使用者操作。
- `phrases.py`：本機資料 persistence。
- `app.py`：建立 `QuickPhraseStore` 並注入 UI。
- Controller / queue / TTS / Discord：不用知道文字來自手打還是快捷句。

### 新 TTS Engine

保持：

```text
TTSEngine Protocol
      │
      ├─ EdgeTTSEngine
      └─ NewTTSEngine
```

但要真正做到可切換 engine，還應把 `controller.py` 中直接建立 `EdgeTTSEngine` 的地方改成 factory / provider，並放寬 `config.py` 現在只接受 `engine = "edge"` 的限制。

## 12. 目前架構的刻意取捨

這是一個小型桌面程式，但已經比單檔腳本更模組化。

優點：

- 各責任區容易單獨測試。
- UI、TTS、queue、Discord 可以局部修改。
- Agent 或人類修改時，影響範圍較容易控制。

代價：

- 一個「按 F8 然後說話」的人類操作會跨多個檔案。
- 初次讀 repo 時，不看這份地圖容易一直追 callback。

因此本文件的主要用途不是增加更多抽象，而是讓現有抽象**可導航**。
