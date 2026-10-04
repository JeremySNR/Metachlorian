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
