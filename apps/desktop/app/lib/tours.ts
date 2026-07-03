// Definiciones de los tutoriales interactivos, indexadas por ruta. Cada paso apunta a un
// elemento con data-tour="…" en la vista correspondiente. Se lanzan desde el botón "?" del
// topbar (tour de la vista actual) o desde el hub de Ayuda (navega + arranca el tour).
import type { TourStep } from '~/composables/useTour'

export type TourDef = { id: string; label: string; description: string; icon: string; route: string; steps: TourStep[] }

export const TOURS: Record<string, TourDef> = {
  '/': {
    id: 'empresas',
    label: 'Empresas (inicio)',
    description: 'Crear tu primera empresa y moverte por la pantalla principal.',
    icon: 'Building2',
    route: '/',
    steps: [
      { title: '¡Bienvenido a Contab!', body: 'Te muestro lo esencial en unos pasos. Puedes saltar el tutorial cuando quieras.' },
      { target: '[data-tour="nueva-empresa"]', title: 'Crear una empresa', body: 'Cada empresa es un libro independiente. Empieza aquí, con su NIT y razón social.' },
      { target: '[data-tour="empresas-lista"]', title: 'Tus empresas', body: 'Tus empresas aparecen en esta lista. Haz clic en una para abrir su detalle.' },
      { target: '[data-tour="consulta-dian"]', title: 'Consulta DIAN', body: 'Desde aquí consultas el RUT de terceros a partir de sus NIT.' },
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
    description: 'Validar, filtrar no conformes y exportar.',
    icon: 'FileSearch',
    route: '/load',
    steps: [
      { target: '[data-tour="load-validar"]', title: 'Validar', body: 'Cruza el Excel del mes contra sus soportes y marca las filas que no cuadran.' },
      { target: '[data-tour="load-solo-nc"]', title: 'Solo no conformes', body: 'Filtra para ver únicamente las filas con problemas.' },
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
