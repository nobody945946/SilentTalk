# SilentTalk

Windows 本機文字輸入 → EdgeTTS → Discord Bot 語音頻道。程式不讀寫 Discord 文字頻道，也不保存輸入全文或音訊歷史。

## 開發者導覽

如果你要修改程式而不是只使用它，先看 [ARCHITECTURE.md](ARCHITECTURE.md)。裡面有「想改什麼 → 去哪個檔案」、核心資料流、執行緒模型與測試對照表。

## 最快使用方式

1. 雙擊 `啟動 SilentTalk.cmd`。啟動後不會出現大型主視窗。
2. 用 `.env` 內 `OWNER_USER_ID` 對應的 Discord 帳號加入一般語音頻道。
3. Bot 會自動加入；跨 Server 時，目標 Server 也必須先安裝 Bot。
4. 按 F8 開啟置頂輸入框，輸入文字後按 Enter。
5. 播放途中按 F9，可停止目前語音並清空尚未播放的句子。
6. 要關閉程式時，按 F8，再點「退出 SilentTalk」。

### UI 聲線選單與預設語音包

F8 視窗現在有「聲線」下拉選單與獨立「語速」滑桿。下拉選單只放真正的聲線 / 角色 preset，不再混入「快速、慢速」這類速度選項；語速統一由 60%～140% 滑桿控制。選定語速會套用到手打文字與 Ctrl+1～Ctrl+9，並保存在本機 `ui_preferences.json`。快捷句仍各自記住自己的聲線。

第一次使用、且本機尚未建立 `quick_phrases.json` 時，會自帶四句快捷句：

1. `For the Emperor!` — 星際戰士。
2. `The Emperor protects!` — 星際戰士。
3. `For the Omnissiah!` — 機械神甫。
4. `Faith is my shield!` — 戰鬥修女。

目前聲線下拉選單只保留「一般、星際戰士、機械神甫、戰鬥修女」。星際戰士與機械神甫是已經過實際聽感驗收的基準；戰鬥修女採成熟、冷峻、堅定的女聲取向，不做甜美或高音角色化。舊的 `/slow`、`/fast`、`/deep`、`/cute` 文字前綴仍保留相容性，但不顯示於聲線下拉選單。

快捷鍵：

- F8：開啟輸入框。
- Enter：送出文字。
- Shift+Enter：在輸入框中換行。
- Ctrl+1～Ctrl+9：直接播放前九個快捷句。
- 雙擊快捷句：直接播放該句。
- Esc：關閉輸入框並清空尚未送出的文字。
- F9：停止目前播放並清空 queue；Bot 不會因此退出頻道。

### 快捷句

F8 視窗內有一個可編輯的快捷句清單。快捷句仍走原本的「文字驗證 → queue → EdgeTTS → Discord Voice」流程，不會繞過既有播放邏輯。

使用方式：

1. 在上方文字框輸入一句常用文字。
2. 點「新增目前文字」保存。
3. 選取快捷句後可「載入選取」、「更新選取」或「刪除選取」。
4. 前九句會自動對應 Ctrl+1～Ctrl+9；也可以直接雙擊任一句播放。

快捷句保存在本機 `quick_phrases.json`，每筆包含 `text` 與 `voice_style`。語速是全域 UI 偏好，另外保存在 `ui_preferences.json`，因此把語速調成 80% 後，所有快捷句都會一起變慢。兩個本機檔案都不會跟著 Git commit。舊版純字串快捷句陣列仍可直接讀取。

## 如何輸入抑揚頓挫

SilentTalk 會把輸入文字交給 EdgeTTS。標點會影響斷句與語氣，但效果由 Microsoft 語音模型決定，並不是精確的音樂節拍控制。

