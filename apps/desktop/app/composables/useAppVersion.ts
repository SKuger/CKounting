// Live app version (= the installed release). Fetched once from /api/version (which reads
// CONTAB_VERSION injected by the Electron shell) and cached in shared state.
export function useAppVersion() {
  const version = useState<string>('app-version', () => '')
  if (import.meta.client && !version.value) {
    $fetch<{ version: string }>('/api/version')
      .then((r) => { version.value = r.version })
      .catch(() => {})
  }
  return version
}
