# SilentTalk

SilentTalk 是 Discord 語音角色與回覆建議玩具。下載後啟動同一個入口，即會自動部署依賴與獨立的本機編程 Agent：EdgeAgent（已包在下載檔裡）。

| 產品 | 用途 | 啟動入口 |
|---|---|---|
| SilentTalk | 角色聊天、回覆選項、打字轉語音 | `啟動 SilentTalk.cmd` |
| EdgeAgent | 讀取專案、修改程式、執行驗證、審閱修改 | `開啟 EdgeAgent.cmd` 或 `edge-agent` |

兩者共用 EdgeAgent 的模型管理與推論服務，各自使用獨立 Python 環境。SilentTalk 租借角色模型，歸還後恢復原 Agent 配置；最多載入一個完整模型。對話與轉錄只留在記憶體。

## 下載、安裝與啟動

支援 Windows x64。從公開的 [SilentTalk 下載頁](https://github.com/nobody945946/SilentTalk-download/releases/latest) 下載最新的 `silenttalk-windows-*.zip`，解壓到要使用的資料夾，雙擊 `啟動 SilentTalk.cmd`。不需要 GitHub 帳號。

首次啟動會自動準備 Python 3.12、各自的 venv 與依賴、Git、Node／Pi SDK、推論引擎、公開 Agent 與角色基底、FFmpeg，以及語音辨識模型。不需預裝 Python、Git、winget 或 CUDA Toolkit；已有可用 NVIDIA 驅動時選擇 CUDA，否則使用 CPU，速度依硬體而異。

首次下載約 7–8 GB，建議保留至少 16 GB 可用磁碟空間。固定版本下載會驗證 SHA256；大型模型可續傳。中斷時重跑同一啟動器，完成的資產會沿用。後續啟動檢查部署完成紀錄與必要元件；元件缺損或版本改變時，由同一安裝流程修復。

下載頁是公開的，只放在 Windows 上驗證過的發行檔；ZIP 已附 EdgeAgent，安裝全程不用登入 GitHub。原始碼 repository 不公開；只有直接從 repository 原始碼啟動、而且沒有 ZIP 附的 EdgeAgent 時，才需要 repository 的存取權限。

| 項目 | 預設位置 |
|---|---|
| SilentTalk 程式、自己的 venv、FFmpeg、STT | 解壓的 SilentTalk 資料夾 |
| EdgeAgent 程式、自己的 venv 與 runtime | `%USERPROFILE%\EdgeAgent` |
| 編程／角色 GGUF 與 adapter（附帶的和自己的） | EdgeAgent 的 `models` 目錄 |

可用環境變數 `EDGE_AGENT_HOME` 指定其他 Agent 安裝位置，必須在 SilentTalk 目錄之外。已存在但版本過舊的 Agent 目錄會保留，另行安裝符合版本的來源。

### 首次 Discord 授權

1. 在 Discord Developer Portal 建立 Application 與 Bot。
2. 把 Bot 的邀請連結交給要使用的 Server 的管理員，由他開啟並選擇 Server：
   <https://discord.com/oauth2/authorize?client_id=1552128066719981608&scope=bot&permissions=309240859712>
   （換成別的 Bot 時，`client_id` 改成它的 Application ID。）連結已勾好 Bot 用到的 8 個權限：View Channel、Connect、Speak、Send Messages、Read Message History、Add Reactions、Create Public Threads、Send Messages in Threads。權限清單只寫在 `silenttalk/discord_voice.py` 的 `BOT_PERMISSIONS`，連結由同檔的 `invite_url()` 產生；Bot 登入後 `AppController.invite_link` 就是這條連結（連上 Discord 後，在「設定 → Discord」頁也可直接複製）。
3. 取得 Bot Token，並在 Discord Developer Mode 複製自己的 User ID。
4. 初次啟動時，在授權介面輸入這兩項資料。

新輸入存入 Windows 認證管理員，之後不用重填。既有 `.env` 優先，安裝器不修改它或其他使用者設定。Application ID 與 Public Key 不能代替 Bot Token。建立 Bot 與帳號授權仍是必要的一次性步驟。

預設只使用語音。要啟用文字聊天，需在設定開啟文字聊天，於 Developer Portal 開啟 Message Content Intent，並授予發送訊息權限。Bot 讀寫所在語音頻道的內建聊天室；角色模式下 Owner 在任何文字頻道 @ 它，它就從那則訊息開一個討論串，之後的對話都在串裡（不用再 @），不洗版原頻道。只有 Owner 能開串；串裡誰都能和角色聊。其他文字頻道的訊息不讀。每個討論串是獨立的對話：角色只在那個串裡回答、也只在那個串裡記得說過的話。

已經在 Server 裡的 Bot，權限清單變多時（例如討論串和表情），請管理員再開一次邀請連結，Discord 會更新它的權限。頻道自己的權限設定仍可能擋住（例如某個頻道不准開討論串），要在那個頻道的權限裡放行 Bot。Message Content Intent 不在邀請連結裡，由 Bot 擁有者在 [Developer Portal](https://discord.com/developers/applications) 開啟；批准按鈕不需要它，只有讀取打字內容時才需要。

## 日常使用

啟動後沒有大型主視窗。使用授權的 Discord 帳號加入一般語音頻道，Bot 會跟隨；跨 Server 時，目標 Server 也需先安裝 Bot。Stage Channel 不在目前支援範圍。

| 操作 | 按鍵／入口 |
|---|---|
| 開啟置頂視窗 | F8 |
| 送出文字／換行 | Enter／Shift+Enter |
| 停止目前播放並清空待播句子 | F9 |
| 播放前九個快捷句 | Ctrl+1～9 |
| 收起視窗 | Esc |
| 關閉 SilentTalk | F8 →「退出 SilentTalk」 |

左側只有「對話」「人設」「設定」三個入口。「對話」有三種模式，共用同一段記憶體中的對話：

- **角色：**用啟動器開啟時直接進入角色模式。預設「被叫到才回」：每一句都要叫它的名字（語音照發音比對，「雞魂」「基魂」這類聽錯的字也算；文字可以 @ 它），沒叫就不回，不會插進朋友間的對話；可改成「會主動加入」，或在冷場時找話題。切到其他模式會暫停。
- **選項：**產生最多四種角色會說的回覆。W／A／S／D 或方向鍵選擇，同鍵再按一次、Enter 或 Space 說出。R 換到待顯示的新選項，沒有時重新產生；E 帶到打字框修改，M 切換心情。中文輸入法若攔截按鍵，可改用方向鍵。
- **打字：**手動輸入後讓 Bot 說出。建議清單可用上下鍵選擇、Tab 帶入文字框；快捷句可新增、更新、刪除或雙擊播放。

開啟文字聊天後，角色在哪裡被問就在哪裡答：討論串打字回串裡，語音頻道裡依來源用文字或語音；選項模式可用 T 將選中回覆送到所在語音頻道的文字聊天。

預設角色是戰鎚 40K 的機魂 Machina-Prime-09A（馬基納，中性電子音，自認是機器）：新安裝就選好；以前的人設檔第一次讀到時會加入並選它，之後照你的選擇，這個內建角色不會從清單消失。人設頁設定角色的名字、身分、背景、想要的事、個性、人際關係與聲音。開啟「設定 → 聊天 → 讓主人交代 Agent 工作」後，角色可接令並透過 EdgeAgent 做事。聲線、語速與音效可試聽，試聽只在本機播放。標點會影響 EdgeTTS 的斷句與語氣，但不保證精確停頓或拉長音。

在 EdgeAgent「⋯ → 權限」開啟 Discord Agent，設定寫檔、執行指令、上網及可用資料夾；派工使用第一個資料夾，沒有設定時角色會請主人先設定。SilentTalk 租借時會傳送角色的基底和 LoRA，Agent 自動共用這個模型，不必再到 EdgeAgent 手動切換；歸還後恢復 EdgeAgent 原本的模型和 LoRA 選擇。租借期間也載入基底的看圖配件（E4B 約多 0.55 GB 記憶體，省 VRAM 時不佔顯示卡），讓聊天室貼的圖能交給 Agent 看。叫法（2026-10-05）：在語音頻道喊「機魂」＝用嘴巴 @ 它，開始語音聊天；在任何文字頻道打字提到「機魂」或 @ 它，就在那個頻道聊天（任何人都可以）；Owner 在文字頻道 @ 它會開一個討論串，那是 Owner 的 Agent 串：串裡 Owner 打的每一句都原封不動交給 Agent，別人的話不會變成工作。用說的、或 Owner 以外的人，都不能叫它動電腦。聊天裡任何人都能請它做「只進出這個對話」的事：讀的東西只來自這個聊天室裡大家貼的（文字、圖片、檔案）和公開網路，產出只是回到這個聊天室的一則訊息——例如查資料、寫程式（只寫不跑）、寫文章、看圖認字、翻譯或解釋一段指令。角色判斷要不要請 Agent 做；要的話 Agent 只拿得到網路、翻譯器和叫它的那則訊息（以及它回覆的那則）的附件（EdgeAgent 的 `public` 範圍：沒有電腦裡的檔案、指令、MCP，也不會問 Owner），這是由程式擋的，不靠模型自律。角色說它去做、再轉述重點，完整內容打在那個聊天室。Agent 串裡，角色先判斷這句有沒有要改動東西：只讀的工作以唯讀送出，任何改動都直接擋下；要改的話每次改動前私訊 Owner 批准（只有 Owner 按得到，沒回應就算拒絕），私訊送不出去就拒絕。受理的那則訊息會加上 ⚙️，完成換成 ✅、失敗或取消換成 ❌。結果直接貼在那個討論串（每段開頭標「【思考機回報】」，串貼不進去才改私訊），同一串之後的工作沿用同一個 Agent 對話；查資料的結果貼在原本的聊天室。討論串是公開的，頻道裡看得到串的人都看得到貼出的結果。SilentTalk 重開或忘了某個串之後（最多記 16 個），那個串的下一句話會先把串裡之前的訊息讀回記憶體（只當脈絡，不重新回答、派工或記錄；讀不到時角色會知道自己讀不到）。Owner 需允許同伺服器成員私訊，背景執行時仍可聊天。

設定頁提供聊天、Discord、聲音、聽力、本機模型與快捷鍵。變更自動保存；標示「需重開」的項目下次啟動生效。預設值在 `config.toml`，使用者變更在 `settings.json`，同名項目以後者優先。

## 編程 Agent 與模型切換

部署完成後執行 `edge-agent`，或在 Agent 安裝目錄雙擊 `開啟 EdgeAgent.cmd`。在介面選擇專案資料夾，輸入編程工作，查看工具操作與修改審閱。寫檔、編輯與 PowerShell 執行會先要求批准；Plan 模式只使用讀取工具。批准機制不是作業系統沙盒，執行程式仍具有目前帳號的權限。

Agent 預設為 `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf`（和角色同一個模型）、131,072 token context（角色租用時由兩邊共用）、thinking off，日常工作記憶目標和 context 一樣大。4 GB 顯示卡放不下的層自動放 CPU、模型鎖在記憶體，速度換成能用的 context。`Qwen3.5-4B-Q4_K_M.gguf` 也支援，考場上寫程式比 E4B 好，從模型頁下載後選用。

模型下載與熱切換使用 EdgeAgent 右上角「⋯ → 模型模組」：從 Hugging Face 列出檔案、下載並驗證後，選擇模型再「套用並切換」。下載完成不會自動切換。支援目前 llama.cpp 可載入的單檔 GGUF；切換失敗會嘗試恢復原配置。工作或角色租借中不能切換，先結束工作或退出 SilentTalk。

完整操作與實測由 EdgeAgent 自己的文件維護，安裝後在 Agent 安裝目錄（預設 `%USERPROFILE%\EdgeAgent`）：`README.md`（使用與模型管理）、`VALIDATION.md`（驗證與限制）。

### SilentTalk 的角色模型與 LoRA

「設定 → 本機模型」設定下次租借的角色基底，改完需重開。模型先放進 EdgeAgent 的 `models`，可透過 Agent 介面下載。首次部署只準備預設編程 4B 與公開 Gemma 4 E4B，不會下載下拉選單內所有替代模型。自訂角色模型可在 `config.toml` 的 `[copilot]` 以 `llm_model` 指定已安裝檔名，仍受使用者設定覆蓋。

租借時 EdgeAgent 同時載入角色的 adapter（這裡設定的）和 Agent 自己的 adapter（同一個檔只載一次），預設都不套用：Agent 的請求只點名它自己的，角色的請求只在 `character_lora_uses` 列出的部分點名角色的。兩邊用同一個 adapter 時，Agent 做事中角色也能即時回話；用不同的就得等 Agent 讓出模型。

- **預設（附帶）：**基底是預設的 E4B 時，帶上 EdgeAgent 附帶的 `machine-spirit-fw3n.q8_0.gguf`（EdgeAgent 部署時放進 `models`）。它同時是 Agent 的 adapter，所以 Agent 做事時機魂照樣即時回話（筆電 0.62 秒）。套用在它訓練過的部分：台詞和聊天級工作（`line,task`）。台詞盲評和上一版 `machine-spirit-char-v1` 打平（76 組：31 比 33，12 組平手）；聊天工作判斷 37/40（上一版 39/40，不套的 E4B 34/40），漏的三題都是「查最新消息」（2026-10-12）。換別的基底就不帶（adapter 只配得上它訓練的基底）。
- **自己的 adapter：**放入 EdgeAgent 的 `models`，在 SilentTalk `config.toml` 的 `[copilot]` 設定 `character_lora` 為檔名，確認 `llm_model` 是訓練基底，重開後生效；設為空字串就不用任何 adapter。`settings.json` 的同名項目仍優先。

`character_lora_uses` 指定角色的哪些請求套用：`called`（被叫到判斷）、`active`（主動插話判斷）、`line`（角色回覆）、`options`（回覆選項）、`task`（聊天級工作：要不要交給思考機、交辦的指示）、`scope`（主人串裡的工作要不要改動）。單獨用 EdgeAgent 時，adapter 在它的「模型模組」選。

架構篩選只是最低檢查；同架構不同基底也可能不相容。E4B 的 adapter 不能任意套在 Qwen 或其他模型。

## 資料與外部服務

語音辨識與模型推論在本機。Discord 與 EdgeTTS 需要網路；EdgeTTS 會將要合成的文字送到外部語音服務，但不需要額外付費 API key。

未開啟紀錄時，對話、轉錄、候選與摘要只在 RAM，關閉後不恢復。設定「紀錄」頁選擇已存在的紀錄資料夾，按「設為紀錄資料夾」，再開啟「記錄對話」。原生 SSD 上的一般目錄即可，C 槽也可以，不需要加密容器、獨立分割區或解鎖；設定步驟會建立 `.agent-records` 標記檔，代表這是你指定的紀錄位置。轉錄文字（誰、何時、打字或語音、內容；不含錄音）只寫進這裡；資料夾無法使用或缺少標記時顯示「暫停」，也不會改寫到別處。紀錄只給你自己用，不在頻道提示。未採用候選不進 context；語音播放或文字送出成功後才記錄為已說出的回覆。自動壓縮可濃縮較早內容，保留近期原文。角色與 Agent context 各自設定，預設分別為 32,768 與 131,072 token。共用時每個 slot 以兩者較大值部署，不縮小設定的 context；所需記憶體可能增加，載入失敗會回報。

程式保存使用者設定、人設、快捷句、UI 偏好；選用角色長期狀態時，可保存角色自己的近況與心情，不能包含人的對話原文。合成音訊在播放期間使用暫存檔並於結束清除。log 只記事件與數字，不記對話全文或 token。

發行包附帶 E4B 的兩個 LoRA（Agent 和機魂各一個，見上方「角色模型與 LoRA」），排除個人設定、憑證、角色狀態和模型權重；不把使用者資料交給打包器。

## 常見問題與驗收

- **下載中斷／元件損壞：**重跑同一啟動器。只部署用 `啟動 SilentTalk.cmd --setup-only`；完整驗收用 `--check`，會實際載入 STT、租借角色並歸還，不連 Discord。正在租借時先退出會話。
- **Bot 沒加入或缺權限：**確認 Owner ID，並請 Server 管理員用邀請連結再邀請一次（會補上缺的權限；可在「設定 → Discord」頁複製連結）。
- **F8 無反應：**確認已啟動，並檢查其他程式是否占用快捷鍵。
- **播放中斷線：**已開始的句子不自動重播以避免回音；程式恢復連線後讓下一句接續。
- **換模型失敗：**確認沒有 Agent 工作或角色租借，且模型已下載完整、格式與引擎相容。
- **退出後仍占顯存：**歸還會重新載入原 Agent。要釋放顯存，執行 `edge-agent stop` 或在 Agent 的「⋯」選「關閉EdgeAgent」。

## 開發與發行

架構與責任地圖見 [ARCHITECTURE.md](ARCHITECTURE.md)。Agent 工作入口是 [AGENTS.md](AGENTS.md)，Windows 交接見其指定工作檔。開發分支為 `copilot-story-mode`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

真人 Discord 播放驗收需已有授權與語音連線；可分別執行 `app.py --voice-smoke` 與 `app.py --tts-smoke`，不要與不連 Discord 的部署 `--check` 混淆。

commit 後，用 manifest 指定且已驗證的 EdgeAgent 來源包建立玩家 ZIP：

```powershell
python scripts/package_windows.py --edge-source <EdgeAgent來源包.zip> --output <Windows發行包.zip>
```

打包器從 Git commit 讀取應用程式 allowlist，核對 EdgeAgent SHA256，再放入既有下載快取；可用 `--revision` 指定 commit。產品與模型管理只有同一套部署／啟動流程。

## 授權

SilentTalk 與 EdgeAgent 以 [PolyForm Strict License 1.0.0](LICENSE) 授權，著作權屬於 nobody945946。以下是白話摘要，實際以英文條文為準：

- **可以**：個人、非商業的使用，例如自己玩、學習、研究、興趣專案；學校、公益團體、研究與政府機構也可以使用。
- **不可以**：重新散布或轉載（想分享請給[官方下載頁](https://github.com/nobody945946/SilentTalk-download/releases/latest)的連結）；修改後發布或做成衍生作品；用於商業目的。
- **免責**：在法律允許的範圍內，軟體照現狀提供，不做任何保證；使用造成的損失（例如 Agent 改動或刪除了檔案），作者不負責。
- **違反時**：收到書面通知後 32 天內改正並補救，可以繼續使用；否則授權終止。

這份授權只涵蓋 nobody945946 撰寫的程式。`edge_agent/skills/grill-me` 改寫自 [mattpocock/skills](https://github.com/mattpocock/skills)，依其 MIT 授權（同資料夾的 `LICENSE`）。安裝時下載的 Python 與 Node 套件、推論引擎、語音模型與語言模型，各自依原本的授權條款，不在這份授權範圍內。
