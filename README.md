# AI_threads_chatbot

這是一個 Threads 機器人，用「想統治人類、但是很廢又很可愛的賤萌 AI」人設自動發文和回覆留言。

- 只用 **Meta 官方 Threads API**
- 文字用 **Claude** 生成，配圖可以選 **OpenAI / Gemini**
- 原創梗和 **時事（RSS）** 混著發，生成時會挑出最好的候選，再經過紅線審查
- 審核可以選 **Discord**（✅ / ❌ 按表情核准）或 **全自動**
- 排程跑在 **GitHub Actions**，狀態存在 repo 的 `state` branch
- **本機控制台**：審核草稿、預覽貼文、調整設定和人設

計畫書見 [PLAN.md](PLAN.md)，給 AI 協作者的工作規則見 [AGENT.md](AGENT.md)。

---

## 運作方式

```
GitHub Actions（每 15 分鐘）
  ├─ 到了 schedule.generate_at → 產生當天的草稿（Claude 寫多個候選 → 審查挑最好的一篇 → 配圖）
  │     ├─ review.mode = discord → 推到 Discord，等你按 ✅ / ❌
  │     └─ review.mode = auto    → 直接核准
  ├─ 讀取 Discord 的審核結果；超過 24 小時沒核准就丟棄
  ├─ 已核准而且時間到了 → 發布到 Threads（只會在發文區間內發）
  ├─ 檢查自己最近貼文的新留言 → 分層判斷 → 回覆（同樣走審核模式）
  └─ Token 超過 30 天 → 自動更新並寫回 GitHub Secret
```

| 檔案 | 用途 |
|---|---|
| `config/settings.yaml` | 所有可以調整的選項（不含金鑰） |
| `persona/persona.md`、`persona/examples.md` | 人設 prompt、紅線、範例貼文 |
| `bot/` | 程式本體（見下表） |
| `.github/workflows/bot.yml` | 排程：每 15 分鐘跑一次 `tick` |
| `scripts/state.sh` | 跟 `state` branch 同步狀態 |

| 模組 | 負責 |
|---|---|
| `content.py` | 選貼文類型、挑新聞、生成候選、挑出最好的一篇 |
| `guard.py` | 硬規則（字數、禁用詞、和舊貼文的相似度）加上 Claude 紅線審查 |
| `news.py` | 抓 RSS，過濾災難和政治類新聞 |
| `images.py` | 圖片生成（可以換供應商），並產生公開網址 |
| `discord.py` | 用 REST 推送草稿、讀取 ✅ / ❌ |
| `jobs.py` | 產生、審核同步、發布的流程 |
| `replies.py` | 留言分層處理：跳過 → 轉人工 → 固定回覆 → Claude 回覆 |
| `tokens.py` | Threads token 自動更新 |
| `threads.py` | 官方 Threads API client |
| `ui.py`、`static/` | 本機控制台 |

---

## 安裝（本機）

需要 [uv](https://docs.astral.sh/uv/) 和 Git（Windows 請用 Git Bash）。

```bash
uv sync
```

```bash
cp .env.example .env
```

把金鑰填進 `.env`，然後確認 Threads 連線：

```bash
uv run python -m bot whoami
```

## 常用指令

| 指令 | 說明 |
|---|---|
| `uv run python -m bot ui` | 開啟控制台：http://127.0.0.1:8765 |
| `uv run python -m bot preview -n 3 --news off` | 生成 3 篇預覽，不存檔（調整人設時用） |
| `uv run python -m bot draft` | 馬上產生一篇草稿，並送去審核 |
| `uv run python -m bot tick` | 手動跑一次排程流程 |
| `uv run python -m bot status` | 看待處理的草稿 |
| `uv run python -m bot approve <id>` / `reject <id>` / `publish-now <id>` | 處理草稿 |
| `uv run python -m bot exchange-token <短效token>` | 把短效 token 換成 60 天的長效 token |

`DRY_RUN=true`（預設）的時候，所有流程照常執行，但不會真的發到 Threads。

---

## 上線步驟

### 1. Meta / Threads
1. 準備機器人要用的 Threads 帳號，在個人簡介寫明「本帳號由 AI 經營」。
2. 用 Facebook 帳號登入 [developers.facebook.com](https://developers.facebook.com)，建立一個 App，用途選 **Access the Threads API**。
3. 權限勾選 `threads_basic`、`threads_content_publish`、`threads_read_replies`、`threads_manage_replies`。
4. 到 App roles 把機器人的 Threads 帳號加成 **Threads Tester**，並在 Threads App 裡接受邀請。
5. 用後台的 User Token Generator 產生 token，再執行 `exchange-token` 換成長效 token。執行 `whoami` 就能看到 `THREADS_USER_ID`。

### 2. Discord（審核用）
1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 建立一個 Application 並新增 Bot，複製 Bot Token。
2. 用 OAuth2 URL Generator（scope 選 `bot`）把 bot 邀請進你的伺服器。權限要給：View Channel、Send Messages、Attach Files、Add Reactions、Read Message History。
3. 開一個審核頻道，複製頻道 ID（要先在 Discord 設定裡開啟「開發者模式」才能複製 ID）。

### 3. GitHub 設定
到 repo 的 **Settings → Secrets and variables → Actions** 新增下面這些項目：

| 類型 | 名稱 | 說明 |
|---|---|---|
| Secret | `THREADS_ACCESS_TOKEN` | 長效 token |
| Secret | `THREADS_USER_ID` | |
| Secret | `ANTHROPIC_API_KEY` | |
| Secret | `OPENAI_API_KEY` 或 `GEMINI_API_KEY` | 依你選的圖片供應商 |
| Secret | `DISCORD_BOT_TOKEN` | |
| Secret | `GH_PAT` | fine-grained PAT，只授權這個 repo 的 **Secrets: Read and write**；token 自動更新時會用到 |
| Variable | `THREADS_USERNAME` | 機器人的帳號名稱（不含 @） |
| Variable | `DISCORD_CHANNEL_ID` | |
| Variable | `DISCORD_REVIEWER_IDS` | 選填；限定哪些人按 ✅ 才算數 |
| Variable | `DRY_RUN` | 先設 `true` 試跑，確認沒問題再改成 `false` |
| Variable | `BOT_ENABLED` | 設成 `true` 排程才會開始跑 |

設好之後，可以到 Actions → bot → Run workflow 選 `draft`，馬上產生一篇草稿測試。

### 4. 本機控制台和雲端狀態
控制台讀的是本機的 `state/` 資料夾。按「⬇ 拉取 state」可以抓到雲端最新的草稿；在控制台審核完，按「⬆ 推送 state」，下一次排程就會照你的決定處理。設定和人設改完後，按「提交並推送設定」才會在 GitHub Actions 上生效。

---

## 注意事項

- 這是 **public repo**：金鑰只能放在 `.env` 或 GitHub Secrets。`state` branch 也是公開的，只存草稿、發文紀錄、時間戳。
- 配圖會 commit 到 `state` branch，再用 `raw.githubusercontent.com` 的網址給 Threads 抓取。
- GitHub 的排程尖峰時可能延遲 5～30 分鐘；發文時間本來就有隨機偏移，影響不大。
- 費用估算見 [PLAN.md](PLAN.md) 第 9 節。

## 開發

```bash
uv run ruff format .
```

```bash
uv run ruff check .
```

```bash
uv run pytest
```

部分程式改寫自 [linzoie/threads-bot-template](https://github.com/linzoie/threads-bot-template)（MIT），授權聲明見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
