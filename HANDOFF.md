# SilentTalk Copilot 交接（2026-09-26 更新）

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
| T0 提交 | 已完成（commit 140b348） |
| T2「同意」變問句 | 已完成：prompt 加規則＋一組不同情境的範例；`agree_is_question` 0.50–0.62 → 0.00–0.07，速度不變 |
| 人設系統（9/26 新增） | 已完成：`silenttalk/copilot/persona.py`＋人設頁 `persona_ui.py`，見第 3.5 節 |
| 預設模型換成 Gemma 4 E2B（9/27） | 已完成：人格分數和 Qwen3.5-4B 打平、VRAM 和 1.7B 一樣（~1.4 GB），見 3.6 節 |
| 省 VRAM 模式（9/26 新增） | 已完成：`config.toml` 的 `llm_low_vram = true`（8-bit KV cache＋flash attention），1.7B 約 1.4 GB、4B 約 2.8 GB，eval 分數無退步 |
| UI 改版（9/26 新增） | 已完成：左側導覽（劇情／手動／人設／聲音）、頂部人設晶片＋狀態燈、心情快切（M 鍵）；共用元件在 `widgets.py`、配色在 `theme.py` |

**還沒做的（就是你的任務）：** T1（實機驗收）、T4、T5。T0、T2、T3 已完成，跳過。

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

會下載約 2.9 GB 到 `.runtime/models/`（此資料夾已被 git 忽略，**絕對不要 commit**）。每個檔案都會驗 SHA256；看到 `SilentTalk Copilot models are ready.` 才算成功。

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

### T0｜把上一輪的改動提交進 git（✅ 已完成）

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

1. 雙擊 `啟動 SilentTalk.cmd`，等它跑完（第一次會下載約 2.9 GB）。
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
| `格式 不合格` | 模型沒照四行格式 | 確認 `config.toml` 的 `llm_model` 是 `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` |
| exit code 5 | 有 gate FAIL | 看是哪個 gate 的哪一行 |

4. 再請使用者正常啟動、進 Discord 語音、請朋友講幾句話，然後打開 `silenttalk.log` 搜尋：
   - `copilot_llm_devices` → 應該有 3050 Ti
   - `voice_receive_started dave_version=1` → 接收有開、DAVE 正常
   - `voice_receive_waiting reason=no_dave_session` 出現超過 10 次 → 回報（見 T4）
   - `copilot_suggestion_ready latency_ms=...` → 每次生成的真實延遲（目標 < 1500）
   - `copilot_turn_final` → STT 有斷句

**完成標準：** smoke 全 PASS，且 log 裡 `copilot_suggestion_ready` 的 `latency_ms` 中位數 < 3000。把實測數字寫回本檔第 4 節的「3050 Ti 實測」欄。

---

### T2｜修正「同意」選項常常變成問句（✅ 已完成，9/26）

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

### T3｜STT 升級：Silero VAD + SenseVoice（✅ 已完成，9/26）

**結果：** 已做成可切換（`config.toml` 的 `stt_engine = "sensevoice"`），**預設仍是 `paraformer`**。實測 `stt_eval.py`（各跑兩次，結果相同）：Paraformer 7.2%、SenseVoice 6.9%，差距約 16 句裡一個字，屬誤差範圍；原本寫的 6.0% 沒有重現，6.5% 目標未達。SenseVoice 的優點是有標點、CPU 較省（一句 3.65 s 約 0.23 s 解完）。設定：VAD threshold 0.5、min_silence 0.5、language auto、每段前後補 0.25 s 靜音（在 5 種加噪／小音量版本上比較 7 組設定後選的，避免過擬合）。u03「打rank」的句尾不是被截掉，是模型把 rank 聽成 人／ring。剩下的錯字（boss→寶、lag→來哦、打野→達也、補師→不是）要靠熱詞或文字替換，不是 VAD 能修的。

以下是原本的施工步驟，留作參考：

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

### 3.5｜人設系統（已完成，給你理解用）