| 輸入方式 | 通常產生的效果 | 範例 |
|---|---|---|
| `，` | 短停頓，適合一句內換氣 | `等一下，我馬上回來。` |
| `。` | 明確結句，停頓通常比逗號長 | `我知道了。等等再說。` |
| `；` | 介於逗號和句號之間的分段 | `我可以處理；但需要一點時間。` |
| `：` | 引出後面的內容 | `重點是：先不要離開。` |
| `？` | 疑問語氣；是否明顯上揚取決於 voice | `你確定嗎？` |
| `！` | 較有力的結句；不保證一定提高音量 | `快跑！` |
| `……` | 猶豫、留白或較長停頓 | `我想想……應該可以。` |
| `——` | 突然停住、轉折或拉開兩段話 | `等等——先別按。` |
| 換行 | 把內容分成較明確的語意段落 | `第一件事。` 換行後輸入 `第二件事。` |

推薦寫法：

```text
平靜敘述：我知道了，等一下就過去。
驚訝語氣：真的假的？你確定嗎！
猶豫語氣：這個嘛……讓我想一下。
強烈轉折：等等——先不要動！
分段說明：第一件事，先存檔；第二件事，重新啟動。
```

### 拖長音怎麼寫

EdgeTTS 沒有可靠的「把某個中文字母精確拉長 N 秒」輸入符號。以下只能做近似效果：

```text
好——喔……
不要——
等、等一下！
真的嗎……？
```

- `——` 通常是拉開語句或增加停頓，不保證延長前一個母音。
- `……` 通常是留白或猶豫，不等於固定秒數的休止。
- 重複文字，例如 `好好好`，通常會被當成三個字念出，不是真正的長音。
- `~~~`、`～～～`、大量重複標點可能被忽略、念成符號或產生不自然結果，不建議依賴。
- `<break>`、`<prosody>` 等 SSML 標籤不要輸入；目前 edge-tts 不接受自訂 SSML，可能直接把它當文字或拒絕請求。

一般使用不必再為語速修改 `config.toml`；F8 視窗的語速滑桿會乘在聲線 preset 的原始速度上。若要修改整個程式的底層預設值，才需要調整 `config.toml`：

```toml
[tts]
voice = "zh-TW-YunJheNeural"
rate = "-10%"
pitch = "-20Hz"
volume = "+0%"
```

- `rate`：整段語速；負值較慢，正值較快。
- `pitch`：整段音高；負值更低沉，正值更高。
- `volume`：整段音量。
- 修改後要退出並重新啟動 SilentTalk 才會生效。
- 這些設定作用於整句，無法只套用到句子中的某幾個字。

