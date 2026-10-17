// Panel "Detalle del XML" (Fase 3.5): el documento entero —líneas, impuestos y
// la factura a la que apunta una nota— que el Excel de la DIAN no trae.
// Vive en su propio composable, como los otros paneles de `load.vue` (D-092).
import { ref, type Ref } from 'vue'
import { rpc } from './useRpc'

export type ImpuestoXml = {
  tipo: string
  nombre: string | null
  base: string | null
  tarifa: string | null
  valor: string | null
  es_retencion: boolean
}

export type LineaXml = {
  numero: number
  descripcion: string | null
  cantidad: string | null
  valor_unitario: string | null
  total: string | null
  impuestos: ImpuestoXml[]
}

export type DocumentoXml = {
  cufe: string
  tipo: string
  numero: string | null
  fecha_emision: string | null
  emisor_nit: string | null
  emisor_nombre: string | null
  subtotal: string | null
  total_impuestos: string | null
  total: string | null
  lineas: LineaXml[]
  impuestos: ImpuestoXml[]
  referencias: { cufe_referido: string | null; numero_referido: string | null; motivo: string | null }[]
}

type Opciones = {
  dbPath: Ref<string>
  periodo: Ref<string | null>
  /** Leer XML nuevos cambia lo que V3 contrasta: hay que revalidar. */
  alLeer?: () => Promise<void>
}

export function useDetalleXml({ dbPath, periodo, alLeer }: Opciones) {
  const toast = useToast()

  const resumen = ref<{ con_xml: number; total: number; cufes: string[] } | null>(null)
  const abierto = ref(false)
  const leyendo = ref(false)
  const documento = ref<DocumentoXml | null>(null)
  const cufeAbierto = ref<string | null>(null)

  async function refrescar() {
    if (!dbPath.value || !periodo.value) return
    try {
      resumen.value = await rpc('documentos_del_mes', {
        db_path: dbPath.value, periodo: periodo.value,
      })
    } catch {
      // Que no se pueda contar no es un fallo que deba tapar la pantalla: el
      // panel simplemente no aparece.
      resumen.value = null
    }
  }

  async function leerXml() {
    if (leyendo.value || !dbPath.value || !periodo.value) return
    leyendo.value = true
    try {
      const r = await rpc<{ leidos: number; desde_cache: number; fallidos: number; errores: { archivo: string; error: string }[] }>(
        'indexar_xml', { db_path: dbPath.value, periodo: periodo.value },
      )
      await refrescar()
      if (r.fallidos) {
        // Decir cuál falló y por qué, no «hubo errores» (D-083).
        const primero = r.errores?.[0]
        toast.warn(
          `${r.leidos} leídos · ${r.fallidos} con problemas`,
          primero ? `${primero.archivo}: ${primero.error}` : '',
        )
      } else if (r.leidos === 0 && r.desde_cache === 0) {
        toast.info('No hay XML en la carpeta', 'Los XML llegan con el ZIP de cada documento del portal.')
      } else {
        toast.success(`${r.leidos + r.desde_cache} documentos leídos`,
          r.leidos ? `${r.leidos} nuevos.` : 'Ya estaban todos leídos.')
      }
      if (r.leidos && alLeer) await alLeer()
    } catch (e: any) {
      toast.error('No se pudieron leer los XML', e?.message || String(e))
    } finally {
      leyendo.value = false
    }
  }

  async function verDocumento(cufe: string) {
    if (cufeAbierto.value === cufe) {
      cufeAbierto.value = null
      documento.value = null
      return
    }
    cufeAbierto.value = cufe
    documento.value = null
    const r = await rpc<{ documento: DocumentoXml | null }>('documento_xml', {
      db_path: dbPath.value, cufe,
    })
    documento.value = r.documento
  }

  return { resumen, abierto, leyendo, documento, cufeAbierto, refrescar, leerXml, verDocumento }
}