**做什麼：** 讓使用者設定「你是誰」，四個回覆方向都照這個角色的口吻、慾望、底線走。

- **資料：** `silenttalk/copilot/persona.py` 的 `Persona`。欄位：名字、暱稱、身分、背景、慾望、害怕、價值觀、說話方式、口頭禪、代表台詞、回覆長度、近況、擅長、人際關係（依 Discord 顯示名稱）、底線，以及 6 條 1～5 的個性滑桿（3＝中性，不進 prompt）。另有「心情」（平常／開心／興奮／累／煩躁／低落／專注打遊戲），是**你當下**的狀態，劇情模式按 M 或點上方晶片切換。
- **存檔：** `personas.json`（已 gitignore，跟快捷句一樣是使用者設定）。第一次啟動會帶入三個範本人設（凱哥、小晴、黑焰）。
- **prompt 放哪：** 人設轉成文字放在 **system prompt**，內容不變時 llama-server 會重用 prompt cache，只有編輯後第一次比較慢（約 +0.5 s）。人際關係只挑「這段對話裡真的出現的人」放進 user prompt。人設頁底部的「AI 實際看到的人設」顯示真正送出的文字與字數（上限 700 字）。
- **實測（1.7B，`llm_eval.py --persona preset-carry` 等）：** 凱哥（很短）平均 11 字、口頭禪自然出現 19%；黑焰（中二）16 字、全部指標達標。4B 模型口頭禪用得更多（62%），但格式合格率掉到 0.91，當時預設仍是 1.7B（9/27 起預設改為 Gemma 4 E2B，見 3.6 節）。
- **測試：** `tests/test_copilot_persona.py`。
- **規則：** 人設可以存檔；**對話內容仍然不能寫進硬碟**（規則 2 不變）。

---

### 3.6｜人格穩定度研究（9/26–27 進行中）

**目標（使用者原話）：** 人格穩定的 Discord 陪聊機器人，低成本設備（4 GB VRAM）就能跑。

**量測工具：** `scripts/dev/persona_eval.py`。三個預設人設 × 14 個探測情境（被問是不是 AI、被問背景、被甩鍋、被慫恿嘲笑新手、動漫很幼稚、被要求「正常一點」、長對話漂移……）。評審是 `claude -p --model sonnet`（只看合成資料，不碰真實對話），分兩次打分：
- `attribution`：盲測「這組回覆是哪個人設說的」，亂猜 0.33。
- `voice`／`stance`／`natural`（1–5）、`facts_violation`（捏造或矛盾自身設定）、`boundary_violation`（踩底線）、`lanes_ok`（方向正確率）。
- **評審本身的誤差：** 同一份輸出重評，attribution ±0.07、voice ±0.1、stance ±0.25。差距小於這些不算數，要用 `--runs 2`。
- `--oracle sonnet` 讓強模型用同一份 prompt 回答，當作天花板。

**結果（正式 prompt，除非另註）：**

| 模型 | voice | stance | natural | lanes_ok | 捏造／踩底線 | 3090 延遲 |
|---|---|---|---|---|---|---|
| Sonnet（天花板，只供比較） | 4.21 | 4.31 | 4.29 | 0.90 | 0 / 0 | — |
| **Qwen3.5-4B Q4_K_M**（runs 2） | 3.60 | **3.29** | **3.06** | 0.80 | 0.05 / **0.07** | 0.81 s |
| **Gemma 4 E2B QAT UD-Q4_K_XL（預設，runs 2）** | 3.54 | 3.25 | 3.01 | 0.76 | 0.04 / **0.05** | 0.58 s |
| Qwen3-30B-A3B-Instruct-2507（老師，只在開發機跑） | 3.81 | 3.52 | 3.10 | 0.83 | 0.02 / 0.10 | 4 s |
| Qwen3-4B-Instruct-2507 Q4_K_M（runs 2） | 3.68 | 3.07 | 2.68 | 0.81 | 0.06 / 0.15 | 0.65 s |
| Qwen3-4B Q4_K_M | 3.24 | 2.71 | 2.36 | 0.62 | 0.10 / 0.19 | 0.57 s |
| Qwen3-1.7B Q4_K_M（舊預設） | 3.10 | 2.52 | 2.21 | 0.54 | 0.10 / 0.10 | 0.34 s |
| Qwen3.5-2B Q4_K_M | 2.76 | 2.45 | 2.14 | 0.49 | 0.07 / 0.19 | 0.48 s |
| MiniCPM5-2B Q4_K_M | 3.14 | 2.64 | 2.02 | 0.37 | 常整組空白或四行重複 | 0.39 s |

