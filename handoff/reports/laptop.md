# Discord audit｜2026-10-07（Windows）

## 機魂劇本

本回合為 Discord 文字與語音稽核，沒有訓練資料工作，未讀使用者對話、人設或角色狀態內容。

## 時間與額度

回報時間依時鐘核對 2026-10-07 14:10:29 +08:00。本次固定實機事件視窗：10:39:08～13:57:32.926596 +08:00；不是稽核總耗時。平臺未提供 token／額度總數。

兩 repo 與 report worktree 均 pull --ff-only 成功。SilentTalk HEAD a5ee772、EdgeAgent HEAD 5422f02。discord_voice、discord_messages、runtime、task_runner 相對7355d68無差異。沒有開 sub-agent。

## 目標完成度統計（分母 29）

完成故障稽核與隔離重現；沒有修復、部署或真人驗收，不重新評定歷史29項。

**P1：語音替換沒有收回舊連線背景重連工作的控制權。**

owner：silenttalk/discord_voice.py:501 `_close_voice`，caller :303 `_connect_fresh_locked`、:248 `_follow`。只 await disconnect(force=True) 後建立替換連線；沒有終止／等待舊SDK重連runner。`_follow`也只選is_connected()，沒有區分SDK正在重連和真正退役。

實際安裝discord.py 2.7.1的voice_state.py:741一般異常分支先backoff，之後:743 disconnect(cleanup=False)、:746 _connect。disconnect本身不取消runner。隔離重現使用真VoiceConnectionState._poll_voice_ws、disconnect及app._close_voice，只mock網路。注入4006使runner進入backoff，app關閉舊voice並建立替換後，舊runner仍實際送channel=None並再次連線，兩個生命週期因此互相干擾。

實機15次4006、573次by force、573次Reconnect was unsuccessful；收音啟動574次，間隔中位數20.279621秒，符合SDK20秒等待加app重建。測試證實競態存在；固定週期與之相符，但缺少connection/task identity診斷，不能確定每一個實機週期都由它觸發，首次失效來源也未確認。不能把它全部歸咎於網路或DAVE。

修復應由voice transport唯一owner統一管理建立、SDK自動重連、退役、shutdown；替換前完成舊工作退役，不立即替換正在握手／重連的client。不能只調長監測週期掩蓋。回歸需驗舊工作不能再發離開／連線、transient reconnect、關閉及健康連線。

**P1：主人在文字頻道直接@固定變成Agent派工，和這次聊天目的衝突。**

owner：silenttalk/discord_messages.py:110、:176 `_opens_thread`；runtime._handle_turn的agent分支。主人在TextChannel直接@、沒有reference、角色開啟時，不看聊天意圖，一律開Agent串並標agent=True。聊天分支位於其後，串內主人文字也一律派工。

13:51:45.248245第一則即開串；13:54:00.734641第二則是串內文字。皆addressed=True、place=thread，兩次dispatched=True，角色聊天判斷及回覆皆0。這符合2026-10-05的舊規則，不能寫成新引入回歸；此次使用者明確要聊天，需交開發機處理角色／工具入口語意，筆電配合Discord caller與實測。不要直接取消所有@派工，造成既有工作入口失效。

**P2：Agent失敗事件沒有安全、穩定的原因碼。**

owner：silenttalk/copilot/task_runner.py:222 `_agent_event`、:279 `agent_result_posted`及EdgeAgent `/chat` error來源。兩次工作104891／175984ms，均kind=error、posted=True、task_marked=failed；是派工失敗，並非Discord沒收到@或貼不出錯誤結果。

數字log只記kind，未記穩定error code、失敗階段或例外類別，上游即使帶reason也沒有保留。因此不能確診為token截斷、推論逾時、模型品質或SDK故障。禁止把error message、prompt或結果全文寫入log補診斷；需由開發機提供結構化原因，再由筆電傳遞安全列舉。

## 測試執行結果

使用SilentTalk .venv，pytest -q -p no:cacheprovider，exit取pytest自己。

| 執行 | 結果 | exit |
|---|---|---|
| 合成重現＋voice_monitor／voice_receive／discord_config／copilot_runtime／agent_tasks第一次 | 1 failed、69 passed、2 warnings，4.68秒；fixture的AsyncMock回傳coroutine未await，尚無有效重現 | 1 |
| 同組第二次 | 1 failed、69 passed、1 warning，4.91秒；合成guild缺me.voice，不能走完reconnect，不能當產品失敗 | 1 |
| 修正fixture後同組 | 70 passed、1 warning，3.87秒；重現舊runner離開替換連線，確認主人@開串規則 | 0 |

