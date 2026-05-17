"""
core/agent_providers.py
Registry of all supported AI providers for AXIS IDE.
Each provider has: id, name, icon, base_url, models, sdk_type.
sdk_type: "openai_compat" | "anthropic" | "cohere" | "azure"
Each model entry: {"id": str, "label": str, "desc": str, "tags": [str]}
"""

PROVIDERS: dict[str, dict] = {

    "anthropic": {
        "name": "Anthropic", "icon": "🟣",
        "sdk_type": "anthropic",
        "base_url": None,
        "key_hint": "sk-ant-api03-...",
        "models": [
            {"id": "claude-opus-4-7",              "label": "Claude Opus 4.7",          "desc": "Найновіший флагман · складний код та агенти",    "tags": ["новий", "топ"]},
            {"id": "claude-sonnet-4-6",            "label": "Claude Sonnet 4.6",        "desc": "Рекомендована 2026 · баланс швидкості й якості", "tags": ["новий", "рекомендована"]},
            {"id": "claude-haiku-4-5",             "label": "Claude Haiku 4.5",         "desc": "Найшвидша і найдешевша 4-серія",                "tags": ["новий", "швидка"]},
            {"id": "claude-opus-4-5",              "label": "Claude Opus 4.5",          "desc": "Попередній флагман · 200K контекст",            "tags": ["топ", "200K"]},
            {"id": "claude-sonnet-4-5",            "label": "Claude Sonnet 4.5",        "desc": "Стабільна · ідеальна для коду",                 "tags": ["200K"]},
            {"id": "claude-3-7-sonnet-20250219",   "label": "Claude 3.7 Sonnet",        "desc": "Extended thinking mode · 200K",                 "tags": ["thinking", "200K"]},
            {"id": "claude-3-5-sonnet-20241022",   "label": "Claude 3.5 Sonnet",        "desc": "Перевірена класика",                            "tags": ["200K"]},
            {"id": "claude-haiku-3-5",             "label": "Claude Haiku 3.5",         "desc": "Легка стара версія",                            "tags": ["48K"]},
        ],
    },

    "openai": {
        "name": "OpenAI", "icon": "🟢",
        "sdk_type": "openai_compat",
        "base_url": None,
        "key_hint": "sk-proj-...",
        "models": [
            {"id": "gpt-5.5",         "label": "GPT-5.5",        "desc": "Найновіший флагман OpenAI 2026",          "tags": ["новий", "топ"]},
            {"id": "gpt-5.4-pro",     "label": "GPT-5.4 Pro",    "desc": "Професійна версія 5-серії",               "tags": ["новий", "топ"]},
            {"id": "gpt-5.4",         "label": "GPT-5.4",        "desc": "Стандартний флагман 5-серії",             "tags": ["новий"]},
            {"id": "gpt-5.4-mini",    "label": "GPT-5.4 Mini",   "desc": "Швидкий і дешевий GPT-5",                "tags": ["новий", "швидка"]},
            {"id": "gpt-5.4-nano",    "label": "GPT-5.4 Nano",   "desc": "Найлегший GPT-5 · низька затримка",      "tags": ["новий", "nano"]},
            {"id": "gpt-5.2-codex",   "label": "GPT-5.2 Codex",  "desc": "Спеціалізований кодер від OpenAI",       "tags": ["новий", "код"]},
            {"id": "gpt-4.1",         "label": "GPT-4.1",        "desc": "Флагман 2025 · 1M контекст",             "tags": ["1M"]},
            {"id": "gpt-4.1-mini",    "label": "GPT-4.1 Mini",   "desc": "Швидкий GPT-4.1 · 1M контекст",         "tags": ["1M"]},
            {"id": "o3",              "label": "o3",             "desc": "Найрозумніший reasoning",                "tags": ["reasoning", "топ"]},
            {"id": "o4-mini",         "label": "o4-mini",        "desc": "Швидкий reasoning · хороший для коду",   "tags": ["reasoning"]},
            {"id": "gpt-4o",          "label": "GPT-4o",         "desc": "Мультимодальний · vision · 128K",        "tags": ["vision", "128K"]},
            {"id": "gpt-4o-mini",     "label": "GPT-4o Mini",    "desc": "Легкий GPT-4o",                          "tags": ["128K"]},
        ],
    },

    "google": {
        "name": "Google Gemini", "icon": "🔵",
        "sdk_type": "openai_compat",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_hint": "AIza...",
        "models": [
            {"id": "gemini-3.1-pro-preview",          "label": "Gemini 3.1 Pro",     "desc": "Найновіший Gemini · топ reasoning 2026", "tags": ["новий", "топ"]},
            {"id": "gemini-3.1-flash-lite",           "label": "Gemini 3.1 Flash Lite","desc": "Перший Flash-Lite в серії 3 · швидкий", "tags": ["новий", "швидка"]},
            {"id": "gemini-3.1-flash-image",          "label": "Gemini 3.1 Flash Image","desc": "Оптимізований для зображень · швидкий","tags": ["новий", "vision"]},
            {"id": "gemini-3-flash",                  "label": "Gemini 3 Flash",     "desc": "Мультимодальний · складний reasoning",   "tags": ["новий"]},
            {"id": "gemini-2.5-pro-preview-05-06",    "label": "Gemini 2.5 Pro",     "desc": "1M контекст · потужний",                 "tags": ["топ", "1M"]},
            {"id": "gemini-2.5-flash-preview-05-20",  "label": "Gemini 2.5 Flash",   "desc": "Швидкий 2.5 · thinking mode · 1M",       "tags": ["1M"]},
            {"id": "gemini-2.0-flash",                "label": "Gemini 2.0 Flash",   "desc": "Стабільний Flash · мультимодальний",     "tags": ["vision", "1M"]},
            {"id": "gemini-2.0-flash-lite",           "label": "Gemini 2.0 Flash Lite", "desc": "Наймалий Gemini · дуже дешевий",      "tags": ["lite"]},
            {"id": "gemini-1.5-pro",                  "label": "Gemini 1.5 Pro",     "desc": "Перевірений · 2M контекст",              "tags": ["2M"]},
            {"id": "gemini-1.5-flash",                "label": "Gemini 1.5 Flash",   "desc": "Швидкий 1.5 · 1M контекст",             "tags": ["1M"]},
        ],
    },

    "mistral": {
        "name": "Mistral AI", "icon": "🔶",
        "sdk_type": "openai_compat",
        "base_url": "https://api.mistral.ai/v1",
        "key_hint": "...",
        "models": [
            {"id": "magistral-medium-2506",   "label": "Magistral Medium",     "desc": "Новий reasoning від Mistral · 2025",    "tags": ["новий", "reasoning"]},
            {"id": "magistral-small-2506",    "label": "Magistral Small",      "desc": "Малий reasoning · швидкий",             "tags": ["новий", "reasoning"]},
            {"id": "mistral-large-latest",    "label": "Mistral Large",        "desc": "Флагман Mistral · 128K",                "tags": ["топ", "128K"]},
            {"id": "mistral-medium-latest",   "label": "Mistral Medium",       "desc": "Баланс якості і швидкості",             "tags": ["128K"]},
            {"id": "codestral-2501",          "label": "Codestral 25.01",      "desc": "Спеціалізований кодер · 256K",          "tags": ["код", "256K"]},
            {"id": "codestral-latest",        "label": "Codestral (Latest)",   "desc": "Кращий для генерації коду",             "tags": ["код"]},
            {"id": "mistral-small-latest",    "label": "Mistral Small",        "desc": "Легка і швидка",                        "tags": ["швидка"]},
            {"id": "open-mistral-7b",         "label": "Mistral 7B",           "desc": "Open-source · мала",                   "tags": ["open"]},
        ],
    },

    "groq": {
        "name": "Groq", "icon": "⚡",
        "sdk_type": "openai_compat",
        "base_url": "https://api.groq.com/openai/v1",
        "key_hint": "gsk_...",
        "models": [
            {"id": "llama-4-maverick-17b-128e-instruct", "label": "Llama 4 Maverick",  "desc": "Новий Llama 4 · мультимодальний · 1M",  "tags": ["новий", "1M"]},
            {"id": "llama-4-scout-17b-16e-instruct",     "label": "Llama 4 Scout",     "desc": "Llama 4 · легка версія",                "tags": ["новий"]},
            {"id": "llama-3.3-70b-versatile",            "label": "Llama 3.3 70B",     "desc": "Найкращий Llama 3 на Groq · 128K",      "tags": ["рекомендована", "128K"]},
            {"id": "llama-3.1-70b-versatile",            "label": "Llama 3.1 70B",     "desc": "Потужний open-source",                  "tags": ["128K"]},
            {"id": "compound-beta",                      "label": "Compound Beta",     "desc": "З пошуком в інтернеті",                 "tags": ["search"]},
            {"id": "mixtral-8x7b-32768",                 "label": "Mixtral 8x7B",      "desc": "MoE архітектура · 32K",                 "tags": ["32K"]},
            {"id": "gemma2-9b-it",                       "label": "Gemma 2 9B",        "desc": "Google Gemma на Groq",                  "tags": []},
            {"id": "llama3-70b-8192",                    "label": "Llama 3 70B",       "desc": "Класичний Llama 3",                     "tags": ["8K"]},
        ],
    },

    "deepseek": {
        "name": "DeepSeek", "icon": "🐋",
        "sdk_type": "openai_compat",
        "base_url": "https://api.deepseek.com",
        "key_hint": "sk-...",
        "models": [
            {"id": "deepseek-chat",        "label": "DeepSeek V3",          "desc": "DeepSeek-V3 · найкращий чат · 64K",     "tags": ["топ", "64K"]},
            {"id": "deepseek-reasoner",    "label": "DeepSeek R1",          "desc": "Chain-of-thought reasoning · 64K",       "tags": ["reasoning", "64K"]},
            {"id": "deepseek-coder",       "label": "DeepSeek Coder",       "desc": "Спеціалізований для коду",               "tags": ["код"]},
            {"id": "deepseek-prover-v2",   "label": "DeepSeek Prover V2",   "desc": "Математика і логіка",                   "tags": ["math"]},
        ],
    },

    "xai": {
        "name": "xAI Grok", "icon": "✖",
        "sdk_type": "openai_compat",
        "base_url": "https://api.x.ai/v1",
        "key_hint": "xai-...",
        "models": [
            {"id": "grok-3",              "label": "Grok 3",             "desc": "Флагман xAI 2025 · 131K",           "tags": ["топ", "131K"]},
            {"id": "grok-3-fast",         "label": "Grok 3 Fast",        "desc": "Швидкий Grok 3",                    "tags": ["швидка", "131K"]},
            {"id": "grok-3-mini",         "label": "Grok 3 Mini",        "desc": "Reasoning · малий і швидкий",       "tags": ["reasoning"]},
            {"id": "grok-3-mini-fast",    "label": "Grok 3 Mini Fast",   "desc": "Найшвидший reasoning Grok",         "tags": ["reasoning", "швидка"]},
            {"id": "grok-2",              "label": "Grok 2",             "desc": "Попередній флагман",                 "tags": []},
            {"id": "grok-vision-beta",    "label": "Grok Vision",        "desc": "Бачить зображення",                 "tags": ["vision"]},
        ],
    },

    "perplexity": {
        "name": "Perplexity", "icon": "🌐",
        "sdk_type": "openai_compat",
        "base_url": "https://api.perplexity.ai",
        "key_hint": "pplx-...",
        "models": [
            {"id": "sonar-pro",                "label": "Sonar Pro",            "desc": "З пошуком у реальному часі · топ",    "tags": ["search", "топ"]},
            {"id": "sonar-reasoning-pro",      "label": "Sonar Reasoning Pro",  "desc": "Reasoning + пошук",                  "tags": ["search", "reasoning"]},
            {"id": "sonar-deep-research",      "label": "Sonar Deep Research",  "desc": "Глибокий веб-пошук і синтез",         "tags": ["search", "research"]},
            {"id": "sonar",                    "label": "Sonar",                "desc": "Базова модель з пошуком",             "tags": ["search"]},
            {"id": "sonar-reasoning",          "label": "Sonar Reasoning",      "desc": "Reasoning + пошук · легкий",         "tags": ["search", "reasoning"]},
            {"id": "r1-1776",                  "label": "R1-1776",              "desc": "DeepSeek R1 без цензури",            "tags": ["reasoning"]},
        ],
    },

    "cohere": {
        "name": "Cohere", "icon": "🟠",
        "sdk_type": "cohere",
        "base_url": None,
        "key_hint": "...",
        "models": [
            {"id": "command-a-03-2025",   "label": "Command A",         "desc": "Флагман Cohere 2025 · 256K",        "tags": ["топ", "256K"]},
            {"id": "command-r-plus",      "label": "Command R+",        "desc": "Потужний з RAG · 128K",             "tags": ["128K"]},
            {"id": "command-r-plus-08-2024","label":"Command R+ (Aug)", "desc": "Стабільна версія серпень 2024",     "tags": ["128K"]},
            {"id": "command-r",           "label": "Command R",         "desc": "Легкий і швидкий",                  "tags": []},
        ],
    },

    "together": {
        "name": "Together AI", "icon": "🤝",
        "sdk_type": "openai_compat",
        "base_url": "https://api.together.xyz/v1",
        "key_hint": "...",
        "models": [
            {"id": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "label": "Llama 4 Maverick",   "desc": "Новий Llama 4 від Meta · 1M",      "tags": ["новий", "1M"]},
            {"id": "Qwen/Qwen3-235B-A22B",                               "label": "Qwen3 235B",         "desc": "Величезний Qwen3 MoE · thinking",  "tags": ["reasoning", "великий"]},
            {"id": "Qwen/Qwen2.5-Coder-32B-Instruct",                   "label": "Qwen2.5 Coder 32B",  "desc": "Найкращий open-source кодер",      "tags": ["код"]},
            {"id": "deepseek-ai/DeepSeek-V3",                            "label": "DeepSeek V3",        "desc": "Open-source DeepSeek V3",          "tags": []},
            {"id": "meta-llama/Llama-3-70b-chat-hf",                    "label": "Llama 3 70B",        "desc": "Класичний Llama 3",                "tags": []},
            {"id": "mistralai/Mixtral-8x7B-Instruct-v0.1",              "label": "Mixtral 8x7B",       "desc": "MoE від Mistral",                  "tags": []},
        ],
    },

    "openrouter": {
        "name": "OpenRouter", "icon": "🔀",
        "sdk_type": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
        "key_hint": "sk-or-v1-...",
        "models": [
            {"id": "anthropic/claude-opus-4-7",                    "label": "Claude Opus 4.7",         "desc": "Через OpenRouter",   "tags": ["новий", "топ"]},
            {"id": "anthropic/claude-sonnet-4-6",                  "label": "Claude Sonnet 4.6",       "desc": "Через OpenRouter",   "tags": ["новий", "рекомендована"]},
            {"id": "openai/gpt-5.5",                               "label": "GPT-5.5",                 "desc": "Через OpenRouter",   "tags": ["новий", "топ"]},
            {"id": "openai/gpt-5.4-pro",                           "label": "GPT-5.4 Pro",             "desc": "Через OpenRouter",   "tags": ["новий"]},
            {"id": "openai/o3",                                    "label": "o3",                      "desc": "Через OpenRouter",   "tags": ["reasoning"]},
            {"id": "google/gemini-3.1-pro-preview",                "label": "Gemini 3.1 Pro",          "desc": "Через OpenRouter",   "tags": ["новий", "топ"]},
            {"id": "google/gemini-3-flash",                        "label": "Gemini 3 Flash",          "desc": "Через OpenRouter",   "tags": ["новий"]},
            {"id": "google/gemini-2.5-pro-preview-05-06",          "label": "Gemini 2.5 Pro",          "desc": "Через OpenRouter",   "tags": ["1M"]},
            {"id": "deepseek/deepseek-r1",                         "label": "DeepSeek R1",             "desc": "Через OpenRouter",   "tags": ["reasoning"]},
            {"id": "deepseek/deepseek-chat-v3-0324",               "label": "DeepSeek V3",             "desc": "Через OpenRouter",   "tags": []},
            {"id": "x-ai/grok-3",                                  "label": "Grok 3",                  "desc": "Через OpenRouter",   "tags": []},
            {"id": "meta-llama/llama-4-maverick",                  "label": "Llama 4 Maverick",        "desc": "Через OpenRouter",   "tags": ["новий"]},
            {"id": "qwen/qwen3-235b-a22b",                         "label": "Qwen3 235B",              "desc": "Через OpenRouter",   "tags": ["reasoning"]},
            {"id": "mistralai/magistral-medium-2506",              "label": "Magistral Medium",        "desc": "Через OpenRouter",   "tags": ["reasoning"]},
        ],
    },

    "azure": {
        "name": "Azure OpenAI", "icon": "☁️",
        "sdk_type": "azure",
        "base_url": "",   # user provides endpoint
        "key_hint": "Ваш Azure API ключ",
        "models": [
            {"id": "gpt-4o",        "label": "GPT-4o",        "desc": "На Azure · deployment name", "tags": []},
            {"id": "gpt-4.1",       "label": "GPT-4.1",       "desc": "На Azure",                   "tags": ["новий"]},
            {"id": "gpt-4-turbo",   "label": "GPT-4 Turbo",   "desc": "На Azure",                   "tags": []},
            {"id": "gpt-35-turbo",  "label": "GPT-3.5 Turbo", "desc": "На Azure · дешевий",         "tags": []},
            {"id": "o3-mini",       "label": "o3-mini",       "desc": "Reasoning на Azure",         "tags": ["reasoning"]},
        ],
    },

    "ollama": {
        "name": "Ollama (Local)", "icon": "🦙",
        "sdk_type": "openai_compat",
        "base_url": "http://localhost:11434/v1",
        "key_hint": "ollama (будь-який рядок)",
        "models": [
            {"id": "llama3.2",          "label": "Llama 3.2",         "desc": "Meta Llama 3.2 · локально",     "tags": ["local"]},
            {"id": "llama3.1",          "label": "Llama 3.1",         "desc": "Meta Llama 3.1",                "tags": ["local"]},
            {"id": "qwen3",             "label": "Qwen3",             "desc": "Qwen3 з thinking mode",         "tags": ["local", "reasoning"]},
            {"id": "qwen2.5-coder",     "label": "Qwen2.5 Coder",     "desc": "Кодер · локально",              "tags": ["local", "код"]},
            {"id": "deepseek-r1",       "label": "DeepSeek R1",       "desc": "Reasoning · локально",          "tags": ["local", "reasoning"]},
            {"id": "deepseek-coder-v2", "label": "DeepSeek Coder V2", "desc": "Кодер від DeepSeek",            "tags": ["local", "код"]},
            {"id": "codellama",         "label": "Code Llama",        "desc": "Meta Code Llama",               "tags": ["local", "код"]},
            {"id": "mistral",           "label": "Mistral 7B",        "desc": "Mistral локально",              "tags": ["local"]},
            {"id": "gemma3",            "label": "Gemma 3",           "desc": "Google Gemma 3",                "tags": ["local"]},
            {"id": "phi4",              "label": "Phi-4",             "desc": "Microsoft Phi-4 · малий",       "tags": ["local"]},
        ],
    },
}


def get_provider(provider_id: str) -> dict | None:
    return PROVIDERS.get(provider_id)


def all_provider_ids() -> list[str]:
    return list(PROVIDERS.keys())


def get_model_ids(provider_id: str) -> list[str]:
    """Return flat list of model id strings for a provider."""
    p = PROVIDERS.get(provider_id, {})
    return [m["id"] if isinstance(m, dict) else m for m in p.get("models", [])]