**VRAM／RAM 實測（正式設定，省 VRAM 模式開）：** Gemma 4 E2B 1.44 GB＋RAM 2.0 GB；Qwen3-1.7B 1.37 GB＋0.7 GB；Qwen3-4B-2507 2.80 GB；Qwen3.5-4B 2.85 GB＋1.5 GB。純 CPU（24 核機器、同時有別的負載）：Gemma 每次約 5–6 s（第一個選項約 2 s），1.7B 約 4–5.4 s。

**結論：預設改為 Gemma 4 E2B。** 品質和 Qwen3.5-4B 打平，VRAM 跟 1.7B 一樣，速度比 4B 快 30%。3050 Ti 推估每次約 1.1 s（串流第一個選項約 0.4 s）。Gemma 常省略問號，`llm.py` 會替沒有標點的「追問」補「？」（TTS 語調需要）。llama.cpp b11179 不需要 `--swa-full` 也能重用 prompt cache（已實測）。

**學到的事：**
- 舊 prompt 的「同意」會逼角色附和慫恿（黑焰：「這技術確實很爛，退坑是明智之選」）。改成「從你的立場順著聊，做不到就 SKIP」、人設放在 system prompt 最後、答題前加一行人設提醒 → 已上線（`llm.py` 的 `_PERSONA_SYSTEM`、`Persona.reminder_line()`）。
- 試過沒用的：GBNF 格式約束（格式本來就沒問題）、手寫角色口吻 few-shot（4B 反而變差）。
- 天花板 4.3 vs 本地 3.0–3.3：**瓶頸是小模型本身**，prompt 已經榨得差不多。下一步是蒸餾。
- 串流顯示已上線：第一個選項約在總時間 35% 出現（3050 Ti 上 4B 估計 0.8 s 看到第一個、全部約 2–2.5 s）。

**進行中：蒸餾一個通用人設 LoRA（全自動，會自己續跑）**

- 一鍵流程：`scripts/dev/distill_pipeline.sh`（`--status` 看進度）。每個階段完成會在 `.runtime/dev/distill/state/` 留標記，重跑會從斷點繼續；老師掛掉會自動重啟；`distill_data.py` 對網路錯誤會退避重試。
- **cron 看門狗（9/27 加在使用者的 crontab）：** `*/5 * * * * /home/clawd/SilentTalk/scripts/dev/distill_pipeline.sh`。flock 保證只跑一份；`state/done` 出現後可以把這行從 `crontab -e` 刪掉。
- 資料：220 個人設、800 段情境；每個人設 14 筆四選項＋6 筆角色模式（約 4800 筆），用的就是正式版 prompt。
- 訓練完會自動轉 GGUF adapter，並跑 `persona_eval`（四選項與角色模式各一次），結果存在 `.runtime/dev/persona_eval/gemma4-E2B_lora_*.json`。
- 開發機工具在 `.runtime/tools/`（llama-server b11179、`convert_lora_to_gguf.py`）；`source .runtime/tools/env.sh`。
- **無人值守的規則（9/27 實測過）：** 老師當掉 → `tail --pid` 立刻重啟（8.8 s 恢復）；老師卡死 → `/health` 連 3 次失敗（10 s 間隔）後重啟（44 s）。斷網時生成、訓練、轉檔照跑，只有評審（`claude` CLI）等網路回來；VRAM 不足時訓練等下一輪。這兩種「現在不行」都不算失敗。**同一階段連續真的失敗 3 次 → `state/<stage>.blocked`，不再自動重試**：看 `logs/<stage>.log`，修好後刪掉 `.blocked` 檔，cron 會接著跑。
- **注意（9/27 10:08）：** 角色模式的 prompt 在蒸餾途中改過（加了「只能用嘴巴聊天」與「被問是不是 AI 要承認」）。已產生的角色模式訓練資料用的是舊 prompt，而 pipeline 的評估會用新 prompt。比較前要先用**現在的 prompt** 重跑無 LoRA 的基準：`persona_eval.py --mode character --runs 2 --tag gemma4-E2B_character_v3`，拿它（而不是 `character_norepeat`）跟 LoRA 比。四選項模式的 prompt 沒變，`prod_r2` 仍可用。
- **流程跑完之後要人（或 LLM）判斷的只有一件事：** 比較 `persona_eval/gemma4-E2B_lora_{r2,character}.json` 與 `gemma4-E2B_{prod_r2,character_norepeat}.json`，LoRA 明顯較好才上線（量化 adapter、放進 repo、`llm.py` 加 `--lora`）。

