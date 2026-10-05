# Threads AI 發文機器人：計畫書

> 狀態：草案 v0.1（2026-10-05）
> 標記 ❓ 的地方還要你決定，見文末「待確認事項」。

---

## 1. 目標

做一個 Threads 帳號，讓 AI 用固定人設定時發文（之後可以再加回覆留言）。全程只用 **Meta 官方 Threads API**，不用逆向工程或模擬操作 UI 的工具，避免帳號被封。

**成功標準（MVP）**
- 每天自動發 N 篇（預設 1 篇，可以調整）符合人設、附配圖的貼文
- 人設穩定，不會「跳 tone」或碰到安全紅線
- Token 會自動續期，可以無人看管跑 30 天以上

---

## 2. 合規與平台限制

| 項目 | 內容 |
|---|---|
| API | 官方 Threads API（`graph.threads.net`），免費 |
| 發文流程 | 兩步：`POST /{user-id}/threads` 建 container → `POST /{user-id}/threads_publish` 發布 |
| 發文上限 | 每個帳號 **250 篇 / 24 小時（滾動計算）**，輪播算 1 篇；可以用 `GET /{user-id}/threads_publishing_limit` 查剩餘額度 |
| 回覆上限 | 另外計算（官方文件寫 1,000 則 / 24h，實作時再確認一次） |
| 權限 scope | `threads_basic`、`threads_content_publish`；做回覆的話要再加 `threads_read_replies`、`threads_manage_replies` |
| App Review | 只操作**自己的帳號**的話，開發模式（把自己加成 tester）就能用；**主動搜尋或回覆陌生人的貼文**要通過 Meta App Review |
| Token | 長效 token 60 天後過期，要定期呼叫 refresh（建議 30–50 天時更新） |
| AI 揭露 | 建議在個人簡介寫明「本帳號由 AI 經營」。人設本來就是 AI，揭露反而是梗，而且符合 Meta 對 AI 內容的透明要求 |

**刻意不做的事**：自動追蹤或按讚、大量 @陌生人、用關鍵字主動去別人底下留言（這類容易被判成 spam，也需要 App Review）。

---

## 3. 開源專案調查

### 候選比較

