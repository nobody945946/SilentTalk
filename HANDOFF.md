# SilentTalk Copilot 交接（2026-09-25）

> 給接手的模型：這份文件是「照著做」用的。一次只做一個任務，每個任務最後都有**驗證指令**和**完成標準**；沒達標就不要進下一步。遇到文件沒寫到的判斷，停下來問使用者，不要猜。

---

## 0. 先讀這三段（5 分鐘）

**專案是什麼：** Windows 桌面程式。Discord Bot 在語音頻道替使用者用 TTS 說話；Copilot 功能會聽頻道裡其他人講話 → 本機 STT 轉文字 → 本機 LLM 產生四種回覆 → 使用者用 WASD 選一個 → Bot 說出來。整體架構看 [ARCHITECTURE.md](ARCHITECTURE.md)。

**上一輪做完了什麼：**

| 項目 | 狀態 |
|---|---|
| 模型下載網址 404（app 在新電腦上根本啟動不了） | 已修：改用 Qwen3-1.7B Q4_K_M，下載由 `config.toml` 的 `copilot.llm_model` 決定 |
| Qwen3-0.6B 回覆格式幾乎全錯 | 已換掉（0/32 格合格 → 1.7B 32/32） |
| STT 句尾掉字（CER 14.7%） | 已修：tail padding 0.2 s → 0.66 s（CER ~8%） |
| 開放式麥克風的人 25 秒才斷句 | 已修：sherpa endpoint rules，約 1 秒斷句 |
| STT 輸出簡體 | 已修：OpenCC `s2twp` 轉台灣繁體（STT 與 LLM 輸出都轉） |
| Discord DAVE（E2EE）接收的兩個風險 | 已加防護（`discord_voice.py`） |
| AI 劇情模式（WASD 四選項分頁） | 已完成（`story_ui.py`） |
| 本機一鍵驗收 `app.py --copilot-smoke` | 已完成 |
| 評分工具 `scripts/dev/*.py` | 已完成，基準數字在下面 |

**還沒做的（就是你的任務）：** 見第 3 節 T0～T5，依序做。

---

## 1. 開工前的環境準備

### 1.1 Python 環境（Linux 或 Windows 都可）

需要 Python **3.12**（專案用 `tomllib`、`StrEnum`；3.10 跑不起來）。

```bash
# 在 repo 根目錄
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python.exe
.venv/bin/python -m pytest -q
```

**完成標準：** `64 passed`（數字可能因你新增測試而變多，但不能有 failed）。

### 1.2 本機模型（跑 smoke / eval 才需要）

```bash
.venv/bin/python scripts/setup_copilot.py
```

會下載約 1.4 GB 到 `.runtime/models/`（此資料夾已被 git 忽略，**絕對不要 commit**）。每個檔案都會驗 SHA256；看到 `SilentTalk Copilot models are ready.` 才算成功。

### 1.3 llama-server

- **Windows：** `winget install --id ggml.llamacpp -e`（裝的是 **Vulkan** 版，NVIDIA/AMD/Intel GPU 都能用）。
- **Linux：** 用上一輪驗證過的 b11179 Vulkan 版（不要點 GitHub 的「Latest」，那個 `v0.5.0` 沒有執行檔）：
  ```bash
  curl -LO https://github.com/ggml-org/llama.cpp/releases/download/b11179/llama-b11179-bin-ubuntu-vulkan-x64.tar.gz
  tar xzf llama-b11179-bin-ubuntu-vulkan-x64.tar.gz      # 解出 llama-b11179/
  export PATH=/解壓路徑:$PATH
  export LD_LIBRARY_PATH=/解壓路徑      # 否則會找不到 libggml*.so
  llama-server --list-devices           # 應該列出 Vulkan0: 你的 GPU
  ```

