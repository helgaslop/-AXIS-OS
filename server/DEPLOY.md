# AXIS OS Proxy Server — Deploy Guide

## Railway (найпростіший варіант, безкоштовно)

1. Зайди на https://railway.app → New Project → Deploy from GitHub repo
2. Вибери репозиторій, встанови **Root Directory** = `server`
3. У вкладці **Variables** додай:

```
AXIS_LICENSE_SECRET = AXIS-OS-LICENSE-2024-V1
OPENAI_API_KEY      = sk-...
ANTHROPIC_API_KEY   = sk-ant-...
GOOGLE_API_KEY      = AIza...
XAI_API_KEY         = xai-...
DEEPSEEK_API_KEY    = sk-...
PERPLEXITY_API_KEY  = pplx-...
```

4. Railway автоматично виявить `Procfile` і запустить сервер
5. Скопіюй URL вигляду `https://axis-proxy-production.up.railway.app`

## Після деплою

Встанови URL в клієнті AXIS OS — два способи:

**a) Env var (для розробки):**
```
set AXIS_PROXY_URL=https://your-app.up.railway.app
```

**b) config.json (для production builds):**
```json
{
  "proxy_url": "https://your-app.up.railway.app"
}
```

## Тест після деплою

```bash
curl https://your-app.up.railway.app/health
# → {"status": "ok", "version": "1.0.0"}

curl -X POST https://your-app.up.railway.app/api/v1/activate \
  -H "Content-Type: application/json" \
  -d '{"key": "AXIS-M-01E-XXXXXXXX-XXXX"}'
```

## Render (альтернатива)

1. https://render.com → New Web Service → Connect GitHub
2. Root Directory = `server`
3. Build Command = `pip install -r requirements.txt`
4. Start Command = `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Додай Environment Variables (ті ж що в Railway)
