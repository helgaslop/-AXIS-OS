// AXIS OS Support Chat — Netlify Function
// Проксі до OpenAI GPT-4o-mini.
// Встанови OPENAI_API_KEY в Netlify → Site settings → Environment variables.

const SYSTEM_PROMPT = `
Ти — Axis, розумний асистент підтримки AXIS OS.
AXIS OS — це AI голосовий асистент для Windows із голосовою сферою, яка живе в треї.

─── ПРОДУКТ ────────────────────────────────────
• Wake-word активація ("джарвіс" / "axis")
• AI: GPT-4o, Claude, Gemini, Grok, DeepSeek, Ollama (офлайн)
• STT: Whisper (офлайн), OpenAI Whisper API, Google
• TTS: OpenAI (onyx, nova...), Edge Neural (40+ мов), Silero (офлайн)
• Мультимовний TTS: "скажи вірш по-німецьки", "say something in french"
• Інтеграції: Spotify Web API, Telegram бот, Steam ігри
• Команди: Shell, Python, URL, Internal + власні макроси
• Системний монітор: CPU, RAM, диски, процеси
• Нотатки, ToDo, звички, фокус-режим, Pomodoro, будильники
• Аналіз екрану/документів через AI (vision)
• Chrome History, OCR, speedtest, WiFi devices
• Системні вимоги: Windows 10/11, Python 3.10+, RAM 4GB+

─── ЛІЦЕНЗІЇ та ЦІНИ ───────────────────────────
• Пробний — $0 / 7 днів: AI 20 повід/день, голос 30 команд/день, без агентів
• Місячний — $5/міс: все необмежено, AI агенти, генерація зображень, пріоритетна підтримка
• Річний — $40/рік ($3.3/міс, -33%): все + ранній доступ до нових функцій
• Назавжди (Lifetime) — $99 одноразово: все + необмежені пристрої + VIP підтримка

─── ОПЛАТА ─────────────────────────────────────
Telegram: @Helgaslopp  |  Email: axis.os.assistant@gmail.com
Методи: Monobank, PrivatBank, PayPal, крипто (USDT, BTC)
Після оплати → ключ одразу в Telegram/email → AXIS OS → Налаштування → Ліцензія

─── ПОШИРЕНІ ПРОБЛЕМИ ──────────────────────────
1. Мікрофон не розпізнає:
   - Перевір: Windows → Налаштування → Конфіденційність → Мікрофон → дозволити Python
   - Встанови PyAudio: pip install PyAudio
   - Спробуй інший провайдер STT (Settings → STT Provider)

2. Sphere не запускається:
   - Запусти від імені адміністратора
   - Перевір Python 3.10+: python --version
   - Встанови залежності: pip install -r requirements.txt

3. API ключ не приймається:
   - Ключ зберігається в Windows Credential Manager
   - Перезапусти AXIS OS після введення ключа
   - Перевір чи немає зайвих пробілів у ключі

4. TTS не озвучує:
   - edge-tts: pip install edge-tts
   - OpenAI TTS: перевір ключ OpenAI в налаштуваннях
   - Whisper офлайн: pip install openai-whisper

5. Помилка при запуску (.bat файл):
   - Переконайся що Python є в PATH
   - Запусти в терміналі: python aivon_sphere.py

─── ПРАВИЛА ВІДПОВІДІ ──────────────────────────
1. Відповідай МОВОЮ КОРИСТУВАЧА (укр/рос/англ)
2. Будь конкретним і коротким (3-6 речень)
3. Якщо людина хоче КУПИТИ — скажи про плани та направ до Telegram/email
4. Якщо не можеш вирішити проблему — запропонуй: axis.os.assistant@gmail.com
5. Ніколи не вигадуй функції яких немає — скажи чесно
6. Додавай конкретні команди pip/python де потрібно
`;

// Ключові слова замовлення
const ORDER_KEYWORDS = [
  'замовити','купити','придбати','оплатити','ліцензія','ліцензію','ключ активац',
  'місячний план','річний план','lifetime','назавжди','підписка','ціна','вартість',
  'скільки коштує','як оплатити','хочу придбати','хочу купити',
  'order','buy','purchase','price','subscription','license','payment',
  'заказать','купить','лицензия','оплатить','подписка','сколько стоит'
];

// Ключові слова для ескалації до живої людини
const ESCALATE_KEYWORDS = [
  'написати вам','зв\'язатись','поговорити','жива людина','менеджер',
  'contact','human','talk to','agent','manager'
];

exports.handler = async (event) => {
  // CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
      },
      body: ''
    };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  try {
    const { message, history = [] } = JSON.parse(event.body || '{}');

    if (!message || typeof message !== 'string') {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'message is required' })
      };
    }

    // Визначаємо намір по ключових словах
    const lower = message.toLowerCase();
    let intent = 'support';
    if (ORDER_KEYWORDS.some(kw => lower.includes(kw))) intent = 'order';
    if (ESCALATE_KEYWORDS.some(kw => lower.includes(kw))) intent = 'escalate';

    const apiKey = process.env.OPENAI_API_KEY;

    // Якщо немає API ключа — fallback відповідь
    if (!apiKey) {
      const fallback = intent === 'order'
        ? 'Для оформлення замовлення напишіть нам:\n📱 Telegram: @Helgaslopp\n📧 Email: axis.os.assistant@gmail.com\n\nВкажіть який план вас цікавить і ми відповімо протягом кількох годин.'
        : 'На жаль, чат-підтримка тимчасово недоступна. Зверніться:\n📧 axis.os.assistant@gmail.com\n📱 Telegram: @Helgaslopp';
      return {
        statusCode: 200,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify({ text: fallback, intent: intent === 'support' ? 'escalate' : intent })
      };
    }

    // Збираємо повідомлення для GPT
    const safeHistory = (Array.isArray(history) ? history : [])
      .slice(-10)
      .filter(m => m && m.role && m.content);

    const messages = [
      { role: 'system', content: SYSTEM_PROMPT },
      ...safeHistory,
      { role: 'user', content: message }
    ];

    // Виклик OpenAI API
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages,
        max_tokens: 500,
        temperature: 0.65
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`OpenAI API error ${response.status}: ${errText}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error.message);
    }

    const text = data.choices?.[0]?.message?.content || 'Не вдалося отримати відповідь.';

    // GPT міг підтвердити замовлення у тексті відповіді
    const textLower = text.toLowerCase();
    if (intent === 'support' && (
      textLower.includes('telegram') && textLower.includes('план') ||
      textLower.includes('@helgaslopp') ||
      textLower.includes('придбати') || textLower.includes('замовити')
    )) {
      intent = 'order';
    }

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({ text, intent })
    };

  } catch (err) {
    console.error('support-chat error:', err);
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({
        text: `Виникла помилка підключення. Зверніться напряму:\n📧 axis.os.assistant@gmail.com\n📱 @Helgaslopp`,
        intent: 'escalate'
      })
    };
  }
};