### 1.4 常用檢查指令（每個任務結束都要跑）

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
.venv/bin/python -m compileall -q app.py silenttalk scripts/setup_copilot.py
```

這三個指令目前都是乾淨的（ruff 應印出 `All checks passed!`）。`ruff check` 不帶這些參數會跑出一堆**原本就存在**的警告（BLE001 等），不用管，也不要為了消警告去大改既有程式。

---

## 2. 規則（違反任何一條都要先問使用者）

1. **不要換回 Qwen3-0.6B。** 實測它 32 格只填 0 格，會把對話紀錄原樣抄回來。Qwen 官方 repo 也沒有 0.6B 的 Q4_K_M（只有 Q8_0）。
2. **對話內容不能寫進硬碟。** 轉錄文字、PCM、prompt 都只在 RAM。所以：
   - 不要提高 llama-server 的 `-lv` / `--verbose`，也不要加 `--log-file`、`--log-prompts-dir`。
   - `_LOG` 只能記數字、長度、ID、錯誤類型，不能記使用者講的話。
3. **回覆方向只有一個來源：** `silenttalk/copilot/types.py` 的 `REPLY_LANES`。要改標籤、按鍵、新增方向，只改那裡＋`llm.py` 的 prompt，UI 會自動跟著變。
4. **劇情模式的 WASD 只能在 SilentTalk 視窗有焦點時生效。** 不要把 W/A/S/D 註冊成全域熱鍵——使用者在打遊戲，會直接壞掉移動鍵。
5. **不要 `ruff format` 整個 repo。** repo 沒有統一格式化過，整包格式化會產生幾千行無關 diff。只格式化你新增的檔案。
6. **殺程序不要用 `pkill -f <字串>`**：如果你的 shell 指令本身也含那個字串，會把自己的 shell 殺掉（exit code 144）。用 `pgrep -x 程序名` 取得 PID 再 `kill`。
7. 改 prompt、STT、模型之前，**先跑一次對應的 eval 記下「改之前」的分數**，改完再跑一次比較。分數變差就回退。
8. Commit 前一定要跑 1.4 的三個指令。不要在 `main` 直接 commit，先開分支。

---

## 3. 任務清單（依序做）

### T0｜把上一輪的改動提交進 git

**什麼時候要做：** `git status` 還看得到下列未提交檔案時。已經提交過就跳過。

新增：`HANDOFF.md`、`silenttalk/story_ui.py`、`silenttalk/ime.py`、`silenttalk/copilot/script.py`、`silenttalk/copilot/smoke.py`、`scripts/dev/*.py`、`tests/test_copilot_runtime.py`、`tests/test_copilot_script.py`
修改：約 20 個檔案（`git diff --stat` 看得到）。

步驟：
```bash
git checkout -b copilot-story-mode
.venv/bin/python -m pytest -q          # 必須全過
git add -A
git status                             # 確認沒有 .runtime/、.env、*.log 被加進去
git commit -m "Fix Copilot model download, STT accuracy, add WASD story mode"
```

**完成標準：** `git status` 乾淨；`git log -1 --stat` 裡沒有 `.runtime/` 或 `.env`。

---

### T1｜在 Windows + RTX 3050 Ti 筆電實機驗收（需要使用者本人的電腦）

**為什麼：** 所有速度數字是在 RTX 3090 上量的，3050 Ti 是推估（見第 4 節）。必須實測。

這個任務要請**使用者**在那台筆電上操作，你負責給他指令、看他貼回來的輸出。

1. 雙擊 `啟動 SilentTalk.cmd`，等它跑完（第一次會下載約 1.4 GB）。
2. 關掉 SilentTalk（F8 → 退出），在 repo 資料夾開 PowerShell：
   ```powershell
   .venv\Scripts\python.exe app.py --copilot-smoke
   ```
3. 看輸出：

| 看到什麼 | 代表什麼 | 怎麼辦 |
|---|---|---|
| `llama.cpp 看到的 GPU：Vulkan0: NVIDIA GeForce RTX 3050 Ti ...` | GPU 有抓到 | 正常 |
| `沒有（CPU 模式…）` | llama.cpp 沒看到 GPU | 請使用者更新 NVIDIA 驅動；筆電要確認不是被強制用內顯 |
| `STT PASS / LLM PASS`，exit code 0 | 驗收通過 | 記下延遲中位數 |
| `延遲中位數` > 3 s | 太慢 | 先確認 GPU 行；若 GPU 正常仍慢，回報給使用者，不要自己換模型 |
| `格式 不合格` | 模型沒照四行格式 | 確認 `config.toml` 的 `llm_model` 是 `Qwen3-1.7B-Q4_K_M.gguf` |
| exit code 5 | 有 gate FAIL | 看是哪個 gate 的哪一行 |

4. 再請使用者正常啟動、進 Discord 語音、請朋友講幾句話，然後打開 `silenttalk.log` 搜尋：
   - `copilot_llm_devices` → 應該有 3050 Ti
   - `voice_receive_started dave_version=1` → 接收有開、DAVE 正常
   - `voice_receive_waiting reason=no_dave_session` 出現超過 10 次 → 回報（見 T4）
   - `copilot_suggestion_ready latency_ms=...` → 每次生成的真實延遲（目標 < 1500）
   - `copilot_turn_final` → STT 有斷句

**完成標準：** smoke 全 PASS，且 log 裡 `copilot_suggestion_ready` 的 `latency_ms` 中位數 < 3000。把實測數字寫回本檔第 4 節的「3050 Ti 實測」欄。

---

### T2｜修正「同意」選項常常變成問句

**問題：** LLM 的四個方向會互相污染。實測 1.7B 有 **50–62%** 的「同意」回覆是問句（例：「你覺得B點守的人是不是有特別的技能？」），那應該是「追問」的工作。

**要改的檔案：** 只改 `silenttalk/copilot/llm.py` 的 `_build_prompt()`。

**步驟：**
1. 先量基準（改之前）：
   ```bash
   .venv/bin/python scripts/dev/llm_eval.py --runs 3
   ```
   記下 `agree_is_question` 的數字。
2. 修改 prompt。建議做法（一次試一個，每次都重新量）：
   - 在 `AGREE：` 那行加上「必須是肯定句，不可以用問號結尾」。
   - 在四行格式說明前面加**一個**完整範例（一段假對話＋四行正確輸出）。範例要是跟 `LLM_SCENES` **不同**的情境，否則分數會作弊般地變好。
   - 不要讓 prompt 變得很長：每多約 300 字，3050 Ti 上每次生成大約多 0.1–0.2 秒。
3. 重跑 `llm_eval.py --runs 3`。

**完成標準（`--runs 3`）：**
- `agree_is_question` ≤ 0.20
- `lanes_filled` ≥ 0.95、`ask_is_question` ≥ 0.90、`simplified` = 0、`median_seconds` 沒有比改前多 30% 以上
- 最後印出 `ALL TARGETS MET`
- `pytest -q` 全過（`tests/test_copilot_llm.py` 測的是 parser，不會因 prompt 改動而壞）

**不要做：** 不要在 parser 裡「把問號刪掉」來騙分數；不要換模型。

---

### T3｜STT 升級：Silero VAD + SenseVoice（較大的任務，分四步做）

**為什麼：** 同一組測試音檔，SenseVoice 的 CER 是 **6.0%**（Paraformer 約 8%），完全不掉句尾、有標點、CPU 更省。代價是多下載約 240 MB。

**原則：** 新引擎做成**可切換**，預設仍是 Paraformer，直到 eval 證明新的比較好，才請使用者決定要不要改預設。

#### T3-1 下載設定
在 `scripts/setup_copilot.py` 的 `ASSETS` 後面**另外**加一組 `SENSEVOICE_ASSETS`，只有 `config.toml` 的 `copilot.stt_engine == "sensevoice"` 時才下載（照 `llm_asset` 的寫法）。資料（已驗證）：

| 檔案 | 網址 | 位元組 | sha256 |
|---|---|---|---|
| `.runtime/models/sensevoice/model.int8.onnx` | `https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/model.int8.onnx?download=true` | 239,233,841 | `c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51` |
| `.runtime/models/sensevoice/tokens.txt` | `https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/tokens.txt?download=true` | 315,894 | `f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc` |
| `.runtime/models/vad/silero_vad.onnx` | `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx` | 643,854 | `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6` |

`min_size` 用上表位元組數的 95% 即可。

#### T3-2 設定欄位
`silenttalk/config.py` 的 `CopilotConfig` 加 `stt_engine: str = "paraformer"`，`load_settings()` 只接受 `"paraformer"` 或 `"sensevoice"`，其他值丟 `ConfigError`。在 `tests/test_config.py` 加一個測試：非法值會被拒絕。

#### T3-3 新的轉錄器
新增 `silenttalk/copilot/stt_offline.py`，類別 `OfflineTranscriber`。**公開介面必須和 `StreamingTranscriber` 完全一樣**（`__init__(model_dir, on_turn, on_error, *, endpoint_silence_ms=650)`、`start()`、`stop()`、`push_pcm(speaker_id, speaker_name, pcm)`），這樣 `runtime.py` 只要依設定選類別，其他都不用動。

直接照抄 `stt.py` 的結構（一條背景 thread、一個 queue、每位 speaker 一個狀態），只換掉辨識部分：

```python
import numpy as np
import sherpa_onnx

vad_config = sherpa_onnx.VadModelConfig()
vad_config.sample_rate = 16000
vad_config.silero_vad.model = str(vad_dir / "silero_vad.onnx")
vad_config.silero_vad.threshold = 0.5
vad_config.silero_vad.min_silence_duration = 0.5
vad_config.silero_vad.min_speech_duration = 0.25
vad_config.silero_vad.max_speech_duration = 20
vad_config.silero_vad.window_size = 512
# 每位 speaker 各自一個 VAD：
vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model=str(sv_dir / "model.int8.onnx"),
    tokens=str(sv_dir / "tokens.txt"),
    num_threads=1,
    language="auto",
    use_itn=True,
)

# 收到 PCM：48k stereo s16le → mono float32 → 16k → vad.accept_waveform(samples)
# 之後：
while not vad.empty():
    segment = vad.front
    vad.pop()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, np.array(segment.samples, dtype=np.float32))
    recognizer.decode_stream(stream)
    text = stream.result.text          # 送進 self._emit(...)，它會做 s2twp 轉換
# 某位 speaker 650 ms 沒有封包時：vad.flush()，再跑一次上面的 while 迴圈。
```

注意：
- `scipy` 目前**不在** requirements 裡。先試 `numpy` 自己做（48000→16000 是整數 3 倍，可用簡單低通＋每 3 點取 1 點）；真的需要 scipy 再問使用者要不要加依賴。
- 文字送出前一定要經過 `to_taiwan_traditional()`（`silenttalk/copilot/script.py`）。
- `sherpa_onnx` 的 API 名稱以 `sherpa-onnx==1.13.8` 為準；不確定時用 `python -c "import sherpa_onnx; help(sherpa_onnx.OfflineRecognizer.from_sense_voice)"` 查，不要猜。

#### T3-4 接上並驗證
1. `runtime.py`：依 `config.stt_engine` 選 `StreamingTranscriber` 或 `OfflineTranscriber`（`asr_dir` 也要跟著換）。
2. `scripts/dev/stt_eval.py` 加 `--engine sensevoice` 參數（`build_transcriber` 在 `silenttalk/copilot/smoke.py`，一起改）。
3. 驗證：
   ```bash
   .venv/bin/python scripts/dev/stt_eval.py                       # paraformer，應 ~8%
   .venv/bin/python scripts/dev/stt_eval.py --engine sensevoice   # 目標 ≤ 6.5%
   .venv/bin/python -m pytest -q
   ```

**完成標準：** sensevoice 平均 CER ≤ 6.5%，且沒有任何一句「最後一個字消失」；paraformer 分數不變；測試全過。**預設值維持 `paraformer`**，把兩個分數回報給使用者，由使用者決定要不要改預設。

---

### T4｜修補 discord-ext-voice-recv fork（需要使用者的 GitHub 帳號，先問）

**為什麼：** 目前 `requirements.txt` 釘的是 `rdphillips7/discord-ext-voice-recv@ddd2860`（上游 PR #54，支援 DAVE 解密）。我們在 `discord_voice.py` 已經繞過它的兩個 bug，但從源頭修最乾淨。

需要改 fork 的 `discord/ext/voice_recv/opus.py` 三處：
1. 約第 63 行 `self.vc._connection.dave_session.set_passthrough_mode(True, 10)` 前面加 `if self.vc._connection.dave_session is not None:`。
2. 約第 151 行 `dave_session.decrypt(member.id, ...)` 改用 `self._cached_id`（`member` 可能是 None）。
3. `dave_protocol_version > 0` 但 `dave_session.ready` 為 False 時，直接丟掉這個封包（回傳 `source=None`），不要把密文送去 opus 解碼。

步驟：請使用者 fork → 你寫 patch → 使用者 push → 把 `requirements.txt` 的網址換成新 commit 的 zip → `pip install -r requirements.txt` → `pytest -q` → 請使用者在 Discord 實測（T1 第 4 步的 log 檢查）。

**完成標準：** Discord 實測時 log 有 `voice_receive_started dave_version=1`、有 `copilot_turn_final`、沒有 `voice_transport_recovery` 反覆出現。
**`discord_voice.py` 裡現有的防護不要刪**，留著當第二層保險。

---

### T5｜（可選，先問使用者）不切視窗也能選選項

劇情模式目前要先按 F8 讓視窗取得焦點才能按 WASD。若使用者想在遊戲中直接選：`silenttalk/hotkeys.py` 目前只支援 F1–F12。可以加「修飾鍵＋數字」（例如 Ctrl+Alt+1～4）的全域熱鍵對應四個方向——**但絕不能註冊單獨的 W/A/S/D**（規則 4）。這是設計決定，動手前先問使用者要哪組按鍵。

---

## 4. 參考數字（都是 2026-09-25 實測）

### LLM（llama.cpp b11179 Vulkan，ctx 4096，`--parallel 1`）

| 模型 | VRAM | 四行格式 | RTX 3090 每次延遲 | 3050 Ti 推估 | 3050 Ti 實測（T1 填） |
|---|---|---|---|---|---|
| Qwen3-0.6B（舊） | 0.9 GB | 0/32 ❌ | 0.2 s | — | — |
| **Qwen3-1.7B Q4_K_M（預設）** | **1.6 GB** | 32/32 ✅ | 0.35 s | 1–1.5 s | |
| Qwen3-4B Q4_K_M | 3.1 GB | 32/32 ✅ | 0.6 s | 1.5–2.5 s，但 4 GB 會太擠 | |
| 1.7B 純 CPU（6 threads） | — | — | 約 28 token/s → 約 3 s | 筆電 CPU 更慢 | |

3050 Ti 推估方法：生成速度 ∝ 記憶體頻寬（3090 936 GB/s vs 3050 Ti Laptop 192 GB/s，保守取 1/3～1/5）；prompt 處理 ∝ 算力（約 1/5～1/6）。

`scripts/dev/llm_eval.py --runs 2` 基準（1.7B）：`lanes_filled 1.00`、`simplified 0.00`、`agree_is_question 0.50–0.62`（T2 要修）、`ask_is_question 1.00`、`median_seconds 0.36`（3090）。

### STT（`scripts/dev/stt_eval.py`，16 句 EdgeTTS 台灣腔，4 句加噪音）

| 設定 | 平均 CER |
|---|---|
| Paraformer，舊 0.2 s tail | 14.7% |
| **Paraformer，0.66 s tail（目前）** | **8.2%** |
| SenseVoice int8（T3 目標） | 6.0% |

模型本身的固定錯誤（不是 bug，換 SenseVoice 也大多還在）：boss→包/寶、lag→了鉤、打野→達也、補師→不是。

### 已驗證的下載資訊

| 檔名（`.runtime/models/llm/`） | 來源 | 位元組 | sha256 |
|---|---|---|---|
| `Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF` | 1,107,409,472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` |
| `Qwen3-4B-Q4_K_M.gguf` | `Qwen/Qwen3-4B-GGUF`（官方） | 2,497,280,256 | `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5` |

---

## 5. 工具速查

| 指令 | 用途 | 需要 |
|---|---|---|
| `python app.py --copilot-smoke` | 本機 STT＋LLM 一鍵驗收（不需 Discord）；exit 0＝通過 | `.env`、模型、llama-server、ffmpeg、網路（EdgeTTS） |
| `python scripts/dev/stt_eval.py` | STT 準確度分數（16 句） | ASR 模型、ffmpeg；第一次要網路，之後用快取 `.runtime/dev/stt_samples/` |
| `python scripts/dev/llm_eval.py [--model F] [--runs N]` | LLM 格式／方向／速度分數 | llama-server、LLM 模型 |
| `python scripts/dev/ui_preview.py` | 劇情模式各狀態截圖到 `.runtime/dev/ui_preview/`，並檢查按鍵流程 | `pip install pillow`；Linux 要 `xvfb-run -a` 且加 `--font "Noto Sans CJK TC"` |
| `python app.py --voice-smoke` / `--tts-smoke` | Discord 播放驗收（原有功能） | 真的 Discord Bot 與語音頻道 |

Linux 上 `ui_preview.py` 截圖出現方框字（tofu）是正常的：那台機器沒有「Microsoft JhengHei UI」字型，Tk 也可能沒有 CJK fallback。只看版面，不看字。

---

## 6. 出問題時先看這裡

| 症狀 | 最可能原因 | 檢查 |
|---|---|---|
| `setup_copilot.py` 下載失敗 / SHA256 mismatch | 網路中斷或檔案被換 | 重跑一次；仍 mismatch 就停下來回報，**不要**自己改 hash |
| `找不到 llama-server.exe` | winget 沒裝或 PATH 沒更新 | 重開終端機；`where llama-server` |
| `llama-server 啟動失敗，exit code=…｜…` | 錯誤訊息在 `｜` 後面 | 常見：port 被舊程序占用（跑 `scripts/restart_silenttalk.ps1`）、VRAM 不足（把 `llm_gpu_layers` 降低或設 0） |
| 劇情模式按 WASD 沒反應 | 中文輸入法攔截 | 程式會自動關 IME；仍不行就切英數或用方向鍵，並回報 |
| 選項一直「思考中」 | LLM 請求逾時 | `silenttalk.log` 找 `copilot_suggestion_failed` |
| Copilot 完全沒反應，但 TTS 正常 | Copilot 啟動失敗後會自動降級 | log 找 `copilot_startup_failed` |
| 測試在 import 時就錯 | 用了 Python 3.10 | `python --version` 必須是 3.12 |
