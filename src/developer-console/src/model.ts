export type AnyRecord = Record<string, unknown>

const sensitive = /(?:api[_-]?key|token|secret|password|credential|authorization)/i

export function redact(value: unknown, key = ''): unknown {
  if (sensitive.test(key)) return value == null || value === '' ? value : '[redacted]'
  if (Array.isArray(value)) return value.map((item) => redact(item))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as AnyRecord).map(([name, item]) => [name, redact(item, name)]))
  }
  return value
}

export function json(value: unknown): string { return JSON.stringify(redact(value), null, 2) }

export function semanticProjection(detail: AnyRecord, analysis: AnyRecord | null, resources: AnyRecord | null): AnyRecord {
  const graph = (detail.graph as AnyRecord | undefined) ?? {}
  const cartridge = (detail.cartridge as AnyRecord | undefined) ?? {}
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph.edges) ? graph.edges : []
  const compatibility = (detail.compatibility as AnyRecord | undefined) ?? {}
  return {
    identity: { id: cartridge.id, name: cartridge.name, version: cartridge.version, protocol: (cartridge.root_flow as AnyRecord | undefined)?.protocol },
    topology: { node_count: nodes.length, edge_count: edges.length, entry: graph.entry ?? (cartridge.root_flow as AnyRecord | undefined)?.start, nodes, edges },
    contracts: (analysis?.contracts ?? analysis?.contract_projection ?? []),
    bindings: resources?.models ?? {},
    diagnostics: { compatibility: compatibility.summary ?? {}, findings: [...((compatibility.findings as unknown[]) ?? []), ...((analysis?.findings as unknown[]) ?? []), ...((resources?.findings as unknown[]) ?? [])] },
  }
}

export function pathDiff(before: unknown, after: unknown, path = '$'): Array<{ path: string; before: unknown; after: unknown }> {
  if (JSON.stringify(before) === JSON.stringify(after)) return []
  if (!before || !after || typeof before !== 'object' || typeof after !== 'object' || Array.isArray(before) || Array.isArray(after)) return [{ path, before, after }]
  const left = before as AnyRecord; const right = after as AnyRecord
  return [...new Set([...Object.keys(left), ...Object.keys(right)])].flatMap((key) => pathDiff(left[key], right[key], `${path}.${key}`))
}
