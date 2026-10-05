# AGENT.md

## 規定何時停

- 不需要我介入的步驟，請直接繼續做。
- 進度報告和下一步動作，寫在同一則訊息裡。
- 只有在「沒有我的指示就無法繼續」，或要做任何破壞性操作之前（刪除資料、force-push、修改這個 repository 以外的任何東西），才停下來問我。

### 官方範例原文（claude.dev/blog）

> **KEEP GOING** — When a step doesn't need my input, keep going. Put status notes in the same message as your next action.
>
> **STOP AND ASK** — Stop and ask only when you can't continue without me, or before anything destructive: deleting data, force-pushing, or changing anything outside this repository.

## 工作方式

- **還沒決定的事不要卡住**：做成可以切換的選項（寫在 `config/settings.yaml` 或環境變數），先套用合理的預設值，再把這個待決事項寫進 `PLAN.md` 的「待確認事項」。
- **一個階段一個 commit**：完成一個階段（能跑、測試通過）就 commit 並 push。commit message 用英文、祈使句。
- **commit 前先跑**：`uv run ruff format .`、`uv run ruff check .`、`uv run pytest`，全部都要通過。
- **文件用繁體中文**，程式碼註解和識別字用英文。

## 專案規則

- **這是 public repo**：任何金鑰、token 都不能 commit，只能放在 `.env`（已列入 gitignore）或 GitHub Secrets。`state` branch 也是公開的，只能存不敏感的資料。
- **只用官方 API**：Threads 一律走 `graph.threads.net` 官方 API，不用逆向工程或模擬操作 UI 的套件。
- **人設與紅線**：所有對外發出的文字都要先經過 `bot/guard.py` 的檢查；紅線定義在 `persona/` 和 `PLAN.md` 第 4 節，修改人設時要一併更新。
- **預設安全**：`DRY_RUN` 預設為 true；沒有設定 `BOT_ENABLED=true` 的話，GitHub Actions 不會執行任何動作。
- **LLM**：文字一律用 Claude（預設 `claude-opus-5-5`，可以在設定中更改）；圖片生成的供應商要能抽換。
