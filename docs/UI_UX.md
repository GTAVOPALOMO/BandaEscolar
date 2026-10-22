# Rediseño UI/UX — Banda Escolar Esquipulas

Aplicado localmente el 21 de octubre de 2026 a partir de `main`, commit `0170d88` (`Mejora visual`). El árbol de trabajo estaba limpio al iniciar. Se revisaron las plantillas, vistas, modelos, rutas, permisos, estilos, scripts y pruebas indicados en el documento maestro.

## Resultado

La portada abre con una cabecera compacta, la próxima actividad y la agenda. En teléfonos se presenta una lista cronológica con fecha, hora y lugar. Los enlaces **Lista / Mes**, **Anterior / Siguiente** y **Hoy** funcionan también sin JavaScript y conservan el mes y la vista seleccionados. En el mes móvil, cada día con actividades enlaza a su lista completa; en escritorio muestra los eventos dentro del calendario y una lista complementaria.

Se mantiene Django, las fuentes DM Sans/Fraunces y la paleta institucional. No se añadieron dependencias de ejecución ni cambios de infraestructura, configuración de producción, modelos o migraciones. Los únicos cambios en las vistas financieras son datos de presentación para botones, cancelación y explicaciones. Los servicios de negocio y los decoradores de permisos permanecen intactos.

## Decisiones y diferencias respecto del diagnóstico

- El repositorio actual sí conservaba el hero descrito. Se retiró de la portada; el archivo de ilustración permanece disponible y se conserva en el acceso, después del formulario en el DOM.
- `Event` tiene fecha y hora de **inicio**, pero no finalización. Se define «próximo» como inicio estrictamente posterior al instante actual de Costa Rica. Una actividad que ya empezó deja de aparecer en «próximos» y sigue disponible en su mes, con la etiqueta **Hora transcurrida**, sin afirmar que terminó.
- La misma consulta reutilizable se utiliza en portada y paneles de encargado/comité. El diagnóstico original del comité tampoco descartaba eventos de hoy cuya hora ya pasó; ahora ambos paneles usan la misma regla.
- El único criterio existente de publicación es `is_active`. Se respeta en agenda, próxima actividad, detalle e imagen. No se añadió un estado de publicación nuevo.
- Se escogieron enlaces normales para cambiar Lista/Mes, evitando pestañas simuladas y dependencia de JavaScript. El modo automático muestra la lista hasta 760 px; el calendario y la lista aparecen desde 761 px. La lista complementaria queda debajo del calendario hasta 1100 px y a su lado en escritorio amplio.
- El encabezado deja de ser fijo: mensajes, foco y contenido ampliado no quedan tapados. El menú móvil se puede cerrar con Escape y devuelve el foco; sin JavaScript los enlaces permanecen visibles. Administración utiliza `details/summary` nativos.
- Los campos HTML de fecha y hora ahora reciben valores ISO al editar. Esto evita que una fecha localizada aparezca vacía en un `input type="date"`; no cambia su validación.
- La vista previa de la venta utiliza el mismo formato CRC que los recibos y saldos existentes.

## Archivos y propósito

