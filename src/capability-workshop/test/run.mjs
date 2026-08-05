import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('.', import.meta.url))
const testFiles = []

function collect(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const fullPath = join(directory, entry.name)
    if (entry.isDirectory()) collect(fullPath)
    else if (entry.isFile() && entry.name.endsWith('.test.ts')) testFiles.push(fullPath)
  }
}

collect(root)
if (!testFiles.length) throw new Error('No TypeScript test files were found.')
const result = spawnSync(process.execPath, ['--import', 'tsx', '--test', ...testFiles], { stdio: 'inherit' })
process.exit(result.status ?? 1)
