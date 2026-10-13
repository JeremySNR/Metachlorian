/**
 * Checks a packaged desktop app works with nothing else installed: the bundled
 * Python runs the core, FFmpeg runs, the core serves the web app, a short clip
 * goes through analysis, and the Electron app starts and shows the library.
 *
 * Usage (from desktop/, after `electron-builder --dir`):
 *   node scripts/check-package.mjs [unpacked app dir] [--no-electron]
 * Defaults to release/mac-arm64, release/win-unpacked or release/linux-unpacked.
 * Model downloads are skipped (models: none); analysers needing them report "unavailable".
 */
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const desktop = resolve(import.meta.dirname, '..')
const win = process.platform === 'win32'
const mac = process.platform === 'darwin'
const appDir = resolve(process.argv.slice(2).find((a) => !a.startsWith('--')) ??
  join(desktop, 'release', mac ? 'mac-arm64' : win ? 'win-unpacked' : 'linux-unpacked'))
const resources = mac ? join(appDir, 'Metachlorian.app', 'Contents', 'Resources') : join(appDir, 'resources')
const electronExe = mac ? join(appDir, 'Metachlorian.app', 'Contents', 'MacOS', 'Metachlorian')
  : join(appDir, win ? 'Metachlorian.exe' : 'metachlorian-desktop')
const python = join(resources, 'python', win ? 'python.exe' : join('bin', 'python3'))
const ff = (tool) => join(resources, 'ffmpeg', tool + (win ? '.exe' : ''))
const work = mkdtempSync(join(tmpdir(), 'mc-package-check-'))
const env = {
  ...process.env, METACHLORIAN_APP_DIST: join(resources, 'app'), METACHLORIAN_FFMPEG: ff('ffmpeg'), METACHLORIAN_FFPROBE: ff('ffprobe'),
  PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1', METACHLORIAN_COMMUNITY_ENABLED: 'false',
}
delete env.PYTHONHOME
delete env.PYTHONPATH
const ok = (msg) => console.log(`✓ ${msg}`)
const core = (...args) => execFileSync(python, ['-m', 'metachlorian', '--data', join(work, 'lib'), ...args], { env, encoding: 'utf8' })

for (const p of [python, ff('ffmpeg'), ff('ffprobe'), join(resources, 'app', 'index.html'), electronExe]) {
  if (!existsSync(p)) throw new Error(`Missing from the package: ${p}`)
}
ok(`package contents (${appDir})`)

execFileSync(ff('ffmpeg'), ['-hide_banner', '-version'], { stdio: 'ignore' })
execFileSync(ff('ffprobe'), ['-hide_banner', '-version'], { stdio: 'ignore' })
ok('ffmpeg and ffprobe run')

const version = execFileSync(python, ['-c', 'import metachlorian, onnxruntime, cv2, sherpa_onnx, usearch, scenedetect; print(metachlorian.__version__)'], { env, encoding: 'utf8' }).trim()
ok(`bundled core ${version} and its native dependencies import`)

// A 6-second clip with a hard cut and a tone, analysed end to end.
const footage = join(work, 'footage')
mkdirSync(footage)
execFileSync(ff('ffmpeg'), ['-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=3',
  '-f', 'lavfi', '-i', 'smptebars=size=640x360:rate=25:duration=3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
  '-filter_complex', '[0:v][1:v]concat=n=2:v=1[v]', '-map', '[v]', '-map', '2:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
  join(footage, 'check.mp4')])
core('init')
core('add', footage)
core('process')
const status = core('status')
if (!/\b1\b/.test(status)) throw new Error(`Unexpected status after processing:\n${status}`)
const shots = execFileSync(python, ['-c', `import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from shots").fetchone()[0])`, join(work, 'lib', 'library.sqlite')], { env, encoding: 'utf8' }).trim()
if (Number(shots) < 2) throw new Error(`Expected the hard cut to give at least 2 shots, got ${shots}`)
ok(`a clip with a hard cut was analysed into ${shots} shots`)

// The core serves the API and the bundled web app.
const port = 18765 + Math.floor(Math.random() * 1000)
const server = spawn(python, ['-m', 'metachlorian', '--data', join(work, 'lib'), 'serve', '--host', '127.0.0.1', '--port', String(port)], { env, stdio: 'ignore' })
try {
  let health = null
  for (let i = 0; i < 300 && !health; i++) {
    await new Promise((r) => setTimeout(r, 400))
    health = await fetch(`http://127.0.0.1:${port}/api/health`).then((r) => r.ok ? r.json() : null).catch(() => null)
  }
  if (!health || health.version !== version) throw new Error(`Core did not answer /api/health on port ${port}`)
  const page = await fetch(`http://127.0.0.1:${port}/`).then((r) => r.text())
  if (!/<div id="root"|<script/i.test(page)) throw new Error('Core did not serve the web app')
  ok('core serves the API and the web app')
} finally {
  server.kill()
}

if (!process.argv.includes('--no-electron')) {
  const shot = join(work, 'smoke.png')
  // CI's Linux runners have no SUID sandbox helper or GPU; run it under xvfb-run there.
  const out = execFileSync(electronExe, process.platform === 'linux' ? ['--no-sandbox', '--disable-gpu'] : [], {
    env: { ...process.env, METACHLORIAN_DATA: join(work, 'lib'), METACHLORIAN_SKIP_MODEL_SETUP: '1', METACHLORIAN_COMMUNITY_ENABLED: 'false', METACHLORIAN_DESKTOP_SMOKE: shot },
    encoding: 'utf8', timeout: 240_000,
  })
  const result = out.split('\n').map((l) => { try { return JSON.parse(l) } catch { return null } }).find((r) => r && r.smoke)
  if (!result || result.smoke !== 'ok' || !result.bridge) throw new Error(`Desktop app smoke test failed:\n${out.slice(-2000)}`)
  ok(`desktop app started its bundled core and showed the library (screenshot: ${shot})`)
}
writeFileSync(join(work, 'ok'), version)
console.log(`\nPackage check passed (work dir ${work})`)
