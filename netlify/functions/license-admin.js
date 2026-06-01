// AXIS OS — License Admin API
// Protected by ADMIN_SECRET env var (set in Netlify → Environment variables)
//
// POST  action=generate  → generate a new license key
// GET   action=list      → return all licenses
// POST  action=revoke    → revoke a key
// POST  action=send      → send key email to buyer

const { getStore }  = require('@netlify/blobs');
const nodemailer    = require('nodemailer');
const crypto        = require('crypto');

// ── Blobs helper: pass siteID explicitly so it works outside Netlify CI context ──
function _store(name) {
  const opts = { name };
  const siteID = process.env.NETLIFY_SITE_ID || process.env.SITE_ID || '';
  const token  = process.env.NETLIFY_TOKEN   || process.env.NETLIFY_API_TOKEN || '';
  if (siteID) opts.siteID = siteID;
  if (token)  opts.token  = token;
  return getStore(opts);
}

// ── Helpers ────────────────────────────────────────────────────────────────
const CORS = {
  'Access-Control-Allow-Origin':  process.env.URL || 'https://axis-os-app.netlify.app',
  'Access-Control-Allow-Headers': 'Content-Type, x-admin-secret',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Content-Type': 'application/json'
};

// Alphanumeric without 0/O/1/I to avoid confusion when reading aloud or typing
const CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function seg() {
  let s = '';
  for (let i = 0; i < 4; i++) s += CHARS[crypto.randomInt(0, CHARS.length)];
  return s;
}
function generateKey() {
  return `AXIS-${seg()}-${seg()}-${seg()}-${seg()}`;
}

async function getDb(store) {
  const db = (await store.get('db', { type: 'json' })) || {};
  if (!db.licenses) db.licenses = {};
  if (!db.orders)   db.orders   = {};
  return db;
}
async function saveDb(store, db) {
  await store.setJSON('db', db);
}

function escHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Handler ────────────────────────────────────────────────────────────────
exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS, body: '' };

  const bodyLen = (event.body || '').length;
  if (event.httpMethod === 'POST' && bodyLen > 10240) {
    return { statusCode: 413, headers: CORS, body: JSON.stringify({ error: 'Payload too large' }) };
  }

  // Auth check
  const adminSecret = process.env.ADMIN_SECRET;
  const reqSecret   = event.headers['x-admin-secret'] || '';
  if (!adminSecret) {
    return { statusCode: 401, headers: CORS, body: JSON.stringify({ error: 'Unauthorized' }) };
  }
  const secretA = Buffer.from(reqSecret.padEnd(adminSecret.length, '\0').slice(0, adminSecret.length));
  const secretB = Buffer.from(adminSecret);
  if (secretA.length !== secretB.length || !crypto.timingSafeEqual(secretA, secretB)) {
    return { statusCode: 401, headers: CORS, body: JSON.stringify({ error: 'Unauthorized' }) };
  }

  const store = _store('axis-licenses');

  // Rate limit: max 20 requests per IP per minute
  const ip = ((event.headers['x-forwarded-for'] || '').split(',')[0].trim() || event.headers['client-ip'] || 'unknown').replace(/[^0-9a-fA-F.:]/g, '_').slice(0, 45);
  const rateLimitKey = `ratelimit:admin:${ip}`;
  try {
    const rlStore = _store('axis-ratelimits');
    const now = Date.now();
    const rl = (await rlStore.get(rateLimitKey, { type: 'json' })) || { count: 0, window: now };
    if (now - rl.window > 60000) { rl.count = 0; rl.window = now; }
    rl.count++;
    await rlStore.setJSON(rateLimitKey, rl);
    if (rl.count > 20) {
      return { statusCode: 429, headers: CORS, body: JSON.stringify({ error: 'Too many requests' }) };
    }
  } catch(e) { /* rate limit failure is non-fatal */ }

  // ── GET: list all licenses + pending orders ────────────────────────────
  if (event.httpMethod === 'GET') {
    const db = await getDb(store);
    const licenses = Object.values(db.licenses).sort((a,b) => new Date(b.createdAt)-new Date(a.createdAt));
    const orders   = Object.values(db.orders).sort((a,b)   => new Date(b.createdAt)-new Date(a.createdAt));
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, licenses, orders }) };
  }

  let body = {};
  try { body = JSON.parse(event.body || '{}'); } catch {}
  const { action } = body;

  // ── POST generate ───────────────────────────────────────────────────────
  if (action === 'generate') {
    const { plan = 'lifetime', email = '', name = '', note = '' } = body;
    const key = generateKey();
    const db  = await getDb(store);

    db.licenses[key] = {
      key,
      plan,
      email,
      name,
      note,
      createdAt:         new Date().toISOString(),
      status:            'pending',   // pending → active → revoked
      activatedAt:       null,
      activatedDeviceId: null,
    };
    await saveDb(store, db);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, key, license: db.licenses[key] }) };
  }

  // ── POST revoke ─────────────────────────────────────────────────────────
  if (action === 'revoke') {
    const { key } = body;
    const db = await getDb(store);
    if (!db.licenses[key]) return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: 'Key not found' }) };
    db.licenses[key].status = 'revoked';
    db.licenses[key].revokedAt = new Date().toISOString();
    await saveDb(store, db);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };
  }

  // ── POST restore (un-revoke) ────────────────────────────────────────────
  if (action === 'restore') {
    const { key } = body;
    const db = await getDb(store);
    if (!db.licenses[key]) return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: 'Key not found' }) };
    db.licenses[key].status = db.licenses[key].activatedAt ? 'active' : 'pending';
    delete db.licenses[key].revokedAt;
    await saveDb(store, db);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };
  }

  // ── POST reset-device — allows legitimate user to re-activate on new device ──
  if (action === 'reset-device') {
    const { key, reason = '' } = body;
    const db = await getDb(store);
    if (!db.licenses[key]) return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: 'Key not found' }) };
    const lic = db.licenses[key];
    if (lic.status === 'revoked') return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'Cannot reset revoked key' }) };
    lic.activatedDeviceId = null;
    lic.activatedAt       = null;
    lic.status            = 'active'; // stays active, just unbound from device
    lic.deviceResetAt     = new Date().toISOString();
    lic.deviceResetReason = String(reason).slice(0, 200);
    db.licenses[key] = lic;
    await saveDb(store, db);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };
  }

  // ── POST fulfill — generate key + send to buyer + mark order done ─────
  // Called when owner clicks "Send key" next to a pending order in admin panel
  if (action === 'fulfill') {
    const { ref } = body;
    const db      = await getDb(store);
    const order   = db.orders[ref];
    if (!order) return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: 'Order not found' }) };
    if (order.status === 'fulfilled') return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, note: 'already fulfilled', key: order.licenseKey }) };

    const gmailUser  = process.env.GMAIL_USER || '';
    const gmailPass  = process.env.GMAIL_PASS || '';
    if (!gmailPass) return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: false, error: 'GMAIL_PASS not set' }) };

    // Generate the license key
    const key      = generateKey();
    const planSlug = (order.plan||'').toLowerCase().includes('lifetime') ? 'lifetime'
                   : (order.plan||'').toLowerCase().includes('річн')    ? 'yearly' : 'monthly';

    // Prepare license object — save to DB only AFTER email is sent successfully
    const licenseObj = {
      key, plan: planSlug, email: order.email, name: order.name,
      phone: order.phone||'', deviceId: order.deviceId||'',
      note: `Fulfilled order ${ref}`,
      createdAt: new Date().toISOString(), status: 'active',
      activatedAt: null, activatedDeviceId: null,
      sentAt: null, sentTo: order.email,
    };

    // Send key email to buyer
    const eKey  = escHtml(key);
    const eRef  = escHtml(ref);
    const eName = escHtml(order.name || '');
    const ePlan = escHtml(order.plan || '');
    const greet = eName ? `Привіт, <strong>${eName}</strong>!` : 'Вітаємо!';

    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
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
.steps{background:#161b22;border-radius:10px;padding:14px 20px;margin:12px 0;font-size:13px;color:#8b949e;line-height:2;}
.cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:20px 0 0;font-size:15px;}
.foot{text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">🔑 Ваш ліцензійний ключ</div>
    <h2>Оплату підтверджено!</h2>
    <p>${greet} Дякуємо! Ваш ліцензійний ключ для плану <strong style="color:#e6edf3;">${ePlan}</strong>:</p>
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
    <p style="font-size:12px;">🔒 Ключ прив'язується до вашого пристрою при першій активації.<br>Замовлення: <strong style="color:#e6edf3;">${eRef}</strong></p>
    <a href="https://t.me/Helgaslopp" class="cta">Потрібна допомога? @Helgaslopp</a>
  </div>
  <div class="foot">AXIS OS &mdash; <a href="https://t.me/Helgaslopp" style="color:#00d4ff;text-decoration:none;">@Helgaslopp</a></div>
</div></body></html>`;

    const transporter = nodemailer.createTransport({ service:'gmail', auth:{ user:gmailUser, pass:gmailPass } });
    await transporter.sendMail({
      from: `"AXIS OS" <${gmailUser}>`,
      to:   order.email,
      subject: `🔑 AXIS OS — Ваш ліцензійний ключ (${order.plan})`,
      html,
    });

    // Email sent successfully — NOW save license and mark order fulfilled
    licenseObj.sentAt            = new Date().toISOString();
    db.licenses[key]             = licenseObj;
    db.orders[ref].status        = 'fulfilled';
    db.orders[ref].licenseKey    = key;
    db.orders[ref].fulfilledAt   = new Date().toISOString();
    await saveDb(store, db);

    console.log(`[Fulfill] Key ${key} sent to ${order.email} for order ${ref}`);
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true, key }) };
  }

  // ── POST send (email key to buyer) ──────────────────────────────────────
  if (action === 'send') {
    const { key, toEmail, toName } = body;
    const gmailUser = process.env.GMAIL_USER || '';
    const gmailPass = process.env.GMAIL_PASS || '';
    if (!gmailPass) return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: false, error: 'GMAIL_PASS not set' }) };

    const db = await getDb(store);
    const lic = db.licenses[key];
    if (!lic) return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: 'Key not found' }) };

    const eKey  = escHtml(key);
    const eName = escHtml(toName || lic.name || '');
    const ePlan = escHtml(lic.plan);
    const greet = eName ? `Привіт, <strong>${eName}</strong>!` : 'Вітаємо!';

    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
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
.info{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:14px 20px;margin:12px 0;font-size:13px;color:#8b949e;}
.cta{display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:20px 0 0;font-size:15px;}
.foot{text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);}
</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⬡ AXIS OS</h1></div>
  <div class="body">
    <div class="badge">🔑 Ваш ліцензійний ключ</div>
    <h2>Оплату підтверджено!</h2>
    <p>${greet} Ваш ліцензійний ключ для плану <strong style="color:#e6edf3;">${ePlan}</strong>:</p>
    <div class="keybox">
      <div class="keytext">${eKey}</div>
    </div>
    <div class="info">
      📌 Щоб активувати: відкрийте AXIS OS → Налаштування → Ліцензія → введіть ключ<br>
      🔒 Ключ прив'язується до вашого пристрою при першій активації<br>
      ♾️ Збережіть цей лист — ключ не можна відновити
    </div>
    <a href="https://t.me/Helgaslopp" class="cta">Потрібна допомога? Telegram @Helgaslopp</a>
  </div>
  <div class="foot">AXIS OS &mdash; Підтримка: <a href="https://t.me/Helgaslopp" style="color:#00d4ff;text-decoration:none;">@Helgaslopp</a></div>
</div></body></html>`;

    const transporter = nodemailer.createTransport({ service: 'gmail', auth: { user: gmailUser, pass: gmailPass } });
    await transporter.sendMail({
      from: `"AXIS OS" <${gmailUser}>`,
      to: toEmail || lic.email,
      subject: `🔑 AXIS OS — Ваш ліцензійний ключ (${lic.plan})`,
      html
    });

    // Mark as sent
    db.licenses[key].sentAt = new Date().toISOString();
    db.licenses[key].sentTo = toEmail || lic.email;
    await saveDb(store, db);

    return { statusCode: 200, headers: CORS, body: JSON.stringify({ ok: true }) };
  }

  return { statusCode: 400, headers: CORS, body: JSON.stringify({ error: 'Unknown action' }) };
};
