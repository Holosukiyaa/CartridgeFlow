export function readLocalStorageWithMigration(key: string, legacyKeys: readonly string[] = []) {
  const current = window.localStorage.getItem(key)
  if (current !== null) return current
  for (const legacyKey of legacyKeys) {
    const legacyValue = window.localStorage.getItem(legacyKey)
    if (legacyValue === null) continue
    window.localStorage.setItem(key, legacyValue)
    window.localStorage.removeItem(legacyKey)
    return legacyValue
  }
  return null
}

export function readSessionStorageWithMigration(key: string, legacyKeys: readonly string[] = []) {
  const current = window.sessionStorage.getItem(key)
  if (current !== null) return current
  for (const legacyKey of legacyKeys) {
    const legacyValue = window.sessionStorage.getItem(legacyKey)
    if (legacyValue === null) continue
    window.sessionStorage.setItem(key, legacyValue)
    window.sessionStorage.removeItem(legacyKey)
    return legacyValue
  }
  return null
}
