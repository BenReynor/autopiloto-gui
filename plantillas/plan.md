# PLAN — Sistema POS

Reglas:
- Cada tarea = 1 línea de QUÉ + 1 línea de CRITERIO (archivos + test). Nada subjetivo.
- DONE = commit en la rama de la tarea + gate verde (gate.sh) + el test falla sin el cambio.
- El loop procesa las tareas en orden: deja las dependencias abajo primero (modelos → API → UI).
- Las 3 tareas de abajo son la PLANTILLA: reemplázalas por tus tareas reales conservando este formato.

## Tareas (en orden de dependencia)

- [ ] #1 STOCK: impedir que el stock de un producto quede en negativo al registrar una venta.
      criterio: test nuevo en Backend/productos/tests/test_services.py → test_stock_no_negativo falla sin el cambio y en verde con él; gate.sh OK.

- [ ] #2 STOCK: exponer `stock` actualizado en la respuesta de /api/productos/productos/ tras una venta.
      criterio: test en Backend/productos/tests/test_views.py → test_stock_tras_venta en verde; gate OK.

- [ ] #3 API: filtro ?categoria=<id> en /api/productos/productos/.
      criterio: test en Backend/productos/tests/test_views.py → test_filtro_categoria en verde; gate OK.

- [ ] #4 UI: checkbox "Giftcard" en frontend/view/productos_view.py sincronizado con el campo del modelo.
      criterio: imports frontend OK en gate.sh y gate OK (UI sin tests, lo decide el gate).