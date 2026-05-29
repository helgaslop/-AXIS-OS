// AXIS OS — Order Confirmation Email via Gmail SMTP
// Налаштування: Netlify → Environment variables
//   GMAIL_USER = axis.os.assistant@gmail.com
//   GMAIL_PASS = xxxx xxxx xxxx xxxx  (App Password з Google Account)

const nodemailer = require('nodemailer');

// ── HTML entity escaping — prevents XSS in email template ──────────────────
function escHtml(str) {
  return String(str || '')
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

// ── Strict email validation — prevents header injection ─────────────────────
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(email || ''));
}

exports.handler = async (event) => {
  const CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS, body: '' };
  if (event.httpMethod !== 'POST')    return { statusCode: 405, headers: CORS, body: 'Method Not Allowed' };

  const gmailUser = process.env.GMAIL_USER || 'axis.os.assistant@gmail.com';
  const gmailPass = process.env.GMAIL_PASS;

  // Якщо немає пароля — OK, Netlify Forms вже сповістив власника
  if (!gmailPass) {
    console.log('GMAIL_PASS not set — skipping email');
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, note: 'no GMAIL_PASS' }) };
  }

  let body;
  try { body = JSON.parse(event.body || '{}'); } catch { body = {}; }

  const {
    email    = '',
    plan     = '',
    amount   = '',
    method   = '',
    name     = '',
    surname  = '',
    phone    = '',
    deviceId = ''
  } = body;

  // Validate email strictly — prevents header injection and garbage addresses
  if (!isValidEmail(email)) {
    return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'invalid email' }) };
  }

  // Escape all user-supplied fields before placing them in HTML
  const ePlan     = escHtml(plan);
  const eAmount   = escHtml(amount);
  const eMethod   = escHtml(method);
  const eEmail    = escHtml(email);
  const eName     = escHtml(name);
  const eSurname  = escHtml(surname);
  const ePhone    = escHtml(phone);
  const eDeviceId = escHtml(deviceId);
  const eFullName = (eName || eSurname) ? `${eName} ${eSurname}`.trim() : '';
  const greeting  = eFullName
    ? `Привіт, <strong style="color:#e6edf3;">${eFullName}</strong>!`
    : 'Вітаємо!';

  const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: { user: gmailUser, pass: gmailPass }
  });

  const buyerHtml = `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>
body{font-family:'Segoe UI',Arial,sans-serif;background:#080c14;color:#e6edf3;margin:0;padding:20px;}
.wrap{max-width:520px;margin:0 auto;background:#0d1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;overflow:hidden;}
.hdr{background:linear-gradient(135deg,#00d4ff,#7c3aed);padding:24px 32px;text-align:center;}
.hdr h1{margin:0;font-size:22px;font-weight:900;color:#000;}
.body{padding:28px 32px;}
.badge{display:inline-block;background:rgba(0,212,255,.1);border:1px solid rgba(0,212,255,.3);
  color:#00d4ff;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:700;margin-bottom:16px;}
h2{font-size:20px;font-weight:800;margin:0 0 12px;}
p{color:#8b949e;font-size:14px;line-height:1.7;margin:0 0 12px;}
.info{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:16px 20px;margin:16px 0;}
.row{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;border-bottom:1px solid rgba(255,255,255,.05);}
.row:last-child{border:none;}
.row span:first-child{color:#8b949e;}
.row span:last-child{font-weight:700;word-break:break-all;}
.cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);
  color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:20px 0 0;font-size:15px;}
.foot{text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
.dev{font-size:11px;color:#30363d;margin-top:6px;font-family:monospace;letter-spacing:.05em;}
</style></head>
<body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">✅ Замовлення отримано</div>
    <h2>Дякуємо за покупку!</h2>
    <p>${greeting} Ми отримали ваше замовлення і перевіряємо оплату. Ліцензійний ключ надішлемо на цей email протягом <strong style="color:#e6edf3;">1–24 годин</strong>.</p>
    <div class="info">
      ${eFullName ? `<div class="row"><span>Покупець</span><span>${eFullName}</span></div>` : ''}
      <div class="row"><span>План</span><span>${ePlan}</span></div>
      <div class="row"><span>Сума</span><span>${eAmount}</span></div>
      <div class="row"><span>Оплата</span><span>${eMethod}</span></div>
      <div class="row"><span>Email</span><span>${eEmail}</span></div>
      ${ePhone ? `<div class="row"><span>Телефон</span><span>${ePhone}</span></div>` : ''}
    </div>
    <p>Хочете швидше? Напишіть нам у Telegram — відповімо одразу.</p>
    <a href="https://t.me/Helgaslopp" class="cta">Написати в Telegram @Helgaslopp</a>
  </div>
  <div class="foot">
    AXIS OS &mdash; Підтримка: <a href="https://t.me/Helgaslopp" style="color:#00d4ff;text-decoration:none;">@Helgaslopp</a><br>
    Якщо ви не робили це замовлення &mdash; ігноруйте лист.
    ${eDeviceId ? `<div class="dev">Device ID: ${eDeviceId}</div>` : ''}
  </div>
</div>
</body></html>`;

  try {
    await transporter.sendMail({
      from: `"AXIS OS" <${gmailUser}>`,
      to: email,
      subject: `✅ AXIS OS — Замовлення отримано (${escHtml(plan)})`,
      html: buyerHtml
    });

    console.log(`Confirmation email sent to ${email}`);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };

  } catch (err) {
    console.error('order-confirm error:', err.message);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: false, error: err.message }) };
  }
};
