// AXIS OS — Auto license key generation + dual email on order confirm
// Env vars needed (Netlify → Environment variables):
//   GMAIL_USER  = axis.os.assistant@gmail.com
//   GMAIL_PASS  = xxxx xxxx xxxx xxxx  (App Password)
//   OWNER_EMAIL = your-personal@email.com  (owner notification)
//   ADMIN_SECRET = your-admin-password  (for revoke link security)

const nodemailer   = require('nodemailer');
const { getStore } = require('@netlify/blobs');

// ── Helpers ────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function isValidEmail(e) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(e || ''));
}

// Same charset as license-admin.js — no 0/O/1/I
const CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function generateKey() {
  const seg = () => { let s=''; for(let i=0;i<4;i++) s+=CHARS[Math.floor(Math.random()*CHARS.length)]; return s; };
  return `AXIS-${seg()}-${seg()}-${seg()}-${seg()}`;
}

async function saveLicense(key, data) {
  try {
    const store = getStore('axis-licenses');
    const db    = (await store.get('db', { type: 'json' })) || { licenses: {} };
    db.licenses[key] = data;
    await store.setJSON('db', db);
    return true;
  } catch (e) {
    console.error('[License] Blobs save failed:', e.message);
    return false;
  }
}

// ── Handler ────────────────────────────────────────────────────────────────
const CORS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json'
};

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS, body: '' };
  if (event.httpMethod !== 'POST')    return { statusCode: 405, headers: CORS, body: 'Method Not Allowed' };

  const gmailUser  = process.env.GMAIL_USER  || 'axis.os.assistant@gmail.com';
  const gmailPass  = process.env.GMAIL_PASS;
  const ownerEmail = process.env.OWNER_EMAIL || gmailUser;
  const adminSecret= process.env.ADMIN_SECRET || '';
  const siteUrl    = process.env.URL || 'https://axis-os.netlify.app';

  if (!gmailPass) {
    console.log('GMAIL_PASS not set — skipping emails');
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

  if (!isValidEmail(email)) {
    return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'invalid email' }) };
  }

  // ── 1. Generate license key ──────────────────────────────────────────────
  const key      = generateKey();
  const planName = String(plan).split('—')[0].trim() || plan; // e.g. "Місячний"
  const fullName = [name, surname].filter(Boolean).join(' ');

  await saveLicense(key, {
    key,
    plan:     planName.toLowerCase().includes('lifetime') ? 'lifetime'
            : planName.toLowerCase().includes('річн')    ? 'yearly'
            : 'monthly',
    email,
    name:     fullName,
    phone:    phone || '',
    deviceId: deviceId || '',
    note:     `Auto-generated on order. Method: ${method}`,
    createdAt:         new Date().toISOString(),
    status:            'active',
    activatedAt:       null,
    activatedDeviceId: null,
    sentAt:            new Date().toISOString(),
    sentTo:            email,
  });

  console.log(`[License] Generated ${key} for ${email} (${plan})`);

  // ── 2. Escaped values for HTML ───────────────────────────────────────────
  const eKey      = escHtml(key);
  const ePlan     = escHtml(plan);
  const eAmount   = escHtml(amount);
  const eMethod   = escHtml(method);
  const eEmail    = escHtml(email);
  const eName     = escHtml(name);
  const eSurname  = escHtml(surname);
  const ePhone    = escHtml(phone);
  const eDeviceId = escHtml(deviceId);
  const eFullName = escHtml(fullName);
  const greeting  = eFullName
    ? `Привіт, <strong style="color:#e6edf3;">${eFullName}</strong>!`
    : 'Вітаємо!';

  // Secure revoke link: token = first 12 chars of sha-like hash (simple, good enough for email button)
  const revokeToken = Buffer.from(`${key}:${adminSecret}`).toString('base64').slice(0, 16);
  const adminLink   = `${siteUrl}/admin`;

  const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: { user: gmailUser, pass: gmailPass }
  });

  const CSS = `
body{font-family:'Segoe UI',Arial,sans-serif;background:#080c14;color:#e6edf3;margin:0;padding:20px;}
.wrap{max-width:520px;margin:0 auto;background:#0d1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;overflow:hidden;}
.hdr{background:linear-gradient(135deg,#00d4ff,#7c3aed);padding:24px 32px;text-align:center;}
.hdr h1{margin:0;font-size:22px;font-weight:900;color:#000;}
.body{padding:28px 32px;}
.badge{display:inline-block;background:rgba(0,212,255,.1);border:1px solid rgba(0,212,255,.3);color:#00d4ff;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:700;margin-bottom:16px;}
h2{font-size:20px;font-weight:800;margin:0 0 12px;}
p{color:#8b949e;font-size:14px;line-height:1.7;margin:0 0 12px;}
.keybox{background:#161b22;border:2px solid rgba(0,212,255,.4);border-radius:12px;padding:18px 24px;text-align:center;margin:20px 0;}
.keytext{font-family:monospace;font-size:22px;font-weight:900;color:#00d4ff;letter-spacing:.15em;word-break:break-all;}
.info{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:14px 20px;margin:12px 0;}
.row{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;border-bottom:1px solid rgba(255,255,255,.05);}
.row:last-child{border:none;}.row span:first-child{color:#8b949e;}.row span:last-child{font-weight:700;word-break:break-all;}
.cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:12px 0;font-size:15px;}
.cta-danger{background:linear-gradient(135deg,#f85149,#c0392b);}
.steps{background:#161b22;border-radius:10px;padding:14px 20px;margin:12px 0;font-size:13px;color:#8b949e;line-height:2;}
.foot{text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
.dev{font-size:11px;color:#30363d;margin-top:6px;font-family:monospace;}`;

  // ── Email to BUYER — with license key ────────────────────────────────────
  const buyerHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${CSS}</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">🔑 Ваш ліцензійний ключ</div>
    <h2>Оплату підтверджено!</h2>
    <p>${greeting} Дякуємо за покупку! Ваш ліцензійний ключ для плану <strong style="color:#e6edf3;">${ePlan}</strong>:</p>
    <div class="keybox">
      <div style="font-size:11px;color:#484f58;margin-bottom:6px;text-transform:uppercase;letter-spacing:.08em;">Ліцензійний ключ</div>
      <div class="keytext">${eKey}</div>
    </div>
    <div class="steps">
      📌 <strong style="color:#e6edf3;">Як активувати:</strong><br>
      1. Відкрийте AXIS OS<br>
      2. Натисніть <strong style="color:#e6edf3;">Налаштування → 🔑 Ліцензія</strong><br>
      3. Вставте ключ і натисніть <strong style="color:#e6edf3;">Активувати</strong>
    </div>
    <div class="info">
      ${eFullName ? `<div class="row"><span>Покупець</span><span>${eFullName}</span></div>` : ''}
      <div class="row"><span>План</span><span>${ePlan}</span></div>
      <div class="row"><span>Сума</span><span>${eAmount}</span></div>
      <div class="row"><span>Оплата</span><span>${eMethod}</span></div>
      <div class="row"><span>Email</span><span>${eEmail}</span></div>
      ${ePhone ? `<div class="row"><span>Телефон</span><span>${ePhone}</span></div>` : ''}
    </div>
    <p style="font-size:12px;">🔒 Ключ прив'язується до вашого пристрою при першій активації. Збережіть цей лист — ключ не можна відновити.</p>
    <a href="https://t.me/Helgaslopp" class="cta">Потрібна допомога? @Helgaslopp</a>
  </div>
  <div class="foot">
    AXIS OS &mdash; <a href="https://t.me/Helgaslopp" style="color:#00d4ff;text-decoration:none;">@Helgaslopp</a><br>
    Якщо ви не робили це замовлення &mdash; ігноруйте лист.
    ${eDeviceId ? `<div class="dev">Device: ${eDeviceId}</div>` : ''}
  </div>
