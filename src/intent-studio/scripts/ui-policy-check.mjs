#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const rootArgument = process.argv.indexOf('--root')
const packageRoot = rootArgument >= 0 ? resolve(process.argv[rootArgument + 1]) : join(fileURLToPath(new URL('.', import.meta.url)), '..')
const sourceRoot = join(packageRoot, 'src')
const policyPath = join(packageRoot, 'ui-policy.json')
const policy = JSON.parse(readFileSync(policyPath, 'utf8'))
const failures = []
const notes = []

function check(ok, message) {
  ;(ok ? notes : failures).push(`  ${ok ? 'PASS' : 'FAIL'} ${message}`)
}

function filesUnder(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const fullPath = join(directory, entry)
    return statSync(fullPath).isDirectory() ? filesUnder(fullPath) : [fullPath]
  })
}

function relativePackagePath(file) {
  return relative(packageRoot, file).replaceAll('\\', '/')
}

function parseSource(file) {
  const content = readFileSync(file, 'utf8')
  const sourceFile = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : file.endsWith('.jsx') ? ts.ScriptKind.JSX : file.endsWith('.ts') ? ts.ScriptKind.TS : ts.ScriptKind.JS,
  )
  const counts = Object.fromEntries(policy.nativeControls.map((tag) => [tag, 0]))
  counts.inlineStyle = 0
  const forbiddenImports = []

  function recordModule(moduleName) {
    const forbidden = policy.forbiddenDirectImports.some((prefix) => moduleName === prefix || moduleName.startsWith(prefix))
    const external = !moduleName.startsWith('.')
    const approved = policy.allowedPagePackages.some((name) => moduleName === name || moduleName.startsWith(`${name}/`))
    if (forbidden || (external && !approved)) {
      forbiddenImports.push(moduleName)
    }
  }

  function visit(node) {
    if (ts.isJsxElement(node)) {
      const tag = node.openingElement.tagName.getText()
      if (Object.hasOwn(counts, tag)) counts[tag] += 1
    }
    if (ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText()
      if (Object.hasOwn(counts, tag)) counts[tag] += 1
    }
    if (ts.isJsxAttribute(node) && node.name.text === 'style') counts.inlineStyle += 1
    if (ts.isImportDeclaration(node)) {
      recordModule(String(node.moduleSpecifier.text))
    }
    if (ts.isCallExpression(node) && node.arguments.length) {
      const firstArgument = node.arguments[0]
      if (ts.isStringLiteral(firstArgument)) {
        const expression = node.expression.getText()
        if ((expression === 'createElement' || expression === 'React.createElement') && Object.hasOwn(counts, firstArgument.text)) {
          counts[firstArgument.text] += 1
        }
        if (expression === 'require' || node.expression.kind === ts.SyntaxKind.ImportKeyword) {
          recordModule(firstArgument.text)
        }
      }
    }
    ts.forEachChild(node, visit)
  }

  visit(sourceFile)
  return { counts, forbiddenImports }
}

function totalNative(counts) {
  return policy.nativeControls.reduce((sum, tag) => sum + counts[tag], 0)
}

check(policy.schema === 'cartridgeflow.intent-studio-ui-policy.v1', 'UI policy schema is current')
check(existsSync(join(packageRoot, policy.publicUiEntry)), `public UI entry exists: ${policy.publicUiEntry}`)

const sourceFiles = filesUnder(sourceRoot)
const restrictedFiles = sourceFiles.filter((file) => relativePackagePath(file).startsWith(policy.restrictedSourcePrefix))
for (const file of restrictedFiles.filter((candidate) => /\.(tsx|ts|jsx|js)$/.test(candidate))) {
  const path = relativePackagePath(file)
  const { counts, forbiddenImports } = parseSource(file)
  const baseline = policy.legacyNativeBaseline[path]
  const native = totalNative(counts)
  if (!baseline) {
    check(native === 0, `${path} has no unregistered native controls (${native})`)
    check(counts.inlineStyle === 0, `${path} has no inline visual styles`)
  } else {
    for (const tag of policy.nativeControls) {
      check(counts[tag] <= (baseline[tag] || 0), `${path} ${tag} count does not increase (${counts[tag]} <= ${baseline[tag] || 0})`)
    }
    check(counts.inlineStyle <= (baseline.inlineStyle || 0), `${path} inline style count does not increase (${counts.inlineStyle} <= ${baseline.inlineStyle || 0})`)
  }
  check(forbiddenImports.length === 0, `${path} does not bypass the local UI boundary${forbiddenImports.length ? `: ${[...new Set(forbiddenImports)].join(', ')}` : ''}`)
}

const cssFiles = sourceFiles.filter((file) => file.endsWith('.css'))
const allowedCss = new Set(policy.css.allowedFiles)
for (const file of cssFiles) {
  const path = relativePackagePath(file)
  const content = readFileSync(file, 'utf8')
  const baseline = policy.css.baseline[path]
  check(allowedCss.has(path), `${path} is an approved stylesheet location`)
  check(Boolean(baseline), `${path} has a CSS ratchet baseline`)
  if (baseline) {
    const lines = content.split(/\r?\n/).length
    const mediaQueries = (content.match(/@media\b/g) || []).length
    const hardcodedColors = (content.match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\s*\(/g) || []).length
    const bytes = Buffer.byteLength(content, 'utf8')
    check(bytes <= baseline.bytes, `${path} byte count does not increase (${bytes} <= ${baseline.bytes})`)
    check(lines <= baseline.lines, `${path} line count does not increase (${lines} <= ${baseline.lines})`)
    check(mediaQueries <= baseline.mediaQueries, `${path} media query count does not increase (${mediaQueries} <= ${baseline.mediaQueries})`)
    check(hardcodedColors <= baseline.hardcodedColors, `${path} hardcoded color count does not increase (${hardcodedColors} <= ${baseline.hardcodedColors})`)
  }
  for (const token of policy.css.forbiddenTokens) check(!content.includes(token), `${path} does not contain forbidden CSS token ${token}`)
}

check(cssFiles.length <= allowedCss.size, `stylesheet count stays within the approved surface (${cssFiles.length} <= ${allowedCss.size})`)

console.log('=== Intent Studio UI policy ===')
for (const note of notes) console.log(note)
if (failures.length) {
  console.log(`\n${failures.length} failure(s):`)
  for (const failure of failures) console.log(failure)
}
process.exitCode = failures.length ? 1 : 0