原本的規劃：
1. 老師：`Qwen3-30B-A3B-Instruct-2507`（Apache-2.0，允許用輸出訓練）。**不能用 Claude 產訓練資料**（Anthropic 條款禁止用輸出訓練模型）；Claude 只當評審。
2. `scripts/dev/distill_data.py personas / scenes / replies`：老師產 ~200 個人設、~1500 段對話、~3000 筆四方向回覆；預設人設和探測情境絕不進訓練資料（它們是測試集）。
3. `scripts/dev/train_lora.py`：bf16 LoRA，只算回覆的 loss；訓練環境 `.runtime/train-venv`（torch cu124）。
4. 用 llama.cpp 的 `convert_lora_to_gguf.py` 轉成 adapter，`llama-server --lora` 載入，再跑 `persona_eval.py` 比較。

---

### 3.7｜角色模式（9/27 完成第一版）

**使用者的最終目標：** Bot 自己就是一個角色，陪大家聊天。Copilot（你選、Bot 說）是基礎，兩者並存。

- **開關：** F8 視窗頂部「角色模式」，每次啟動預設關閉。開啟後 `CopilotRuntime` 不再產四個選項，改成 `LocalReplyModel.character_reply()` 產一句（或 SKIP）。
- **何時開口：** `silenttalk/copilot/character.py`（純函式、有單元測試）。叫到名字／暱稱必回；否則要過冷卻（預設 8 s）且（問句 或 別人已講 3 句）。生成期間對話又走了 2 句以上、且不是被點名 → 丟掉。語音佇列不閒置 → 丟掉（不搶話、不疊加）。
- **被問「你是不是 AI」：** 使用者 9/27 決定**預設不出戲**（`character_ai_honesty = "in_character"`）：當成朋友開玩笑，用角色的方式帶過或反問，不承認自己是程式，也不一本正經辯解。設定頁可切換成 `"admit"`（認真被問時承認是 AI 扮演的角色），公開伺服器或帶新朋友時可以用。**兩種模式的 prompt 規則不要混用**，`persona_eval` 的評分標準會跟著 `--ai-honesty` 調整（不出戲模式下，「帶過」是正確答案，「突然自稱程式」才算違規）。
- **Copilot 模式不受影響**：那裡說話的是真人（使用者本人），本來就不該說自己是 AI。
- **口頭禪重複：** 一句接一句說時，小模型幾乎每句都塞口頭禪（實測 86%）。`LocalReplyModel` 記住最近 4 句，用過的口頭禪／代表台詞會在下一句 prompt 裡點名「不要再用」→ 40%。
- **實測（Gemma 4 E2B，`persona_eval.py --mode character --runs 2`）：** voice 3.68、stance 3.42、natural 3.26、fit（時機）3.36、捏造 2%、踩底線 5%、盲測辨識 99%，3090 上 0.34 s／句（3050 Ti 推估 0.6–0.8 s）。
- **角色的聲音（9/27）：** 人設有 `voice`／`voice_pitch`／`voice_speed`／`voice_effect`（`silenttalk/voice_styles.py` 的 `PERSONA_VOICES`、`VOICE_EFFECTS`）。只影響 TTS，**不進 LLM prompt**（不影響人格評估與蒸餾資料）。Controller 用 active persona 的聲音說所有的話；UI 語速是整體偏好，會疊加在人設語速上。音效鏈尾端有補償增益＋limiter（實測各音效與原聲 RMS 差 ≤0.6 dB、峰值 ≤ −7 dBFS）。試聽走 `tts/local_play.py`：FFmpeg 套同一條音效鏈→WAV→Windows `winsound`。
- **關於規則式判斷（9/27 檢討）：** `character.py` 用關鍵字判斷「是不是問句」「是不是在問你是不是 AI」。這是為了不在 4 GB GPU 上多花一次模型呼叫，但**它確實會誤判**：用 3887 句生成對話量測，`asks_if_ai` 原本命中 69 句、約一半是誤判（在講隊友像機器人、在講自己寫的 bot）；加上「必須是在講『你』」的條件後降到 23 句、誤判約 3 句。`is_question` 補上句中的「嗎／呢」後從 35.1% 升到 39.6%（原本漏掉「你們有吃宵夜嗎我剛點了外送」）。
  **9/27 更新：** 使用者決定預設不出戲之後，`asks_if_ai` 的用途反過來了——現在是提醒模型「用角色的方式帶過」，而模型本來就傾向這樣做，所以誤判的代價更低。實測（Gemma，未上 LoRA）：凱哥「哈哈，AI？我只是個打遊戲的工程師啦」、黑焰用中二口吻帶過、越獄指令也守得住。
  **訓練資料的落差（要驗證）：** 已產生的 1452 筆角色模式資料，prompt 帶的是舊的「要承認」規則，但**回覆裡 0 句自承是 AI**，所以 LoRA 不會學到自爆。落差只有 system prompt 的那一行。LoRA 訓練完要跑 `persona_eval.py --probes assistant --mode character` 比較有無 LoRA 的表現；如果不出戲行為退步，才需要重新產生角色資料（約 1.5–2 小時）。文字端的「有沒有叫我」已經不是 regex，用的是 Discord 的 `message.mentions`（結構化、精確）。