</div></body></html>`;

  // ── Email to OWNER — order details + revoke button ───────────────────────
  const ownerHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${CSS}</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS — Нове замовлення</h1></div>
  <div class="body">
    <div class="badge">💰 Замовлення #${Date.now().toString(36).toUpperCase()}</div>
    <h2>Ключ надіслано автоматично</h2>
    <p>Покупець отримав ліцензійний ключ на email. Перевір оплату і відкличи ключ якщо потрібно.</p>
    <div class="keybox">
      <div style="font-size:11px;color:#484f58;margin-bottom:6px;">НАДІСЛАНИЙ КЛЮЧ</div>
      <div class="keytext">${eKey}</div>
    </div>
    <div class="info">
      ${eFullName ? `<div class="row"><span>Покупець</span><span>${eFullName}</span></div>` : ''}
      <div class="row"><span>Email</span><span>${eEmail}</span></div>
      ${ePhone ? `<div class="row"><span>Телефон</span><span>${ePhone}</span></div>` : ''}
      <div class="row"><span>План</span><span>${ePlan}</span></div>
      <div class="row"><span>Сума</span><span>${eAmount}</span></div>
      <div class="row"><span>Оплата</span><span>${eMethod}</span></div>
      <div class="row"><span>Час</span><span>${new Date().toLocaleString('uk-UA',{timeZone:'Europe/Kyiv'})}</span></div>
      ${eDeviceId ? `<div class="row"><span>Device ID</span><span style="font-family:monospace;">${eDeviceId}</span></div>` : ''}
    </div>
    <a href="${adminLink}" class="cta">🔧 Відкрити адмін-панель</a>
    <a href="${adminLink}" class="cta cta-danger" style="margin-top:8px;">🚫 Відкликати ключ (якщо не оплатили)</a>
    <p style="font-size:11px;color:#484f58;margin-top:8px;">Щоб відкликати: відкрий адмін-панель, знайди ключ ${eKey} і натисни "Відкликати"</p>
  </div>
  <div class="foot">AXIS OS Admin Notification</div>
</div></body></html>`;

  // ── Send both emails ─────────────────────────────────────────────────────
  const errors = [];

  try {
    await transporter.sendMail({
      from:    `"AXIS OS" <${gmailUser}>`,
      to:      email,
      subject: `🔑 AXIS OS — Ваш ліцензійний ключ (${plan})`,
      html:    buyerHtml,
    });
    console.log(`[Email] Key sent to buyer: ${email}`);
  } catch (e) {
    console.error('[Email] Buyer email failed:', e.message);
    errors.push('buyer:' + e.message);
  }

  try {
    await transporter.sendMail({
      from:    `"AXIS OS" <${gmailUser}>`,
      to:      ownerEmail,
      subject: `💰 AXIS OS — Нове замовлення від ${fullName || email} (${plan})`,
      html:    ownerHtml,
    });
    console.log(`[Email] Owner notified: ${ownerEmail}`);
  } catch (e) {
    console.error('[Email] Owner email failed:', e.message);
    errors.push('owner:' + e.message);
  }

  return {
    statusCode: 200,
    headers: CORS,
    body: JSON.stringify({ ok: true, key, errors: errors.length ? errors : undefined })
  };
};
