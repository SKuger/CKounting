// Definiciones de los tutoriales interactivos, indexadas por ruta. Cada paso apunta a un
// elemento con data-tour="…" en la vista correspondiente. Se lanzan desde el botón "?" del
// topbar (tour de la vista actual) o desde el hub de Ayuda (navega + arranca el tour).
import type { TourStep } from '~/composables/useTour'

export type TourDef = { id: string; label: string; description: string; icon: string; route: string; steps: TourStep[] }

export const TOURS: Record<string, TourDef> = {
  '/': {
    id: 'inicio',
    label: 'Inicio',
    description: 'Un vistazo a la pantalla de inicio y sus módulos.',
    icon: 'Home',
    route: '/',
    steps: [
      { title: '¡Bienvenido a Contab!', body: 'Esta es tu pantalla de inicio. Te muestro los módulos en unos pasos; puedes saltar cuando quieras.' },
      { target: '[data-tour="inicio-empresas"]', title: 'Empresas', body: 'Tus libros contables, uno por empresa. Aquí cargas los reportes de la DIAN y validas.' },
      { target: '[data-tour="inicio-dian"]', title: 'Consulta DIAN', body: 'Consulta el RUT de terceros a partir de sus NIT.' },
    ],
  },
  '/empresas': {
    id: 'empresas',
    label: 'Empresas',
    description: 'Crear una empresa y abrir su detalle.',
    icon: 'Building2',
    route: '/empresas',
    steps: [
      { target: '[data-tour="nueva-empresa"]', title: 'Crear una empresa', body: 'Cada empresa es un libro independiente. Créala con su NIT y razón social.' },
      { target: '[data-tour="empresas-lista"]', title: 'Tus empresas', body: 'Tus empresas aparecen en esta lista. Haz clic en una para abrir su detalle.' },
    ],
  },
  '/empresa': {
    id: 'empresa',
    label: 'Detalle de empresa',
    description: 'Crear meses y, dentro de cada uno, subir su Excel y elegir sus soportes.',
    icon: 'FolderOpen',
    route: '/empresa',
    steps: [
      { target: '[data-tour="empresa-crear-mes"]', title: 'Crea un mes', body: 'Cada mes es un ambiente independiente. Créalo eligiendo mes y año.' },
      { target: '[data-tour="empresa-periodos"]', title: 'Los meses', body: 'Dentro de cada mes: sube su Excel, elige su carpeta de soportes, valídalo y ábrelo. También puedes mover el Excel a otro mes o enviarlo a la papelera.' },
    ],
  },
  '/load': {
    id: 'carga',
    label: 'Revisar una carga',
    description: 'Validar, revisar los soportes del mes (con/sin CUFE), re-verificarlos, renombrarlos y exportar los faltantes.',
    icon: 'FileSearch',
    route: '/load',
    steps: [
      { target: '[data-tour="load-validar"]', title: 'Validar', body: 'Cruza el Excel del mes contra sus soportes y marca las filas que no cuadran (V1 soporte, V2 nota crédito, V3 tarifa de IVA).' },
      { target: '[data-tour="load-solo-nc"]', title: 'Solo no conformes', body: 'Filtra para ver únicamente las filas con problemas.' },
      { target: '[data-tour="load-soportes"]', title: 'Soportes del mes', body: 'Aquí ves cuántos PDFs de la carpeta del mes tienen CUFE y cuáles no. Ábrelo para ver la lista archivo por archivo con el CUFE encontrado. El botón «Re-verificar soportes» vuelve a leer los CUFE de la carpeta y refresca las validaciones SIN re-subir el Excel — úsalo si agregaste, corregiste o renombraste PDFs.' },
      { target: '[data-tour="load-renombrar"]', title: 'Renombrar soportes', body: 'Renombra los PDF del mes al patrón DD-MM_NIT_RAZÓN-SOCIAL_FACTURA, cruzando cada archivo con su fila del Excel por el CUFE. Primero muestra una vista previa; se renombran en la misma carpeta y se deja un manifiesto _renombrados.csv para revertir. Los PDF sin CUFE o que no cruzan se dejan intactos.' },
      { target: '[data-tour="load-exportar"]', title: 'Exportar', body: 'Genera el Excel de faltantes de soporte para trabajarlo aparte.' },
    ],
  },
  '/consulta-dian': {
    id: 'dian',
    label: 'Consulta DIAN',
    description: 'Abrir el navegador, conectarte y consultar terceros.',
    icon: 'FileSearch',
    route: '/consulta-dian',
    steps: [
      { target: '[data-tour="dian-abrir"]', title: 'Abrir el navegador', body: 'Abre un navegador dedicado para la DIAN con un clic. No necesitas usar la terminal.' },
      { target: '[data-tour="dian-verificar"]', title: 'Verificar conexión', body: 'Cuando la DIAN esté abierta y resuelto el «Soy humano», confirma la conexión aquí.' },
      { target: '[data-tour="dian-archivo"]', title: 'Sube tu Excel', body: 'Carga el Excel con los NIT de los terceros que quieres consultar.' },
      { target: '[data-tour="dian-consultar"]', title: 'Consultar', body: 'Inicia la consulta y descarga el resultado cuando termine.' },
    ],
  },
}

export const TOUR_LIST: TourDef[] = Object.values(TOURS)
