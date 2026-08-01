export function resolveRunInputDefault(input: any): string {
  const runtimeDefault = input?.runtime_default
  if (runtimeDefault?.type === 'current_date') {
    const timeZone = typeof runtimeDefault.timezone === 'string' && runtimeDefault.timezone ? runtimeDefault.timezone : undefined
    try {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date())
      const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
      return `${values.year}-${values.month}-${values.day}`
    } catch {
      return new Date().toISOString().slice(0, 10)
    }
  }
  return input?.default === undefined || input?.default === null ? '' : String(input.default)
}
