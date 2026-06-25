type RpcResponse<T> = { ok: true; result: T } | { ok: false; error: string }

export async function rpc<T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const res = await $fetch<RpcResponse<T>>('/api/rpc', {
    method: 'POST',
    body: { method, params },
  })
  if (!res.ok) throw new Error(res.error)
  return res.result
}