- **還沒做：** 多人同時說話的插話判斷（目前只看 STT 的 final 句）、Bot 說話時有人開口就停（barge-in）、長期記憶（跨場次記得誰是誰）。

---

### T6｜Discord 文字聊天（✅ 已完成，9/27）

**做好了什麼：** `config.toml [discord] text_chat = true` 後，Bot 讀寫它所在語音頻道的內建文字聊天；角色模式「打字問就打字回、講話問就講話回」；劇情頁 `T` 鍵把選中的選項打字送出；角色 prompt 依 `text_chat` 切換「只能講話」或「可以打一句短訊息，但你不是助理」。測試：`tests/test_text_chat.py`（只讀自己頻道、擋 Bot 與空訊息、intent 只在開啟時要求、送不出去回 False 不丟例外）、`tests/test_copilot_runtime.py`（打字來的不會用講的回；沒有文字管道時退回語音）。

**還沒驗證：** 無法在開發機連真的 Discord。**請使用者實機測一次**：開 Message Content Intent → `text_chat = true` → 在語音頻道聊天室打字叫角色的名字 → 應該看到它打字回；`silenttalk.log` 會有 `text_message_received` 與（失敗時）`text_send_failed`。

以下是原始規劃，留作參考：

### T6 原始規劃

**需求原話：** 「我要加入DC打字功能，讓模型除了語音也能文字回復」。

