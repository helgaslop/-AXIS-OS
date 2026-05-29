// AXIS OS — Order Confirmation Email
// Відправляє email підтвердження покупцю через Resend (безкоштовно).
// Налаштування: Netlify → Site settings → Environment variables
//   RESEND_API_KEY  = re_xxxxxxxxxxxxxxxx  (resend.com → безкоштовна реєстрація)
//   OWNER_EMAIL     = axis.os.assistant@gmail.com  (кому приходять нотифікації)

exports.handler = async (event) => {
  const CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS, body: '' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers: CORS, body: 'Method Not Allowed' };

  const apiKey    = process.env.RESEND_API_KEY;
  const ownerEmail = process.env.OWNER_EMAIL || 'axis.os.assistant@gmail.com';

  let body;
  try { body = JSON.parse(event.body || '{}'); } catch { body = {}; }

  const { email = '', plan = '', amount = '', method = '' } = body;

  if (!email || !email.includes('@')) {
    return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'invalid email' }) };
  }

  // Якщо немає API ключа — повертаємо OK (Netlify Forms вже повідомив власника)
  if (!apiKey) {
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, note: 'no RESEND_API_KEY' }) };
  }

  const planLabel = plan || 'AXIS OS License';
  const amountLabel = amount || '';

  // Email покупцю
  const buyerHtml = `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>
  body{font-family:'Segoe UI',Arial,sans-serif;background:#080c14;color:#e6edf3;margin:0;padding:0;}
  .wrap{max-width:520px;margin:40px auto;background:#0d1117;border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden;}
  .hdr{background:linear-gradient(135deg,#00d4ff,#7c3aed);padding:28px 32px;text-align:center;}
  .hdr h1{margin:0;font-size:22px;font-weight:900;color:#000;}
  .body{padding:28px 32px;}
  .badge{display:inline-block;background:rgba(0,212,255,.12);border:1px solid rgba(0,212,255,.3);
    color:#00d4ff;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:700;margin-bottom:16px;}
  h2{font-size:20px;font-weight:800;margin:0 0 12px;}
  p{color:#8b949e;font-size:14px;line-height:1.7;margin:0 0 12px;}
  .info-box{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:16px 20px;margin:20px 0;}
  .info-row{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;}
  .info-row span:first-child{color:#8b949e;}
  .info-row span:last-child{font-weight:700;color:#e6edf3;}
  .cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);
    color:#000;font-weight:800;padding:13px 28px;border-radius:10px;text-decoration:none;margin:20px 0 0;font-size:15px;}
  .footer{text-align:center;padding:16px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
</style></head>
<body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">✅ Замовлення отримано</div>
    <h2>Дякуємо за покупку!</h2>
    <p>Ми отримали ваше замовлення та перевіряємо оплату. Ключ ліцензії буде надісланий на цей email протягом <strong style="color:#e6edf3;">1–24 годин</strong>.</p>
    <div class="info-box">
      <div class="info-row"><span>План</span><span>${planLabel}</span></div>
      <div class="info-row"><span>Сума</span><span>${amountLabel}</span></div>
      <div class="info-row"><span>Спосіб оплати</span><span>${method}</span></div>
      <div class="info-row"><span>Email</span><span>${email}</span></div>
    </div>
    <p>Хочете прискорити процес? Напишіть нам в Telegram і ми перевіримо оплату одразу.</p>
    <a href="https://t.me/Helgaslopp" class="cta">Написати в Telegram @Helgaslopp</a>
  </div>
  <div class="footer">AXIS OS · axis.os.assistant@gmail.com · Якщо ви не робили це замовлення — ігноруйте цей лист.</div>
</div>
</body>
</html>`;

  // Email власнику
  const ownerHtml = `
<div style="font-family:Arial,sans-serif;padding:20px;background:#0d1117;color:#e6edf3;border-radius:10px;">
  <h2 style="color:#00d4ff;">🛒 Нове замовлення AXIS OS</h2>
  <p><strong>План:</strong> ${planLabel}</p>
  <p><strong>Сума:</strong> ${amountLabel}</p>
  <p><strong>Метод:</strong> ${method}</p>
  <p><strong>Email покупця:</strong> <a href="mailto:${email}" style="color:#00d4ff;">${email}</a></p>
  <hr style="border-color:rgba(255,255,255,.1);">
  <p style="color:#8b949e;font-size:13px;">Перевір оплату і надішли ключ ліцензії на email покупця.</p>
</div>`;

  try {
    // Надсилаємо обидва листи паралельно
    const [buyerRes, ownerRes] = await Promise.all([
      fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: 'AXIS OS <onboarding@resend.dev>',
          to: [email],
          subject: `✅ AXIS OS — Замовлення отримано (${planLabel})`,
          html: buyerHtml
        })
      }),
      fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: 'AXIS OS Orders <onboarding@resend.dev>',
          to: [ownerEmail],
          subject: `🛒 Нове замовлення: ${planLabel} — ${email}`,
          html: ownerHtml
        })
      })
    ]);

    if (!buyerRes.ok) {
      const err = await buyerRes.text();
      throw new Error(`Resend error ${buyerRes.status}: ${err}`);
    }

    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };

  } catch (err) {
    console.error('order-confirm error:', err);
    // Не повертаємо 500 — front-end показав success незалежно
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: false, error: err.message }) };
  }
};