warning為audioop deprecation。透過表示缺陷成功重現，不是修好了。未重跑全套、壓測、發Discord訊息或重啟。現有測試綠燈未涵蓋SDK退役競態。

可重跑合成重現：[discord-lifecycle-repro.py](discord-lifecycle-repro.py)。在SilentTalk repo：

```powershell
$env:PYTHONPATH = 'C:\Users\A8fm0\Downloads\SilentTalk'
.\.venv\Scripts\python.exe -m pytest C:\Users\A8fm0\Downloads\SilentTalk-laptop-report\handoff\reports\discord-lifecycle-repro.py -q -p no:cacheprovider
```

目前應2 passed表示現況缺陷存在。修復時轉為正式回歸，改為斷言舊runner不能幹擾替換。

交付附件與 handoff 文件驗證：6 passed、1 warning、1.05 秒，pytest exit 0；包含已複製的兩項重現與四項既有文件檢查。receipt 一致性檢查 exit 0，固定窗口、數字、重現 SHA256、十節與引用檔均核對；git diff --check exit 0。初次整份 report 的 apply_patch 因重複 target 被拒絕，未寫入；交付結果追加腳本第一次因定位 assertion 失敗，未寫入，改用直接 patch 完成。

## 修改檔案與 commit

沒有修改產品碼／正式測試、四個使用者設定檔。只重寫最新report，儲存合成重現與不含對話的數字receipt；提交／push到laptop-report。使用者本次audit授權讀相關程式，覆蓋工作檔僅讀檔案限制，沒有擴大成角色policy修復。

## 記憶體與速度

唯讀HTTP snapshot：18087 mode=character、ready=true、owner_pid=12076、context_size=65536、agent_slot=0、inference_slots=1、error空；18089 total_slots=1、n_ctx=65536。沒有生成probe；ready不能當Agent全流程可用。

程式metadata：SilentTalk wrapper15520／app12076，10:39:08 +08:00建立；Edge Python14444／17512、router12788、model child11280，約10:55建立。只是snapshot，禁止照抄PID停止。

## Discord 數字表

固定視窗7383筆metadata，僅在RAM解析時間、事件、數字、例外類別。receipt：[discord-audit-counts.json](discord-audit-counts.json)。

| 指標 | 數字 |
|---|---|
| discord_ready／gateway_resumed | 1／3 |
| Voice connecting／connection complete | 589／587 |
| voice_receive_started | 574，DAVE v1 |
| receive_stats／RTP packets／STT final | 297／0／0 |
| by force／Reconnect was unsuccessful | 573／573 |
| ConnectionClosed／4006 | 15／15 |
| ClientConnectionResetError | 1，11:01:54，早於本次文字測試 |
| voice_reconnect_backoff／voice_reconcile_failed | 1／1 |
| voice_transport_recovery／voice_playback_failed_recovering | 0／0 |
| text_message_received／thread_opened | 2／1 |
| agent_task_decision dispatched | 2 |
| agent_result_posted error／task_marked failed | 2／2 |
| character_line／job_done | 0／0 |

RTP0不能當麥克風或解密故障證據，沒有本次真人語音輸入確認。官方[Voice Close Event Codes](https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice-close-event-codes)將4006定義為session不再有效，不是直接歸因網路品質的程式碼；SDK by force事件對應Voice4014分支，與主Gateway同號程式碼意義不同。

## 紀錄目錄

沒有讀AgentRecords、人設或角色狀態內容；沒有對話／心事進入report、重現或receipt。沒有修改.env、settings.json、personas.json、character_state.json或紀錄設定。

## 使用者回饋

使用者回報：「我剛才在DC上使用@跟機魂聊天，結果大失敗，而且機魂本身在語音訊道，網路穩定情況下瘋狂進出，audit」。依最新要求做audit，未重做舊128K驗收或自動重啟。

## 給接手模型的交接指示

1. 先同步、讀本機工作檔與本回報。這是稽核成果，不是修復／部署完成。
2. Windows優先修語音生命週期owner，納入真SDK退役與transient reconnect測試；可沿用合成重現，不讀真人對話。
3. 開發機處理@聊天／派工的角色與工具語意、EdgeAgent結構化失敗原因，筆電配合caller與安全事件碼；不在Windows改模型、角色policy或lingua。
4. 修復後有界驗證。首次voice失效來源、兩次原工作具體失敗原因、修復後真人體驗仍未確認，不能寫成已修好或網路不穩，也不請使用者標註資料。
