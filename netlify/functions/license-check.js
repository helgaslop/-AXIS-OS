// AXIS OS — License Validation (public endpoint, called by AXIS OS app)
// POST { key, deviceId }
//   → { valid: true,  plan: 'monthly'|'yearly'|'lifetime', name: '...' }
//   → { valid: false, error: '...' }

const { getStore } = require('@netlify/blobs');

const CORS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json'
};

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS, body: '' };
  if (event.httpMethod !== 'POST')    return { statusCode: 405, headers: CORS, body: 'Method Not Allowed' };

  let body = {};
  try { body = JSON.parse(event.body || '{}'); } catch {}

  const { key = '', deviceId = '' } = body;

  // Basic format check — AXIS-XXXX-XXXX-XXXX-XXXX
  if (!/^AXIS-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(key)) {
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ valid: false, error: 'Невірний формат ключа' }) };
  }

  const store = getStore('axis-licenses');
  const db    = (await store.get('db', { type: 'json' })) || { licenses: {} };
  const lic   = db.licenses[key];

  if (!lic) {
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ valid: false, error: 'Ключ не знайдено' }) };
  }
  if (lic.status === 'revoked') {
    return { statusCode: 200, headers: CORS, body: JSON.stringify({ valid: false, error: 'Ключ відкликано' }) };
  }

  // Require valid deviceId for non-lifetime plans
  if (lic.plan !== 'lifetime' && !deviceId) {
    return { statusCode: 200, headers: CORS,
      body: JSON.stringify({ valid: false, error: 'Ідентифікатор пристрою обовʼязковий' }) };
  }

  // First activation — bind to device
  if (lic.status === 'pending') {
    lic.status            = 'active';
    lic.activatedAt       = new Date().toISOString();
    lic.activatedDeviceId = deviceId;
    db.licenses[key]      = lic;
    await store.setJSON('db', db);
  }

  // Device check — Lifetime plan is not device-locked
  if (lic.plan !== 'lifetime' && lic.activatedDeviceId && deviceId && lic.activatedDeviceId !== deviceId) {
    return {
      statusCode: 200, headers: CORS,
      body: JSON.stringify({ valid: false, error: 'Ключ прив\'язаний до іншого пристрою. Зверніться до підтримки.' })
    };
  }

  return {
    statusCode: 200, headers: CORS,
    body: JSON.stringify({ valid: true, plan: lic.plan, name: lic.name || '' })
  };
};
