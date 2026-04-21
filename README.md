# LLM BudgetForge

Hard budget limits for LLM APIs. Self-hosted proxy that sits between your code and OpenAI / Anthropic / Google / Deepseek.

**Live demo:** https://llmbudget.maxiaworld.app

## What it does

- Set a monthly budget per project
- Block or auto-downgrade to a cheaper model when the budget is hit
- Email + Slack/webhook alerts before you hit the ceiling
- Usage dashboard with charts and CSV export
- Team members with admin/viewer roles

## 2-line integration

Works with any OpenAI-compatible SDK — just change `base_url` and `api_key`:

```python
from openai import OpenAI

client = OpenAI(
    api_key="bf-your-project-key",
    base_url="https://your-domain.com/proxy/openai"
)
```

Same for Anthropic, Google, Deepseek — just change the `/proxy/<provider>` path.

## Self-host

**Requirements:** Python 3.12+, Node.js 18+

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your LLM API keys
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8011
```

### Dashboard

```bash
cd dashboard
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL
npm run build
npm start
```

### Environment variables (backend `.env`)

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
DEEPSEEK_API_KEY=sk-...
ADMIN_API_KEY=your-secret-admin-key   # leave empty for dev (no auth)
SMTP_HOST=smtp.example.com            # optional, for email alerts
SMTP_USER=you@example.com
SMTP_PASSWORD=...
```

## Providers supported

| Provider | Proxy path |
|---|---|
| OpenAI | `/proxy/openai` |
| Anthropic | `/proxy/anthropic` |
| Google Gemini | `/proxy/google` |
| Deepseek | `/proxy/deepseek` |
| Ollama (local) | `/proxy/ollama` |

## License

MIT
