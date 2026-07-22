const PASSIVE_CSP = "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; media-src data: blob:; form-action 'none'; base-uri 'none'; frame-src 'none'"

export function passiveHtmlDocument(content: string) {
  const policy = `<meta http-equiv="Content-Security-Policy" content="${PASSIVE_CSP}">`
  if (/<head(?:\s[^>]*)?>/i.test(content)) {
    return content.replace(/<head(?:\s[^>]*)?>/i, (head) => `${head}${policy}`)
  }
  return `<!doctype html><html><head>${policy}<meta charset="utf-8"></head><body>${content}</body></html>`
}
