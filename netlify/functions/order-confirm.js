// AXIS OS — Order registration + confirmation emails (NO key sent here)
// Key is sent manually by owner from /admin after payment verification.
//
// Env vars: GMAIL_USER, GMAIL_PASS, OWNER_EMAIL, ADMIN_SECRET, URL

const nodemailer   = require('nodemailer');
const { getStore } = require('@netlify/blobs');

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function isValidEmail(e) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(e||''));
}

async function saveOrder(order) {
  try {
    const store = getStore('axis-licenses');
    const db    = (await store.get('db', { type:'json' })) || { licenses:{}, orders:{} };
    if (!db.orders) db.orders = {};
    db.orders[order.ref] = order;
    await store.setJSON('db', db);
  } catch(e) { console.error('[Order] Blobs save failed:', e.message); }
}

const CORS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json'
};

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return { statusCode:200, headers:CORS, body:'' };
  if (event.httpMethod !== 'POST')    return { statusCode:405, headers:CORS, body:'Method Not Allowed' };

  const gmailUser  = process.env.GMAIL_USER  || 'axis.os.assistant@gmail.com';
  const gmailPass  = process.env.GMAIL_PASS;
  const ownerEmail = process.env.OWNER_EMAIL || gmailUser;
  const siteUrl    = process.env.URL         || 'https://axis-os.netlify.app';

  if (!gmailPass) {
    console.log('GMAIL_PASS not set — skipping emails');
    return { statusCode:200, headers:CORS, body:JSON.stringify({ ok:true, note:'no GMAIL_PASS' }) };
  }

  // Rate limit: max 5 orders per IP per hour
  const ip = (event.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  if (gmailPass) { // only rate-limit if email sending is active
    try {
      const rlStore = getStore('axis-licenses');
      const now = Date.now();
      const key  = `ratelimit:order:${ip}`;
      const rl   = (await rlStore.get(key, { type: 'json' })) || { count: 0, window: now };
      if (now - rl.window > 3600000) { rl.count = 0; rl.window = now; }
      rl.count++;
      await rlStore.setJSON(key, rl);
      if (rl.count > 5) {
        return { statusCode: 429, headers: CORS, body: JSON.stringify({ error: 'Too many requests' }) };
      }
    } catch(e) { /* non-fatal */ }
  }

  let body = {};
  try { body = JSON.parse(event.body || '{}'); } catch {}

  const { email='', plan='', amount='', method='',
          name='', surname='', phone='', deviceId='', orderRef='' } = body;

  if (!isValidEmail(email)) {
    return { statusCode:400, headers:CORS, body:JSON.stringify({ error:'invalid email' }) };
  }

  // Whitelist validation — prevents oversized inputs and unexpected values
  const VALID_METHODS = ['USDT TRC20', 'PayPal', 'Monobank'];
  const planLower = (plan || '').toLowerCase();
  const validPlan = planLower.includes('місячний') || planLower.includes('річний') ||
                    planLower.includes('lifetime') || planLower.includes('monthly') ||
                    planLower.includes('yearly');
  if (!validPlan && plan) {
    return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'invalid plan' }) };
  }
  // Truncate fields to safe lengths
  const safeName    = String(name    || '').slice(0, 100);
  const safeSurname = String(surname || '').slice(0, 100);
  const safePhone   = String(phone   || '').replace(/[^\d\s\+\-\(\)]/g, '').slice(0, 20);
  const safeRef     = String(orderRef|| '').replace(/[^A-Z0-9\-]/g, '').slice(0, 12);

  const ref      = safeRef || ('AX-??????');
  const fullName = [safeName, safeSurname].filter(Boolean).join(' ');

  // ── Save pending order ───────────────────────────────────────────────────
  await saveOrder({
    ref, email, name:fullName, phone:safePhone||'',
    plan, amount, method, deviceId:deviceId||'',
    createdAt: new Date().toISOString(),
    status: 'pending',   // pending → fulfilled
    licenseKey: null,
  });

  // ── Escaped values ───────────────────────────────────────────────────────
  const eRef      = escHtml(ref);
  const ePlan     = escHtml(plan);
  const eAmount   = escHtml(amount);
  const eMethod   = escHtml(method);
  const eEmail    = escHtml(email);
  const eName     = escHtml(safeName);
  const eSurname  = escHtml(safeSurname);
  const ePhone    = escHtml(safePhone);
  const eDeviceId = escHtml(deviceId);
  const eFullName = escHtml(fullName);
  const greeting  = eFullName
    ? `Привіт, <strong style="color:#e6edf3;">${eFullName}</strong>!`
    : 'Вітаємо!';

  const adminLink = `${siteUrl}/admin`;

  const CSS = `
body{font-family:'Segoe UI',Arial,sans-serif;background:#080c14;color:#e6edf3;margin:0;padding:20px;}
.wrap{max-width:520px;margin:0 auto;background:#0d1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;overflow:hidden;}
.hdr{background:linear-gradient(135deg,#00d4ff,#7c3aed);padding:24px 32px;text-align:center;}
.hdr h1{margin:0;font-size:22px;font-weight:900;color:#000;}
.body{padding:28px 32px;}
.badge{display:inline-block;background:rgba(0,212,255,.1);border:1px solid rgba(0,212,255,.3);color:#00d4ff;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:700;margin-bottom:16px;}
h2{font-size:20px;font-weight:800;margin:0 0 12px;}
p{color:#8b949e;font-size:14px;line-height:1.7;margin:0 0 12px;}
.refbox{background:#161b22;border:2px solid rgba(0,212,255,.4);border-radius:12px;padding:16px 22px;text-align:center;margin:16px 0;}
.reftext{font-family:monospace;font-size:26px;font-weight:900;color:#00d4ff;letter-spacing:.18em;}
.info{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:14px 20px;margin:12px 0;}
.row{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;border-bottom:1px solid rgba(255,255,255,.05);}
.row:last-child{border:none;}.row span:first-child{color:#8b949e;}.row span:last-child{font-weight:700;word-break:break-all;}
.cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:12px 0;font-size:15px;}
.cta-green{background:linear-gradient(135deg,#3fb950,#238636);}
.foot{text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
.dev{font-size:11px;color:#30363d;margin-top:6px;font-family:monospace;}`;

  // ── Email to BUYER — confirmation + reference code ───────────────────────
  const buyerHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${CSS}</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">✅ Замовлення зареєстровано</div>
    <h2>Дякуємо!</h2>
    <p>${greeting} Ваше замовлення отримано. Після підтвердження оплати ми надішлемо ліцензійний ключ на цей email.</p>
    <p style="font-size:13px;color:#8b949e;">⏱ Зазвичай це займає до <strong style="color:#e6edf3;">1–4 годин</strong> в робочий час.</p>

    <p style="font-size:13px;font-weight:700;margin-bottom:4px;">Ваш код замовлення:</p>
    <div class="refbox">
      <div style="font-size:11px;color:#484f58;margin-bottom:5px;text-transform:uppercase;letter-spacing:.06em;">Вкажіть у призначенні платежу</div>
      <div class="reftext">${eRef}</div>
      <div style="font-size:12px;color:#8b949e;margin-top:6px;">Текст для призначення: <strong style="color:#e6edf3;">AXIS ${eRef}</strong></div>
    </div>

    <div class="info">
      ${eFullName ? `<div class="row"><span>Покупець</span><span>${eFullName}</span></div>` : ''}
      <div class="row"><span>План</span><span>${ePlan}</span></div>
      <div class="row"><span>Сума</span><span>${eAmount}</span></div>
      <div class="row"><span>Оплата</span><span>${eMethod}</span></div>
      <div class="row"><span>Email</span><span>${eEmail}</span></div>
      ${ePhone ? `<div class="row"><span>Телефон</span><span>${ePhone}</span></div>` : ''}
    </div>

    <p style="font-size:12px;">💾 Збережіть цей лист — в ньому є ваш код замовлення та деталі.</p>
    <a href="https://t.me/Helgaslopp" class="cta">Запитання? Telegram @Helgaslopp</a>
  </div>
  <div class="foot">
    AXIS OS &mdash; <a href="https://t.me/Helgaslopp" style="color:#00d4ff;text-decoration:none;">@Helgaslopp</a><br>
    Якщо ви не робили це замовлення &mdash; ігноруйте лист.
    ${eDeviceId ? `<div class="dev">Device: ${eDeviceId}</div>` : ''}
  </div>