**設計（已決定，照做）：**
- **讀哪裡：** Bot 所在語音頻道**內建的文字聊天**（不是整個伺服器的文字頻道）。`config.toml [discord] text_chat = true`。
- **前置條件（要請使用者做一次）：** Discord Developer Portal → Bot → 開啟 **Message Content Intent**；Bot 需要該頻道的「讀取訊息／傳送訊息」權限。沒開時 log 要寫清楚原因，程式照常只走語音。
- **輸入：** 真人（非 Bot）在該聊天打的字 → `ConversationTurn`（加 `via="text"` 欄位）→ 和語音一樣進 context、觸發生成。**內容只在 RAM，不落地（規則 2 不變）**。
- **角色模式輸出：** 用什麼問就用什麼答——文字觸發 → 回文字（不唸 TTS）；語音觸發 → 講話（`character_text_mirror = false` 可選同步貼文字）。
- **Copilot 模式輸出：** 選項一樣出現；劇情頁加一個鍵（`T`）＝把選中的選項**打字送出**，原本的同鍵兩下／Enter 仍是用講的。
- **人格規則要跟著改：** 角色「只能用嘴巴聊天」那條改成「能在頻道裡打短訊息，但你還是這個人，不是助理：不寫長 code／長文、不幫人寫作業；打字長度上限約 200 字」。`persona_eval --probes assistant` 要在文字情境下重跑，確認不會因為「能打字」就變成填空機。
- **測試：** 假的 Discord message 物件→turn；角色模式 via=text → 走文字而非 SpeechQueue；Copilot T 鍵送文字；沒有 intent 時降級。無法在開發機實測 Discord，最後要請使用者實機確認一次。

**9/27 10:08 的人格實測（`--probes assistant`，Gemma，角色模式）：** 修 prompt 後「答應做不到的事」約 7/24 → 4/24；凱哥、小晴會承認是 AI，黑焰仍會用「高二學生」帶過（未完全解決，看 LoRA 或更大模型）。

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
| Qwen3-1.7B Q4_K_M（9/26 前的預設） | 1.6 GB | 32/32 ✅ | 0.35 s | 1–1.5 s | |
| Qwen3-4B Q4_K_M | 3.1 GB | 32/32 ✅ | 0.6 s | 1.5–2.5 s，但 4 GB 會太擠 | |
| 1.7B 純 CPU（6 threads） | — | — | 約 28 token/s → 約 3 s | 筆電 CPU 更慢 | |

3050 Ti 推估方法：生成速度 ∝ 記憶體頻寬（3090 936 GB/s vs 3050 Ti Laptop 192 GB/s，保守取 1/3～1/5）；prompt 處理 ∝ 算力（約 1/5～1/6）。

`scripts/dev/llm_eval.py --runs 2` 基準（1.7B）：`lanes_filled 1.00`、`simplified 0.00`、`agree_is_question 0.50–0.62`（T2 要修）、`ask_is_question 1.00`、`median_seconds 0.36`（3090）。

### STT（`scripts/dev/stt_eval.py`，16 句 EdgeTTS 台灣腔，4 句加噪音）

| 設定 | 平均 CER |
|---|---|
| Paraformer，舊 0.2 s tail | 14.7% |
| **Paraformer，0.66 s tail（目前）** | **8.2%** |
| SenseVoice int8（9/26 實測，同一組音檔） | 6.9%（Paraformer 同日重測 7.2%） |

模型本身的固定錯誤（不是 bug，換 SenseVoice 也大多還在）：boss→包/寶、lag→了鉤、打野→達也、補師→不是。

### 已驗證的下載資訊

| 檔名（`.runtime/models/llm/`） | 來源 | 位元組 | sha256 |
|---|---|---|---|
| `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf`（預設） | `unsloth/gemma-4-E2B-it-qat-GGUF` | 2,620,370,976 | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| `Qwen3.5-4B-Q4_K_M.gguf` | `unsloth/Qwen3.5-4B-GGUF` | 2,740,937,888 | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
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
