# Windows 工作檔：第 7 回合 A（語音修正驗收）

更新：2026-10-07 晚｜程式 copilot-story-mode｜回報 laptop-report｜上一版：開發機 `archive/laptop-2026-10-07-round6-continued.md`（不必讀）

## 這回合只做一件事

你的 Discord 稽核（2026-10-07）找到語音反覆進出。開發機照使用者的指示修好並推了（SilentTalk `87578a9`）。這回合在真的 Discord 上驗它。EdgeAgent 的改動（拆檔、Agent 失敗原因碼、通用修正）**今晚還在開發機量**，量完才推，下一回合（B）再一起驗。所以這回合**不要**測 Agent 派工，免得做兩次。

修了什麼（不用讀程式）：
- 連線改成 `reconnect=False`：重連只由 app 自己的 reconcile 負責（有退避）；SDK 仍會在 4015 時 resume、被移動頻道時跟上。
- 退役舊連線時，先取消 discord.py 的背景 poller 和未完成的 connect，再斷線。舊 poller 不會再「醒來→離開頻道→自己重連」把新連線踢掉。
- 你的重現已改成正式回歸測試 `tests/test_voice_lifecycle.py`。舊程式會失敗，新程式會通過。

## 步驟

1. 在 SilentTalk 執行 `git pull --ff-only`；拉不下來就停下回報。
2. 跑完整測試（`--basetemp`，看 pytest 自己的 exit code）。預期 357 passed 上下，其中 `tests/test_voice_lifecycle.py` 要通過：這支就是語音修正的驗證，用的是真的 discord.py。失敗就停下回報，不要改。
3. 重啟 SilentTalk 讓修正生效（核對過的 PID）。**不安排掛機測試，也不要求使用者做任何事。**
4. 之後使用者正常使用 Discord 時，順手從 log 數這次 session 的 `Disconnected from voice by force`、`Reconnect was unsuccessful`、4006 次數。沒有用到語音就寫「沒有語音使用，未觀察」。
5. 推回報（整份換掉，推到 `laptop-report`）。

## 回報格式（沿用固定十節）

機魂劇本（本回合無）／時間與額度／目標完成度（V1：回歸測試通過＋正常使用時的被踢次數）／測試執行結果（每次 pytest 都列，含失敗）／修改檔案與 commit（應該是無）／記憶體與速度（只寫看得到的數字）／Discord 數字表（上面那些）／紀錄目錄（只看 metadata）／使用者回饋（使用者自己說的感想，原話照錄）／給接手模型的交接指示。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄。
- 不動 `.env`、`settings.json`、`personas.json`、`character_state.json`。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事。
- 不在 `main` 上 commit。程式錯誤若不在這份的範圍，照實寫進回報，不要自己改。
