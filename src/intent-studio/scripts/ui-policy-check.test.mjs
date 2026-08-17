import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const checker = fileURLToPath(new URL('./ui-policy-check.mjs', import.meta.url))

function write(root, path, content) {
  const target = join(root, path)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, content, 'utf8')
}

function createFixture() {
  const root = mkdtempSync(join(tmpdir(), 'intent-ui-policy-'))
  write(root, 'src/ui/index.ts', 'export const Button = "approved"\n')
  write(root, 'src/pages/Existing.tsx', 'export const Existing = () => <button type="button">legacy</button>\n')
  write(root, 'src/pages/Clean.tsx', 'import { Button } from "../ui/index.ts"\nexport const Clean = () => <Button />\n')
  write(root, 'src/styles/app.css', ':root { --surface: #fff; }\n')
  write(root, 'ui-policy.json', JSON.stringify({
    schema: 'cartridgeflow.intent-studio-ui-policy.v1',
    publicUiEntry: 'src/ui/index.ts',
    restrictedSourcePrefix: 'src/pages/',
    forbiddenDirectImports: ['@mantine/', 'allotment'],
    allowedPagePackages: ['react', 'lucide-react', '@dagrejs/dagre', '@xyflow/react'],
    nativeControls: ['button', 'input', 'textarea', 'select', 'dialog'],
    legacyNativeBaseline: {
      'src/pages/Existing.tsx': { button: 1, input: 0, textarea: 0, select: 0, dialog: 0, inlineStyle: 0 },
    },
    css: {
      allowedFiles: ['src/styles/app.css'],
      baseline: { 'src/styles/app.css': { bytes: 28, lines: 2, mediaQueries: 0, hardcodedColors: 1 } },
      forbiddenTokens: ['!important', 'box-shadow', 'transform:'],
    },
  }, null, 2))
  return root
}

function run(root) {
  return spawnSync(process.execPath, [checker, '--root', root], { encoding: 'utf8' })
}

test('accepts the approved entry and unchanged legacy baseline', (context) => {
  const root = createFixture()
  context.after(() => rmSync(root, { recursive: true, force: true }))
  assert.equal(run(root).status, 0)
})

test('rejects new native controls and direct framework imports', (context) => {
  const root = createFixture()
  context.after(() => rmSync(root, { recursive: true, force: true }))
  write(root, 'src/pages/Clean.jsx', "const load = () => import('@mantine/core')\nexport const Clean = () => <>{React.createElement('input')}<button style={{ color: 'red' }}>new</button></>\n")
  const result = run(root)
  assert.notEqual(result.status, 0)
  assert.match(result.stdout, /unregistered native controls/)
  assert.match(result.stdout, /inline visual styles/)
  assert.match(result.stdout, /does not bypass the local UI boundary/)
})

test('rejects an unapproved stylesheet', (context) => {
  const root = createFixture()
  context.after(() => rmSync(root, { recursive: true, force: true }))
  write(root, 'src/pages/local.css', '.ad-hoc { color: red; }\n')
  const result = run(root)
  assert.notEqual(result.status, 0)
  assert.match(result.stdout, /approved stylesheet location/)
})

test('rejects growth inside an approved stylesheet', (context) => {
  const root = createFixture()
  context.after(() => rmSync(root, { recursive: true, force: true }))
  write(root, 'src/styles/app.css', ':root { --surface: #fff; color: rgb(1, 2, 3); }\n')
  const result = run(root)
  assert.notEqual(result.status, 0)
  assert.match(result.stdout, /byte count does not increase/)
  assert.match(result.stdout, /hardcoded color count does not increase/)
})
