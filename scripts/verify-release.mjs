// Refuse to publish an incomplete release or a manifest pointing at bad bytes.
//
//   node scripts/verify-release.mjs <dir>                     local files match the latest*.yml manifests
//   node scripts/verify-release.mjs <dir> uploaded-release.json  ...and so do the assets GitHub holds
//
// Runs after `npm ci` in desktop/, whose electron-builder brings js-yaml.
import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import { basename, join } from 'node:path'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'

const require = createRequire(new URL('../desktop/package.json', import.meta.url))
const yaml = require('js-yaml')
const version = execFileSync(process.execPath, [new URL('version.mjs', import.meta.url).pathname], { encoding: 'utf8' })
const directory = process.argv[2] ?? 'release'
const uploaded = process.argv[3] ? JSON.parse(await readFile(process.argv[3], 'utf8')).assets : null
if (process.argv[3] && !Array.isArray(uploaded)) throw new Error('Missing uploaded asset metadata')

// Each platform's update manifest and the installer types it must list.
const expected = {
  'latest-mac.yml': ['.dmg', '.zip'],
  'latest.yml': ['.exe'],
  'latest-linux.yml': ['.AppImage']
}
let count = 0
for (const [manifest, kinds] of Object.entries(expected)) {
  const data = yaml.load(await readFile(join(directory, manifest), 'utf8'))
  if (data.version !== version || !Array.isArray(data.files)) throw new Error(`Invalid ${manifest} (expected version ${version})`)
  for (const kind of kinds) {
    if (!data.files.some((file) => file.url.endsWith(kind) && file.url.includes(version))) throw new Error(`${manifest} lists no ${kind} for ${version}`)
  }
  for (const file of data.files) {
    if (typeof file.url !== 'string' || basename(file.url) !== file.url) throw new Error(`Invalid asset in ${manifest}`)
    const path = join(directory, file.url)
    if ((await stat(path)).size !== file.size) throw new Error(`Incorrect size: ${file.url}`)
    const hash = createHash('sha512')
    const sha256 = createHash('sha256')
    for await (const chunk of createReadStream(path)) { hash.update(chunk); sha256.update(chunk) }
    if (hash.digest('base64') !== file.sha512) throw new Error(`Incorrect checksum: ${file.url}`)
    if (uploaded) {
      const remote = uploaded.find((asset) => asset.name === file.url)
      if (!remote || remote.state !== 'uploaded' || remote.size !== file.size ||
          remote.digest !== `sha256:${sha256.digest('hex')}`) throw new Error(`Upload not verified: ${file.url}`)
    }
    count++
  }
}
console.log(`All v${version} installers (${count}) and update manifests verified${uploaded ? ' on GitHub' : ''}.`)
