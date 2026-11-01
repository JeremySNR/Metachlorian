/**
 * One version for everything Metachlorian ships: the Python core, the web app,
 * the desktop app and the Docker image all carry the same number.
 *
 *   node scripts/version.mjs            print it; fail if the files disagree
 *   node scripts/version.mjs 0.2.0      set it everywhere and turn
 *                                       "## [Unreleased]" into "## [0.2.0] - <today>"
 *
 * Commit the result as "Release v0.2.0" to publish (see CONTRIBUTING.md).
 */
import { readFileSync, writeFileSync } from 'node:fs'

const root = new URL('../', import.meta.url)
const read = (p) => readFileSync(new URL(p, root), 'utf8')
const write = (p, text) => writeFileSync(new URL(p, root), text)

// Each entry reads the version from a file and can rewrite it.
const regexFile = (path, re) => ({
  path,
  get: () => read(path).match(re)?.[2],
  set: (v) => write(path, read(path).replace(re, `$1${v}$3`))
})
const jsonFile = (path, lock) => ({
  path,
  get: () => JSON.parse(read(path)).version,
  set: (v) => {
    const data = JSON.parse(read(path))
    data.version = v
    if (lock && data.packages?.['']) data.packages[''].version = v
    write(path, JSON.stringify(data, null, 2) + '\n')
  }
})
const files = [
  regexFile('core/pyproject.toml', /^(version = ")([^"]+)(")/m),
  regexFile('core/metachlorian/__init__.py', /^(__version__ = ")([^"]+)(")/m),
  jsonFile('app/package.json'),
  jsonFile('app/package-lock.json', true),
  jsonFile('desktop/package.json'),
  jsonFile('desktop/package-lock.json', true)
]

const next = process.argv[2]
if (!next) {
  const found = files.map((f) => [f.path, f.get()])
  const versions = new Set(found.map(([, v]) => v))
  if (versions.size !== 1) {
    console.error('Version mismatch:\n' + found.map(([p, v]) => `  ${p}: ${v}`).join('\n') + '\nRun: node scripts/version.mjs <version>')
    process.exit(1)
  }
  process.stdout.write([...versions][0])
  process.exit(0)
}

if (!/^[0-9]+\.[0-9]+\.[0-9]+$/.test(next)) {
  console.error(`Not a version: ${next} (expected x.y.z)`)
  process.exit(2)
}
for (const f of files) f.set(next)

const changelog = read('CHANGELOG.md')
const today = new Date().toISOString().slice(0, 10)
if (/^## \[Unreleased\]/m.test(changelog)) {
  write('CHANGELOG.md', changelog.replace(/^## \[Unreleased\].*$/m, `## [${next}] - ${today}`))
  console.log(`Set ${next} in ${files.length} files and dated the [Unreleased] notes.`)
} else {
  console.log(`Set ${next} in ${files.length} files. CHANGELOG.md has no [Unreleased] section; add "## [${next}] - ${today}" notes before releasing.`)
}