| Archivos | Cambio |
| --- | --- |
| `events/queries.py` (nuevo), `events/views.py`, `accounts/views.py` | Reloj local y consulta compartida de próximos eventos; estados del calendario, navegación y contextos de formularios. |
| `events/tests.py` | 15 pruebas adicionales de fechas/horas, zona horaria, visibilidad, meses, estados vacíos, permisos y formularios. |
| `templates/events/home.html` | Portada orientada a agenda, próxima actividad, lista/mes, hoy y calendario HTML semántico. |
| `templates/events/detail.html` | Nombre, fecha, hora y lugar antes de la imagen; retorno al mes del evento. |
| `templates/base.html` | Menú por rol, Administración, sección activa y destino del enlace para saltar al contenido. |
| `templates/accounts/guardian_dashboard.html`, `templates/accounts/staff_dashboard.html`, `templates/includes/upcoming_events.html` (nuevo) | Resumen por estudiante, indicadores operativos, acciones frecuentes y próximos eventos con estados vacíos. |
| `static/css/app.css` | Retirada del hero, estilos de agenda, textos legibles, foco, tamaños táctiles y adaptación de formularios, tablas y paneles. |
| `static/js/app.js` | Menú con teclado, Escape, recuperación de foco y estado de búsqueda de estudiantes. |
| `static/js/sale-form.js` | Formato de colones coherente con el filtro Django; mismo cálculo de precio y total. |
| `templates/generic_form.html`, `templates/confirm.html`, `templates/includes/form_fields.html` (nuevo) | Acciones contextuales, cancelación fija, errores asociados al campo y campos opcionales. |
| `students/views.py`, `dues/views.py`, `cash/views.py`, `tickets/views.py` | Solo etiquetas, destinos seguros de cancelación y explicaciones para acciones delicadas. |
| `events/forms.py`, `students/forms.py`, `accounts/forms.py`, `dues/forms.py` | Etiquetas en español, ayudas e ISO en widgets de fechas/horas; mismas reglas de validación. |
| `templates/registration/login.html`, `templates/registration/password_change.html` | Formulario y encabezado priorizados; errores/ayudas compartidos; conservación del destino de acceso. |
| `templates/students/form.html`, `templates/students/detail.html`, `templates/students/list.html` | Cancelación en matrícula, tablas navegables, búsqueda anunciada y enlace a la confirmación existente de desvinculación. |
| `templates/cash/home.html`, `templates/cash/close.html` | Consulta explícita del período sin envío automático al cambiar la selección, tabla accesible y cancelación del cierre. |
| `templates/tickets/sales.html`, `templates/tickets/sale_form.html`, `templates/tickets/scan.html` | Tabla, confirmaciones comprensibles, cancelación/retorno y estado de cámara anunciado. |
| `templates/dues/rates.html` | Presentación compartida de campos y errores. |
| `templates/events/manage.html`, `templates/accounts/user_list.html`, `templates/audit/list.html` | Regiones de tablas con nombre, foco para desplazamiento y encabezados de columna. |
| `README.md`, `docs/UI_UX.md`, `docs/ui-ux/*` | Informe, capturas y resultados verificables. |

## Pruebas ejecutadas

Los comandos Django se ejecutaron con este prefijo local, sin cambiar archivos de entorno ni usar credenciales de producción:

```bash
env -u DATABASE_URL -u VERCEL DEBUG=1 USE_SUPABASE_STORAGE=0 .venv/bin/python manage.py test --noinput
env -u DATABASE_URL -u VERCEL DEBUG=1 USE_SUPABASE_STORAGE=0 .venv/bin/python manage.py check
env -u DATABASE_URL -u VERCEL DEBUG=1 USE_SUPABASE_STORAGE=0 .venv/bin/python manage.py makemigrations --check --dry-run
node --check static/js/app.js
node --check static/js/sale-form.js
git diff --check
```

| Verificación | Resultado real |
| --- | --- |
| Suite inicial | 37 pruebas aprobadas, 32,818 s. |
| Suite final | **52 pruebas aprobadas**, 37,808 s; ninguna fallida. |
| Django `check` | `System check identified no issues (0 silenced).` |
| Migraciones pendientes | `No changes detected`. |
| Sintaxis JavaScript y whitespace del diff | Sin errores. |
| Chrome/Playwright: diseño y navegación | **56 comprobaciones aprobadas**, sin errores JavaScript. [Detalle](ui-ux/browser-results.json). |
| Chrome/Playwright: recorridos funcionales | **6 recorridos aprobados**. [Detalle](ui-ux/flow-results.json). |
| Comprobaciones complementarias | Movimiento reducido, submenú con teclado, CRC, axe en escritorio y objetivos de día de al menos 44 × 44 px a 360 px. [Detalle](ui-ux/final-checks.json). |
| axe-core 4.14.0 | **20 combinaciones de página/rol**, sin infracciones automáticas de las reglas WCAG A/AA seleccionadas; calendario de escritorio comprobado adicionalmente. [Detalle y revisiones manuales pendientes](ui-ux/accessibility-results.json). |

Las 15 pruebas nuevas incluyen eventos anteriores, hoy antes/igual/después de la hora actual, inactivos, varios en un día, ausencia de próximos eventos, historial, diciembre/enero, febrero bisiesto, meses de 4/5/6 semanas, entrada inválida, límites de años, aislamiento público, roles y errores de formulario. La hora fijada en las pruebas incluye UTC en enero mientras Costa Rica permanece en diciembre.

