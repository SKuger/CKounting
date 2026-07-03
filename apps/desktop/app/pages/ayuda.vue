<script setup lang="ts">
import { LifeBuoy } from 'lucide-vue-next'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs'

const secciones = [
  { value: 'pasos', label: 'Primeros pasos' },
  { value: 'excel', label: 'Cargar Excel' },
  { value: 'soportes', label: 'Soportes por mes' },
  { value: 'validaciones', label: 'Validaciones' },
  { value: 'exportar', label: 'Exportar' },
  { value: 'dian', label: 'Consulta DIAN' },
  { value: 'faq', label: 'Preguntas frecuentes' },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-4xl flex-col gap-4">
    <div class="flex items-center gap-3">
      <span class="inline-flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        <LifeBuoy class="size-5" />
      </span>
      <div>
        <h1 class="font-heading text-2xl font-medium tracking-tight">Ayuda</h1>
        <p class="text-sm text-muted-foreground">Guía rápida para usar Contab, en palabras sencillas.</p>
      </div>
    </div>

    <Tabs default-value="pasos" class="gap-4">
      <TabsList class="flex h-auto flex-wrap justify-start gap-1">
        <TabsTrigger v-for="s in secciones" :key="s.value" :value="s.value">{{ s.label }}</TabsTrigger>
      </TabsList>

      <TabsContent value="pasos">
        <Card><CardContent class="prose-help">
          <h2>¿Cómo funciona Contab?</h2>
          <p>Contab te ayuda a revisar la contabilidad de <strong>varias empresas</strong>. Cada empresa es
            independiente: sus datos no se mezclan con los de otra.</p>
          <ol>
            <li><strong>Crea una empresa</strong> con su NIT y razón social (botón «Nueva empresa» en Inicio).</li>
            <li><strong>Elige el mes</strong> que vas a trabajar y <strong>carga el Excel</strong> que descargaste de la DIAN.</li>
            <li><strong>Indica la carpeta</strong> donde están los soportes (PDF) de ese mes.</li>
            <li><strong>Valida</strong>: Contab cruza el Excel contra los soportes y marca lo que no cuadra.</li>
            <li><strong>Exporta</strong> el Excel con las filas «no conformes» para revisarlas.</li>
          </ol>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="excel">
        <Card><CardContent class="prose-help">
          <h2>Cargar el Excel de la DIAN</h2>
          <p>Es el archivo <strong>.xlsx</strong> que descargas del portal de la DIAN con los documentos
            electrónicos del periodo. Contab respeta sus columnas tal cual (no las renombra).</p>
          <p>Cada fila se asocia automáticamente a un <strong>mes</strong> según su fecha de emisión, así que
            puedes cargar un archivo por mes y mantenerlos separados.</p>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="soportes">
        <Card><CardContent class="prose-help">
          <h2>Carpeta de soportes (por mes)</h2>
          <p>Los <strong>soportes</strong> son los PDF de las facturas que respaldan cada documento del Excel.
            En Contab, <strong>cada mes tiene su propia carpeta</strong> de soportes.</p>
          <p>Eliges la carpeta desde la pantalla de la empresa; Contab lista los PDF automáticamente —no
            necesitas escribir rutas— y los revisa cuando validas.</p>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="validaciones">
        <Card><CardContent class="prose-help">
          <h2>Las validaciones (V1, V2, V3)</h2>
          <p>Al validar un mes, Contab aplica tres revisiones:</p>
          <ul>
            <li><strong>V1 — Soporte del CUFE.</strong> El <em>CUFE</em> es el código único que identifica cada
              factura electrónica. V1 confirma que el CUFE de cada fila aparezca en algún PDF de la carpeta del mes.</li>
            <li><strong>V2 — Notas crédito.</strong> Ajusta el signo de las notas crédito para que resten, no sumen.</li>
            <li><strong>V3 — Tarifa de IVA.</strong> Revisa que el IVA corresponda a una tarifa válida (0 %, 5 % o 19 %).</li>
          </ul>
          <p>Las filas que no pasan quedan marcadas como <strong>«no conformes»</strong>: son las que debes revisar.</p>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="exportar">
        <Card><CardContent class="prose-help">
          <h2>Exportar resultados</h2>
          <p>Contab genera un Excel con las <strong>filas no conformes</strong> (más el motivo de la falla) para que
            las trabajes aparte. También puede exportar las que <strong>faltan de soporte</strong>.</p>
          <p>El archivo conserva las columnas originales de la DIAN, así lo comparas fácil con el reporte que ya conoces.</p>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="dian">
        <Card><CardContent class="prose-help">
          <h2>Consulta DIAN (terceros)</h2>
          <p>En «Consulta DIAN» subes un Excel con NIT de terceros y Contab consulta el RUT de cada uno.</p>
          <p>Para máxima efectividad, usa el botón <strong>«Abrir navegador para la DIAN»</strong>: abre un navegador
            dedicado, entras a la DIAN, resuelves el «Soy humano» y dejas la ventana abierta. No necesitas escribir
            comandos en ninguna consola.</p>
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="faq">
        <Card><CardContent class="prose-help">
          <h2>Preguntas frecuentes</h2>
          <p><strong>¿Se pierden mis datos al cerrar el programa?</strong><br>No. Tu usuario y tus empresas quedan
            guardados y siguen ahí la próxima vez que abras Contab.</p>
          <p><strong>¿Qué es la papelera?</strong><br>Cuando envías filas o cargas a la papelera, dejan de verse pero
            no se borran: puedes restaurarlas cuando quieras.</p>
          <p><strong>¿Qué es el NIT y el DV?</strong><br>El NIT identifica a la empresa; el DV es el dígito de
            verificación que Contab calcula por ti.</p>
          <p><strong>¿Puedo mover un documento de mes?</strong><br>Sí. Si un documento quedó en el mes equivocado,
            puedes moverlo al mes correcto desde la vista de la carga.</p>
        </CardContent></Card>
      </TabsContent>
    </Tabs>
  </div>
</template>

<style scoped>
.prose-help :deep(h2) { font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; }
.prose-help :deep(p) { margin-bottom: 0.6rem; line-height: 1.6; }
.prose-help :deep(p:last-child) { margin-bottom: 0; }
.prose-help :deep(ol), .prose-help :deep(ul) { margin: 0.3rem 0 0.6rem; padding-left: 1.2rem; display: flex; flex-direction: column; gap: 0.35rem; }
.prose-help :deep(ol) { list-style: decimal; }
.prose-help :deep(ul) { list-style: disc; }
.prose-help :deep(li) { line-height: 1.5; }
.prose-help :deep(em) { font-style: italic; }
</style>