edge-tts 官方說明：可調整 rate、volume、pitch，但不再支援自訂 SSML：[edge-tts README](https://github.com/rany2/edge-tts#custom-ssml)。

## 目前範圍

- EdgeTTS、單一 FIFO queue、F8 輸入框、可編輯快捷句、F9 停止與清空。
- Bot 只追蹤 `.env` 內的 `OWNER_USER_ID`，Owner 換台時跟隨、離開時斷線。
- Bot 加入後會保持同一條 Voice 連線；每句播放不會重新加入或離開頻道。
- Voice state 事件先做防抖，Owner 暫時從 cache 消失時有離線寬限期；手動重連失敗採指數退避，避免網路不穩時 Bot 瘋狂進出頻道。另有每 60 秒一次的低頻 watchdog 處理漏事件與 stale cache。
- Gateway 只啟用 `guilds` 與 `voice_states` intents；不啟用 Message Content。
- `--voice-smoke` 會播放固定 440 Hz 測試音，作為 Gate 1 實機 runner。
- CosyVoice / CUDA 不在 MVP 依賴內。

## Bot 何時加入或退出

- SilentTalk 正在運行，而且 Owner 加入語音頻道：Bot 自動加入。
- Owner 在同一 Server 換頻道：Bot 直接移動。
- Owner 跨 Server：Bot 先退出舊 Server，再加入新 Server。
- 播放完一句或暫時沒有輸入：Bot 保持連線，不會反覆進出。
- Owner 離開語音、退出 SilentTalk、電腦關機或權限被撤銷：Bot 退出。
- 網路短暫中斷：先由 discord.py 自動恢復；SilentTalk 會合併短時間內的 voice-state 事件，Owner 暫時消失不會立刻退出；若真的需要重新 connect，失敗會逐次拉長等待時間，避免加入/退出洗頻。

每個需要使用的 Server 都要加入 Bot，最低權限只有 View Channel、Connect、Speak：

[邀請 SilentTalk Bot](https://discord.com/oauth2/authorize?client_id=1552128066719981608&scope=bot&permissions=3146752&integration_type=0)

## 準備 Discord Bot

1. 在 Discord Developer Portal 建立 Application 與 Bot。
2. Bot 邀請到測試伺服器，只授予 View Channel、Connect、Speak。
3. Developer Mode 下複製你自己的 Discord User ID，作為 `.env` 的 `OWNER_USER_ID`。
4. Bot 頁面 Reset Token 後取得 Bot Token。Application ID 與 Public Key 都不能用來登入 Bot。

真正的 `.env` 已由 `.gitignore` 排除，不能提交。若 token 曾公開，請在 Portal 立刻 Reset Token，並同步更新本機 `.env`。

## 安裝

下載或 clone repository 後，直接雙擊 `啟動 SilentTalk.cmd`。啟動檔會：

- 檢查並以 winget 安裝 Python 3.12 與 FFmpeg（缺少時才安裝）。
- 建立 `.venv`。
- 安裝 `requirements.txt` 內的套件。
- 若 `.env` 不存在，由 `.env.example` 建立並開啟記事本讓你填入憑證。
- 驗證 `.env` 與 `config.toml`。
- 呼叫 `scripts/restart_silenttalk.ps1`；它會先關閉任何正在執行的 SilentTalk，再從目前這份 repo 啟動唯一的新實例。

設定的責任刻意分開：一般可調參數只放 `config.toml`；只有 Discord Bot Token 與個人 User ID 放在不進版控的 `.env`。新主機第一次啟動時，在自動開啟的 `.env` 填入：

```dotenv
DISCORD_BOT_TOKEN=你的 Discord Bot Token
OWNER_USER_ID=你的 Discord User ID
```

## 驗證與執行

先加入一個 Discord 語音頻道，再跑 Gate 1：

```powershell
.\.venv\Scripts\python app.py --voice-smoke
```

聽到固定測試音後啟動完整應用：

```powershell
.\.venv\Scripts\python app.py --tts-smoke
```

聽到「等一下，我馬上回來。」後啟動完整應用：

```powershell
.\.venv\Scripts\python app.py
```

平常直接雙擊 `啟動 SilentTalk.cmd`。若舊版 SilentTalk 還在執行，啟動器會先結束舊實例再啟動目前 pull 下來的版本，因此不需要先手動退出。程式不會顯示大型主視窗；按 F8 會開啟輸入框，視窗內的「退出 SilentTalk」可以正常關閉程式。

- F8：開啟置頂輸入框
- Enter：送出；Shift+Enter：換行
- Ctrl+1～Ctrl+9：播放前九個快捷句
- Esc：關閉並清空輸入框
- F9：停止播放並清空 queue

執行自動測試：

```powershell
.\.venv\Scripts\python -m pytest -q
```

`silenttalk.log` 只記錄事件、job id、字數、延遲與錯誤類型；不記錄輸入全文、token 或音訊。

## 常見問題

### 按 F8 沒反應

- 確認已雙擊 `啟動 SilentTalk.cmd`。
- 正常透過 `啟動 SilentTalk.cmd` 啟動時會維持單一實例；若 F8/F9 仍被占用，檢查是否有其他程式使用相同快捷鍵。
- 檢查其他程式是否占用了 F8 或 F9。

### Bot 沒有加入語音頻道

- 確認 Owner User ID 正確。
- 確認 Bot 已加入目前的 Server。
- 確認 Bot 在該頻道有 View Channel、Connect、Speak。
- Stage Channel 不在目前支援範圍；請使用一般 Voice Channel。

### 播放中途斷線

- 已開始播放的句子不會自動重播，避免產生回音。
- 下一句開始前會重新同步 Voice 連線；若正處於重連 cooldown，該句會直接失敗而不是反覆撞 Discord。
- 自我修復正常以事件驅動處理，另有每 60 秒一次的低頻保險檢查。