El navegador se ejecutó con Playwright y Chrome del equipo contra `127.0.0.1:8765`, con SQLite y archivos **exclusivamente temporales** en `/tmp/banda-ui-qa`. Las capturas usan nombres, estudiantes, eventos, imágenes y saldos ficticios creados para QA. No son datos del proyecto ni de producción. Los scripts de ejecución temporales fueron `browser.py`, `flows.py`, `accessibility.py`, `final_checks.py`, `refreshed_templates.py` y `empty_state.py` en ese directorio; los resultados y capturas se conservan en este informe. axe-core se instaló únicamente en ese directorio temporal.

Se comprobaron 360, 390, 768, 1024 y 1440 px, títulos largos, varios eventos el mismo día, menú con Tab/Enter/Escape, enlace «Ir al contenido», Lista/Mes sin JavaScript, imagen fallida, estado vacío, mes sin actividades y navegación de año. Se amplió el texto a 200 % a 360/720 px; 720 CSS px también comprueba el espacio de reflujo equivalente a un escritorio de 1440 px al 200 %. **No se automatizó el ajuste nativo de zoom del navegador.**

El recorrido funcional creó una venta de dos entradas, descargó su PDF, confirmó un código de ticket y rechazó su reutilización, registró un abono, comprobó el saldo de caja y creó/editó un evento con publicación en el mes correspondiente. Todos los POST conservaron CSRF. El cambio de visibilidad para capturar el estado totalmente vacío se hizo solo en la base temporal y se restauró al terminar.

## Evidencia visual

- [Agenda móvil, 360 px](ui-ux/agenda-360.png).
- [Agenda de escritorio, 1440 px](ui-ux/agenda-1440.png).
- [Vista mensual móvil, 360 px](ui-ux/mes-360.png).
- [Sin próximas actividades ni eventos del mes, 360 px](ui-ux/sin-actividades-360.png).
- [Detalle de evento móvil](ui-ux/evento-360.png).
- [Panel de encargado](ui-ux/panel-guardian-1440.png).
- [Panel del comité](ui-ux/panel-committee-1440.png).
- [Panel de administrador](ui-ux/panel-admin-1440.png).

## Criterios de aceptación

- [x] El hero dejó de anteceder a la agenda: eliminado de `home.html` y de sus estilos.
- [x] Próxima actividad calculada con datos Django y fecha/hora local: pruebas de `AgendaTests`.
- [x] Agenda prioritaria en escritorio/móvil: capturas a 1440/360 px.
- [x] Lista móvil legible; mes opcional con enlaces a todos los eventos de cada día.
- [x] Anterior, Siguiente y Hoy conservan la vista; transición diciembre/enero probada.
- [x] Hoy tiene marco, subrayado, leyenda y `aria-current="date"`.
- [x] Paneles sin eventos cuyo inicio ya pasó; misma regla para encargado y comité.
- [x] Meses históricos activos accesibles y ordenados por fecha/hora/ID.
- [x] Datos prácticos antes del cartel en el detalle, incluso si la imagen falla.
- [x] Menús por rol; acceso directo a rutas protegidas comprobado por tests.
- [x] Paneles y formularios priorizan tareas; confirmaciones tienen cancelación fija.
- [x] Suite financiera/de permisos existente aprobada; venta, abono, PDF y validación manual comprobados en navegador.
- [x] Teclado, foco visible, movimiento reducido y ausencia de desbordamiento global comprobados; texto ampliado al 200 %.
- [x] Suite final, `check`, migraciones y JavaScript sin errores.
- [x] Trabajo documentado y limitado al repositorio local, sin despliegue.

## Límites y comprobaciones externas pendientes

- Los eventos no tienen hora final: el criterio es inicio futuro, no una estimación de duración.
- Las pruebas de base de datos de esta entrega usaron SQLite. No se conectó a PostgreSQL/Supabase ni a Vercel.
- Se comprobó la entrada manual del código de ticket; no la cámara de un teléfono físico ni sus permisos HTTPS.
- axe no certifica accesibilidad completa. Sus casos de revisión manual incluyen contraste de elementos decorativos y el vídeo de cámara en vivo (sin pista hablada). No se probó un lector de pantalla real, Safari/Firefox ni zoom nativo del navegador.
- Conviene realizar esas comprobaciones en los dispositivos de operación antes de publicar. No requieren cambios de reglas de negocio.

## Git y entrega

Rama: `main`. HEAD: `0170d88`, el mismo de partida. Cambios locales sin commit; revisar con `git diff --stat`, `git diff` y `git status --short` (los archivos nuevos se muestran aparte mientras no se agreguen al índice). No se hizo push, merge ni despliegue. No se modificaron secretos, archivos de entorno, configuración de infraestructura ni migraciones.