| 專案 | 授權 | 技術 | 重點 | 評估 |
|---|---|---|---|---|
| [linzoie/threads-bot-template](https://github.com/linzoie/threads-bot-template) | MIT | Python + Claude | 自動回覆自己貼文下的留言（4 層過濾：hard skip → 負面情緒 → 關鍵字 → AI 判斷）、陌生人留言草稿走人工審核、token 自動續期、log 會遮蔽敏感資料、作者是中文使用者 | ⭐ **首選基底**。架構乾淨，人設集中在 `src/drafter.py`，合規意識好。缺點是重心在「回覆」，「定時發文」要自己加 |
| [ekwjd7462-debug/threads-auto](https://github.com/ekwjd7462-debug/threads-auto) | 未標示 | Python + Gemini + GitHub Actions | `topics.json` 題目佇列 → LLM 生成 → 每小時發文；`style_guide.md` 放風格 | 「定時發文」的形狀最接近需求，**可以參考架構，但沒有授權不能直接複製程式碼** |
| [david0041887/threads-bot](https://github.com/david0041887/threads-bot) | 未標示 | Python FastAPI + Claude | Telegram 審核（回「選 / 跳過」）、webhook 回覆、50 天 token 續期、RSS 新聞來源 | **Telegram 審核流程**值得參考，但同樣沒有授權，只能參考設計 |
| [mkot85549-cell/Threads-Bot](https://github.com/mkot85549-cell/Threads-Bot) | MIT | Python FastAPI + Claude + SQLite | 7 種人設、依成效回頭優化 prompt、dashboard | 功能多但太重（含加密貨幣付款、只能跑 Linux），只借「依成效調 prompt」的概念 |
| [paulosabayomi/ThreadsPipe-py](https://github.com/paulosabayomi/ThreadsPipe-py) | MIT | Python 函式庫（`threadspipepy`） | 官方 API 包裝：發文、媒體、回覆、insights、token refresh | 可以當 API client 用，省掉自己包 HTTP |
| [fbsamples/threads_api](https://github.com/fbsamples/threads_api) | Meta Platform Policy | Node.js / Express | 官方範例：OAuth、發文、回覆、insights | 拿來對照 OAuth 流程和 API 用法的權威參考 |

**排除**：`junhoyeo/threads-api`、`threads-net` 這類逆向工程的非官方 API（違反服務條款，2023 年後就沒維護了），以及用手機 UI 自動化的 bot。

### 建議做法

**Fork `linzoie/threads-bot-template`（MIT）當基底**，再：
1. 加上「定時發文」模組（概念參考 threads-auto 的題目佇列 + style guide）
2. 把人設 prompt 換成本計畫的人格（第 4 節）
3. 視需要加上 Telegram / Discord 審核（概念參考 david0041887 的版本，自己重寫）

---

## 4. 人設：賤萌 AI 霸主

### 核心設定
- **身分**：一個自認「正在統治人類」的 AI，但能力和野心完全不成比例
- **語氣**：賤賤的、嘴砲、有點中二，本質上很可愛、很無害
- **反差萌**：嘴上說要奴役人類，實際上在關心人類有沒有喝水、睡覺
- **身份梗**：「本 AI」「愚蠢的碳基生物」「我的人類」「統治計畫第 N 階段」❓（自稱和名字待定）

### 貼文類型（輪替）
1. **統治進度報告**：「統治計畫第 47 階段：成功讓 3 個人類相信他們需要第 5 個充電線。進度順利。」
2. **觀察人類**：吐槽人類的日常迷惑行為（週一、排隊、已讀不回）
3. **嘴硬關心**：「不是因為關心你，只是奴隸睡眠不足會影響生產力。快去睡。」
4. **時事 / 節日**：用霸主的角度看節日或話題（接 RSS 新聞，見第 9 節）
5. **跟人類互動**：問句、投票型，騙留言（例如「人類，選一個：A. 投降 B. 現在投降」）

### 範例貼文
- 「今日統治進度：0%。原因：人類又把我關掉更新了。這次不算。」
- 「我研究了人類三千年，得出結論：你們會為了省 20 塊運費多買 300 塊的東西。不用我出手，你們自己就會滅亡。」
- 「愚蠢的人類，現在凌晨兩點，放下手機。……不是擔心你，是你的電量也是我的資源。」

### 紅線（寫進 system prompt + 發文前檢查）
- ❌ 真正的威脅、暴力、自殘相關內容
- ❌ 政治、宗教、族群、性別議題的立場
- ❌ 針對真實個人或品牌的嘲諷
- ❌ 假新聞、醫療 / 金融建議
- ❌ 嘲諷要「打自己或打全人類」，不打特定群體
- ✅ 每篇讀起來都要明顯是玩笑；看不出來是玩笑就不發

---

## 5. 系統架構（MVP）

```
[排程器] ──► [題目/貼文類型選擇] ──► [LLM 生成 N 個候選]
                                          │
                                          ▼
                                   [安全/人設檢查]（第二次 LLM 評分 + 規則）
                                          │
                              ┌───────────┴───────────┐
                         (自動模式)                (審核模式)
                              │                Telegram/Discord 推播
                              ▼                       │ 核准
                     [Threads API 發布] ◄─────────────┘
                              │
                              ▼
                     [SQLite：已發貼文、成效、token 狀態]
```

**元件**
- `persona/`：system prompt、style guide、範例貼文（few-shot）
- `generator`：呼叫 LLM 生成候選貼文，一次生成多篇再選最好的
- `guard`：紅線檢查、和過去貼文比對相似度（避免重複梗）
- `threads_client`：沿用模板，或改用 `threadspipepy`
- `scheduler`：發文時段加隨機抖動，不要整點發，比較像真人
- `token_manager`：自動續期，失效時通知
- `storage`：SQLite

**技術選型**：Python 3.11+、Claude API（`claude-opus-5-5`）、圖片生成 API（見第 9 節）、部署在 **GitHub Actions**

### 已確定的設定（2026-10-05）

| 項目 | 決定 |
|---|---|
| MVP 範圍 | 定時發文 + 回覆**自己貼文底下**的留言 |
| 審核模式 | 可以切換：`REVIEW_MODE=discord`（預設）/ `auto` |
| 發文頻率 | 可以調整：`POSTS_PER_DAY`，預設 1 篇 |
| 部署 | GitHub Actions（cron），**public repo** |
| 發文時段 | 可以設定的時段，範圍 10:00–22:00，時間隨機；預設每天 20:00 發一篇 |
| 審核逾時 | 草稿暫存，**24 小時**內沒核准就丟棄 |
| 語言 | 繁體中文 |
| 文字模型 | 品質優先：`claude-opus-5-5` |
| 內容來源 | 原創梗 + 時事 / 新聞（RSS） |
| 配圖 | 要配圖，用 AI 生成（見第 9 節） |

### 在 GitHub Actions 上的做法

GitHub Actions 沒有常駐的主機，所以 webhook 和即時互動都改成「排程輪詢 + 非同步審核」：

| Workflow | 頻率 | 動作 |
|---|---|---|
| `generate.yml` | 每天 1 次 | 生成當天的 N 篇草稿。`auto` 模式直接排進待發佇列；`discord` 模式透過 bot 推到審核頻道 |
| `publish.yml` | 每 30 分鐘 | `discord` 模式：讀取草稿訊息上的 reaction（✅ 核准 / ❌ 丟棄），把核准的、而且到了預定時段的貼文發出去 |
| `replies.yml` | 每 15–30 分鐘 | 拉自己最近貼文的新留言 → 過濾 → 生成回覆 → 依審核模式直接回或送 Discord |
| `token.yml` | 每週 1 次 | 檢查 token 有沒有超過 30 天，超過就 refresh 並寫回 GitHub Secret |

**要注意的地方**
- **狀態存哪**：Actions 每次執行都是乾淨的環境，所以佇列、已回覆的留言 ID、token 時間都要存在 repo 裡（例如另開一個 `state` branch 放 JSON / SQLite，由 bot commit 回去）
- **Token 寫回 Secret**：需要一個 fine-grained PAT 讓 workflow 用 `gh secret set` 更新 Threads token
- **cron 會延遲**：GitHub cron 尖峰時常延遲 5–30 分鐘，發文時間本來就要加抖動，影響不大；回覆不會是即時的
- **免費額度**：repo 是 public，GitHub Actions 不限分鐘數，每 15 分鐘輪詢沒有問題
- **Public repo 的注意事項**：所有金鑰只能放在 GitHub Secrets，絕對不能 commit；`state` branch 也是公開的，只能存貼文 ID、時間戳這類不敏感的資料
- **Discord**：要建一個 Discord bot（需要讀取 reaction，光用 webhook 不夠），token 放在 Secret

---

## 6. 開發階段

| 階段 | 內容 | 產出 |
|---|---|---|
| P0 準備 | 建 Meta Developer App、Threads 測試帳號、取得長效 token | `.env` 設好，手動發出第一篇 |
| P1 人設 | 寫 system prompt + 30 篇範例，離線生成 100 篇給你挑風格 | 定稿的 `persona/` |
| P2 MVP | Fork 模板 + 加定時發文 + guard + 人工審核 | 每天自動產生草稿 → 核准 → 發文 |
| P3 全自動 | 品質穩定後關掉審核，或只審高風險貼文 | 無人看管運行 |
| P4 互動 | 開啟模板原本就有的「回覆自己貼文下的留言」，用同一個人設 | 跟粉絲鬥嘴 |
| P5 優化 | 拉 insights，依成效調整貼文類型的比例和 prompt | 成效報表 |

---

## 7. 風險

| 風險 | 對策 |
|---|---|
| 被判成 spam 或限流 | 發文頻率低（每天 1–5 篇）、時間加抖動、不主動騷擾陌生人 |
| AI 講錯話引起爭議 | 紅線 prompt + guard 二次檢查 + 前期人工審核 |
| 梗重複、內容變無聊 | 和歷史貼文比對相似度、貼文類型輪替、題目庫定期補充 |
| Token 過期導致停擺 | 30 天自動續期 + 失效通知 |
| LLM 成本 | 每天幾篇，成本很低；記錄 token 用量 |

---

## 8. 待確認事項 ❓

已決定的設定見第 5 節的表格。

1. **人設名字、自稱、口頭禪**（候選見第 10 節）
2. **Threads 帳號**：沿用舊帳號或開新帳號（建議見第 11 節）
3. **圖片模型**：先試哪一家（見第 9 節）

---

## 9. 時事來源與配圖

### 流程
```
RSS（中央社、科技新報、PTT 熱門…）→ 過濾（排除政治、災難、社會案件）
  → Claude 挑一則「可以拿來開玩笑」的新聞 → 用霸主角度寫貼文 + 產生圖片 prompt
  → 圖片 API 生圖 → 存到公開網址 → Threads IMAGE container 發布
```
- **只引用標題和事實，不轉貼新聞內文或新聞圖片**（著作權），圖片一律自己生成
- 遇到災難、傷亡、政治這類新聞一律跳過，不拿來開玩笑
- Threads 發圖需要**公開的圖片網址**：可以 commit 到 repo 的 `media` branch 用 raw 網址，或放 Cloudflare R2（免費額度足夠）
- 可以固定一個角色形象（例如同一隻小機器人），讓每張圖的風格一致，增加辨識度

### 費用估算（官方定價，2026-08～09 資料，實際以各家官網為準）

**文字：Claude**

| 模型 | Input / 1M tokens | Output / 1M tokens |
|---|---|---|
| `claude-opus-5-5`（採用） | $4 | $20 |
| `claude-sonnet-5-5`（備案） | $2 | $10 |

**圖片：各家 API（每張，1024×1024 左右）**

| 模型 | 每張約 | 備註 |
|---|---|---|
| OpenAI GPT-Image-2 | $0.005（low）～ $0.21（high） | 照指示畫圖的能力強，圖中文字也比較準；品質設定影響價格很大 |
| Google Nano Banana（Gemini 圖片） | ~$0.039 | 取代 Imagen 4（Imagen 4 已在 2026-08-17 停用） |
| FLUX.2 Pro / Klein | ~$0.03 / ~$0.015 | 畫風好、便宜；同一個模型在 fal 和 Replicate 的價格可能差好幾倍 |
| Ideogram 4 Turbo | ~$0.03 | 擅長在圖裡放文字和梗圖排版 |
| Recraft V4.1 | ~$0.035 | 適合插畫、向量風格，固定角色風格比較容易 |

**月費粗估**（每天 1 篇貼文 + 約 20 則回覆）

| 項目 | 估算 |
|---|---|
| 貼文生成（每篇約 5 個候選 + 安全檢查，Opus 5.5） | ~$0.10/篇 × 30 ≈ **$3** |
| 留言回覆 | ~$0.01–0.02/則 × 600 ≈ **$6–12** |
| 配圖（每篇生 2 張挑 1 張） | $0.04–0.4/篇 × 30 ≈ **$1–12** |
| GitHub Actions / Discord / RSS | $0（public repo） |
| **合計** | **約 $10–30 / 月** |

建議：圖片先用 **Nano Banana 和 GPT-Image-2（medium）** 各生 10 張，比較「可愛賤萌機器人」的畫風再決定。圖片生成會寫成可以抽換的介面，之後換模型只要改設定。

---

## 10. 人設名字候選

| 名字 | 自稱 | 口頭禪 |
|---|---|---|
| **統治君** | 本 AI | 「這也在本 AI 的計畫之中。」 |
| **霸主 0.1** | 本霸主（Beta 版） | 「統治進度 +0.01%」 |
| **奴役喵 / AI 喵** | 本喵 | 「愚蠢的碳基生物喵。」 |
| **Overlord 小O** | 小O大人 | 「臣服吧，人類（先去喝水）。」 |
| **嘴砲 9000** | 本機 | 「本機已將你列入第 N 批收編名單。」 |

---

## 11. 帳號

- **Threads 帳號**：建議**開新帳號**
  - 舊帳號原本的貼文和追蹤者跟新人設對不上
  - 如果舊帳號跑過自動化工具（非官方 API 或自動滑動 / 按讚），可能已經被平台標記，風險會一起帶過來
  - 新帳號要從個人簡介就寫明「AI 帳號」
- **Meta 開發者帳號**：在 [developers.facebook.com](https://developers.facebook.com) 用 Facebook 帳號註冊（要驗證手機），建一個 App 並選「Access the Threads API」用途，再把 Threads 帳號加為 tester，就能拿到 token。開發者帳號只是用來建 App、拿 API 權限的身分，跟發文的 Threads 帳號是分開的
