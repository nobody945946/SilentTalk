# Windows 工作檔：第 7 回合 A（語音修正驗收）

更新：2026-10-07 晚｜程式 copilot-story-mode｜回報 laptop-report｜上一版：開發機 `archive/laptop-2026-10-07-round6-continued.md`（不必讀）

## 這回合只做一件事

你的 Discord 稽核（2026-10-07）找到語音反覆進出。開發機照使用者的指示修好並推了（SilentTalk `87578a9`）。這回合在真的 Discord 上驗它。EdgeAgent 的改動（拆檔、Agent 失敗原因碼、通用修正）**今晚還在開發機量**，量完才推，下一回合（B）再一起驗。所以這回合**不要**測 Agent 派工，免得做兩次。

修了什麼（不用讀程式）：
- 連線改成 `reconnect=False`：重連只由 app 自己的 reconcile 負責（有退避）；SDK 仍會在 4015 時 resume、被移動頻道時跟上。
- 退役舊連線時，先取消 discord.py 的背景 poller 和未完成的 connect，再斷線。舊 poller 不會再「醒來→離開頻道→自己重連」把新連線踢掉。
- 你的重現已改成正式回歸測試 `tests/test_voice_lifecycle.py`。舊程式會失敗，新程式會通過。

## 步驟

1. 在 SilentTalk 執行 `git pull --ff-only`，拉不下來就停下回報。再讀 AGENTS.md 和這份。EdgeAgent 這回合不用拉。
2. 跑完整測試：`.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp <暫存資料夾>`。預期 357 passed、13 skipped 上下，Windows 專用的 skip 數可能不同。看 pytest 自己的 exit code。失敗就停下回報，不要改。
3. 照平常的方式重啟 SilentTalk（`scripts\restart_silenttalk.ps1`；或照使用者習慣的方法）。關程序只用核對過的 PID。
4. 使用者在語音頻道時，讓 app 至少連續掛 **30 分鐘**。這期間不要求使用者講話；如果使用者剛好講話，就照實記下。
5. 用 `scripts\dev\log_summary.py` 只算這次 session 的數字，切點是這次 app 程序的建立時間。另外算你稽核時的那幾項：
   - `Disconnected from voice by force`；
   - `Reconnect was unsuccessful`；
   - 4006 和 `ConnectionClosed`；
   - `voice_receive_started` 次數和間隔中位數；
   - `voice_reconnect_backoff`、`voice_reconcile_failed`。

   只記事件名稱和次數，不記內容。
6. 判定：
   - **通過**：30 分鐘內 `by force` 和 `voice_receive_started` 的次數個位數以內，而且沒有固定 20 秒左右的循環。
   - **沒通過**：照實記數字和例外類別，附上最早一次失效前後 10 行 log。只要事件名稱、時間、close code，不要訊息內容。不要自己改程式，寫進回報給開發機。
7. 推回報：只寫最新這一回合，整份換掉；推到 `laptop-report`。

## 回報格式（沿用固定十節）

機魂劇本（本回合無）／時間與額度／目標完成度（本回合只有 V1：語音穩定 30 分鐘）／測試執行結果（每次 pytest 都列，含失敗）／修改檔案與 commit（應該是無）／記憶體與速度（只寫看得到的數字）／Discord 數字表（上面那些）／紀錄目錄（只看 metadata）／使用者回饋（使用者自己說的感想，原話照錄）／給接手模型的交接指示。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄。
- 不動 `.env`、`settings.json`、`personas.json`、`character_state.json`。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事。
- 不在 `main` 上 commit。程式錯誤若不在這份的範圍，照實寫進回報，不要自己改。