</div></body></html>`;

  // ── Email to OWNER — all order details + "Send key" button ───────────────
  const ownerHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${CSS}</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS — Нове замовлення</h1></div>
  <div class="body">
    <div class="badge">💰 ${eRef}</div>
    <h2>${eFullName || eEmail}</h2>
    <p>Нове замовлення зареєстровано. Перевір оплату в банку/гаманці і надішли ключ.</p>

    <div class="refbox" style="margin:14px 0 10px;">
      <div style="font-size:11px;color:#484f58;margin-bottom:4px;">КОД В ПРИЗНАЧЕННІ ПЛАТЕЖУ</div>
      <div class="reftext">${eRef}</div>
    </div>

    <div class="info">
      ${eFullName ? `<div class="row"><span>Покупець</span><span>${eFullName}</span></div>` : ''}
      <div class="row"><span>Email</span><span>${eEmail}</span></div>
      ${ePhone ? `<div class="row"><span>Телефон</span><span>${ePhone}</span></div>` : ''}
      <div class="row"><span>План</span><span>${ePlan}</span></div>
      <div class="row"><span>Сума</span><span>${eAmount}</span></div>
      <div class="row"><span>Метод</span><span>${eMethod}</span></div>
      <div class="row"><span>Час</span><span>${new Date().toLocaleString('uk-UA',{timeZone:'Europe/Kyiv'})}</span></div>
      ${eDeviceId ? `<div class="row"><span>Device ID</span><span style="font-family:monospace;font-size:12px;">${eDeviceId}</span></div>` : ''}
    </div>

    <p style="font-weight:700;color:#e6edf3;">✅ Підтвердив оплату? Натисни кнопку:</p>
    <a href="${adminLink}" class="cta cta-green" style="font-size:16px;">🔑 Надіслати ключ (відкрити адмін)</a>
    <p style="font-size:11px;color:#484f58;margin-top:6px;">В адмін-панелі знайди замовлення за кодом <strong>${eRef}</strong> → "Надіслати ключ"</p>
  </div>
  <div class="foot">AXIS OS Admin Notification</div>
</div></body></html>`;

  const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: { user: gmailUser, pass: gmailPass }
  });

  const errors = [];

  try {
    await transporter.sendMail({
      from: `"AXIS OS" <${gmailUser}>`,
      to: email,
      subject: `✅ AXIS OS — Замовлення ${ref} отримано (${plan})`,
      html: buyerHtml,
    });
    console.log(`[Email] Confirmation sent to buyer: ${email} (ref: ${ref})`);
  } catch(e) {
    console.error('[Email] Buyer email failed:', e.message);
    errors.push('buyer:' + e.message);
  }

  try {
    await transporter.sendMail({
      from: `"AXIS OS" <${gmailUser}>`,
      to: ownerEmail,
      subject: `💰 AXIS OS — ${ref} | ${fullName||email} | ${plan} ${amount}`,
      html: ownerHtml,
    });
    console.log(`[Email] Owner notified: ${ownerEmail}`);
  } catch(e) {
    console.error('[Email] Owner email failed:', e.message);
    errors.push('owner:' + e.message);
  }

  return {
    statusCode: 200,
    headers: CORS,
    body: JSON.stringify({ ok:true, ref, errors: errors.length ? errors : undefined })
  };
};
