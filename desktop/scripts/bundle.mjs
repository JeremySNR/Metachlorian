/**
 * Builds everything the desktop app ships alongside Electron, for the platform
 * it runs on, into desktop/bundle/ (packaged as Resources/{python,app,ffmpeg}):
 *
 *   python/   a relocatable CPython 3.11 (python-build-standalone, via uv) with
 *             the core and its analysis dependencies installed into it
 *   app/      the built web app (app/dist), which the core serves
 *   ffmpeg/   static ffmpeg + ffprobe builds (ffmpeg-static's release assets)
 *
 * Needs uv on PATH and app/dist built (`cd app && npm run build`).
 * Usage: node scripts/bundle.mjs        (from desktop/; `npm run bundle`)
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { chmodSync, cpSync, createWriteStream, existsSync, mkdirSync, readdirSync, realpathSync, rmSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { Readable } from 'node:stream'
import { createGunzip } from 'node:zlib'

const desktop = resolve(import.meta.dirname, '..')
const repo = resolve(desktop, '..')
const out = join(desktop, 'bundle')
const win = process.platform === 'win32'
const PYTHON = '3.11'
// ffmpeg-static's GitHub release with prebuilt binaries per platform (GPL builds; licences are copied alongside).
const FFMPEG_RELEASE = 'https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1'

const run = (cmd, args, opts = {}) => execFileSync(cmd, args, { stdio: 'inherit', ...opts })
const step = (msg) => console.log(`\n▸ ${msg}`)

rmSync(out, { recursive: true, force: true })
mkdirSync(out, { recursive: true })

// ---------------------------------------------------------------- python + core
step(`CPython ${PYTHON} (standalone)`)
const cache = join(desktop, '.cache', 'python')
run('uv', ['python', 'install', PYTHON, '--install-dir', cache])
// uv adds a minor-version alias next to the real install; copy the real directory.
const installs = readdirSync(cache).filter((d) => d.startsWith(`cpython-${PYTHON}.`))
if (!installs.length) throw new Error(`uv did not install CPython ${PYTHON} into ${cache}`)
const pythonHome = join(out, 'python')
cpSync(realpathSync(join(cache, installs.sort().at(-1))), pythonHome, { recursive: true, verbatimSymlinks: true })
const python = win ? join(pythonHome, 'python.exe') : join(pythonHome, 'bin', 'python3')
// uv marks its interpreters externally managed; this copy is ours to install into.
rmSync(join(pythonHome, win ? 'Lib' : `lib/python${PYTHON}`, 'EXTERNALLY-MANAGED'), { force: true })

step('Metachlorian core and analysis dependencies')
run('uv', ['pip', 'install', '--python', python, '--no-cache', `${join(repo, 'core')}[analysis]`])
// Precompile so the read-only (and, on macOS, signed) bundle is never written to at runtime. A few files in the
// standard library and in dependencies' test data aren't valid Python 3.11 and fail to compile; that is expected,
// so list them rather than failing the build.
const compiled = spawnSync(python, ['-m', 'compileall', '-q', '-j', '0', pythonHome], { encoding: 'utf8' })
if (compiled.error) throw compiled.error
const failed = (compiled.stdout || '').split(/\r?\n/).filter((l) => /^\*\*\* Error compiling/.test(l))
if (failed.length) console.log(`  (${failed.length} file(s) not precompiled: ${failed.slice(0, 5).map((l) => l.replace(/^\*\*\* Error compiling /, '')).join(', ')}${failed.length > 5 ? ', …' : ''})`)
run(python, ['-c', 'import metachlorian, onnxruntime, cv2, sherpa_onnx, usearch; print("core", metachlorian.__version__, "imports ok")'])

// ---------------------------------------------------------------- web app
step('Web app')
const dist = join(repo, 'app', 'dist')
if (!existsSync(join(dist, 'index.html'))) throw new Error('app/dist is missing: run `npm run build` in app/ first')
cpSync(dist, join(out, 'app'), { recursive: true })

// ---------------------------------------------------------------- ffmpeg
step('FFmpeg')
const target = { darwin: 'darwin', win32: 'win32', linux: 'linux' }[process.platform] + '-' + process.arch
mkdirSync(join(out, 'ffmpeg'), { recursive: true })
async function download(name, dest, gz) {
  const r = await fetch(`${FFMPEG_RELEASE}/${name}`)
  if (!r.ok) throw new Error(`Download failed (${r.status}): ${FFMPEG_RELEASE}/${name}`)
  const body = Readable.fromWeb(r.body)
  await (gz ? pipeline(body, createGunzip(), createWriteStream(dest)) : pipeline(body, createWriteStream(dest)))
}
for (const tool of ['ffmpeg', 'ffprobe']) {
  const dest = join(out, 'ffmpeg', tool + (win ? '.exe' : ''))
  await download(`${tool}-${target}.gz`, dest, true)
  chmodSync(dest, 0o755)
  run(dest, ['-hide_banner', '-version'], { stdio: ['ignore', 'ignore', 'inherit'] })
}
await download(`${target}.LICENSE`, join(out, 'ffmpeg', 'LICENSE'), false)
await download(`${target}.README`, join(out, 'ffmpeg', 'README'), false)

console.log(`\nBundle ready in ${out}`)
