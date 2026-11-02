'use strict';
const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { freePort, health } = require('./core');

test('freePort returns a usable port', async () => {
  const p = await freePort(0);
  assert.ok(p > 0 && p < 65536);
});

test('health recognises a Metachlorian core and rejects other servers', async () => {
  const srv = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(req.url === '/api/health' ? { name: 'metachlorian', version: 'x' } : {}));
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${srv.address().port}`;
  assert.ok(await health(url));
  srv.close();
  assert.equal(await health('http://127.0.0.1:1'), null);
});

test('occupied ports are rejected rather than silently changing the endpoint', async () => {
  const srv = http.createServer();
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  try { await assert.rejects(freePort(srv.address().port), /occupied/); }
  finally { srv.close(); }
});

test('startup reuses only the same library on the fixed endpoint', async () => {
  const { startSoloCore } = require('./core');
  const fs = require('node:fs');
  const path = require('node:path');
  const dataDir = fs.realpathSync(process.cwd());
  const normalized = process.platform === 'win32' ? dataDir.toLowerCase() : dataDir;
  const library_id = require('node:crypto').createHash('sha256').update(normalized).digest('hex');
  const srv = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ name: 'metachlorian', library_id }));
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  try {
    const port = srv.address().port;
    assert.equal((await startSoloCore({ dataDir, port })).reused, true);
    await assert.rejects(startSoloCore({ dataDir: path.join(dataDir, 'different'), port }), /different or older/);
  } finally { srv.close(); }
});
