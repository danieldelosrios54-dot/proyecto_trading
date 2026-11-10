# Etapa 1: Validación de las entradas principales (propuesta y diseño técnico)

## Conclusión
- **Tus entradas están en muy buen estado.** Apliqué tus reglas a los datos reales: 703 de 703 señales pasan R1–R11 y ningún tick rompe T1–T8.
- **Tus propuestas sirven, con 5 cambios.** El más importante: tal como está escrita, T11 tiraría 12 señales del 17-jul por un hueco que ninguna señal necesita.
- **Falta un tipo de control.** R1–R11 revisan el formato, pero no detectan un dato bien escrito y equivocado. Comparar con la vela real sí lo detecta y ya encontró 2 señales para revisar: **ID 675 e ID 702**.
- Este documento cubre **solo la etapa 1**. Al terminarla me detengo; las mediciones van después.

## Respuestas a tus tres preguntas

### 1. ¿Los saltos mayores a 60 ticks son error de descarga y afectan el recorrido?
**No encontré ninguna señal de error de descarga. Sí pueden afectar el recorrido de una señal, pero porque son mercado real, no porque el dato esté mal.** T9 es una regla de notificar, así que esas fechas siguen siendo válidas.

Revisé los 62 saltos de las 19 fechas uno por uno. Un error de descarga dejaría un hueco de tiempo antes del salto, y eso no aparece:

| Tipo de salto | Casos | Qué se ve en los datos | Lectura |
|---|---|---|---|
| Después de una pausa | 5 (10-jul ×2, 11-ago, 12-ago, 25-ago) | Antes hay de 4,8 a 10 s sin ticks. Luego un solo tick de 246 a 962 contratos, y el precio se queda en el nivel nuevo | Tiene la forma de una pausa de CME (Velocity Logic) y su reapertura |
| Dentro de una ráfaga | 57 | Menos de 16 ms desde el tick anterior, entre 1 y 23 contratos, cientos de ticks en 0,2 s. El Bid y el Ask llegan a estar separados tanto como el salto | Operaciones reales cruzando un libro casi vacío durante un movimiento violento |

21 de los 62 saltos ocurren justo en el minuto +30, las 10:00 de Nueva York, hora habitual de noticias económicas.

**Corrección a lo que te escribí antes:** dije que eran reales porque el Last nunca queda fuera del Bid/Ask. Ese argumento es débil, porque en muchos de estos saltos el Bid/Ask estaba abierto 60 a 138 ticks. La evidencia válida es la de la tabla.

**Qué no puedo probar:** comparar con NinjaTrader no sirve como prueba independiente, porque el Data Box y el archivo salen de la misma base. Para confirmarlo del todo haría falta una segunda fuente de datos.

**Cómo afecta el recorrido:**
- Solo importa si la señal está en juego en ese instante. De las 19 fechas, en 17 el salto cae dentro del tramo de alguna señal (45 señales en total); el 8-jul y el 25-ago no tocan a ninguna.
- El ejemplo más fuerte es el 28-ago a las 14:00:00 UTC: el precio va y viene 138 ticks dentro del mismo milisegundo, con 5 señales en tramo. Una posición abierta ahí registra un MAE o MFE enorme por operaciones de 1 contrato.
- Como un stop se dispara con operaciones reales, ese movimiento también te habría sacado en vivo. Por eso **no se debe borrar ni invalidar**, solo avisar con detalle.

**Decisión:** T9 sigue como notificar, solo para las señales cuyo tramo toca, e indicando hora, tamaño, pausa previa y volumen. El riesgo real pasa a la etapa 2: el deslizamiento fijo de 2 ticks en el SL queda corto en estos momentos.

### 2. ¿Qué es DuckDB y por qué le puse coste medio?
DuckDB es un programa gratuito de base de datos que funciona dentro de tu computador, sin servidor. Guarda los datos en un archivo y se le hacen preguntas en SQL, un lenguaje propio para consultar tablas. Es muy bueno, por ejemplo, para "suma el volumen por semana de todos estos meses".

Instalarlo es fácil. **"Medio" era mi criterio sobre mantenerlo, no un dato medido:**
- El proyecto tendría dos lenguajes, SQL y Python, en vez de uno.
- Tu trabajo principal es recorrer tick a tick con estados ("esperó 300 ms, no se pudo colocar, volvió, se disparó"). Eso no se expresa bien como consulta, así que los ticks acabarían volviendo a Python de todos modos.
- Si vuelves a descargar una semana, hay que borrar e insertar dentro de la base. Con archivos por fecha, se reemplaza el archivo y ya.
- Todo queda en un solo archivo: si una escritura falla, el daño alcanza a todo.

**Lo que no hice:** probarlo con tus datos, porque no está instalado. Las comparativas publicadas indican que usa menos memoria que Polars, pero aquí eso no es el límite, como se ve abajo. Y no se pierde la opción: DuckDB lee Parquet directamente, así que se podría añadir después sin convertir nada.

### 3. Si los datos crecen, ¿sigo recomendando lo mismo?
**Sí, y la ventaja de la opción C aumenta.** Medí tus 68 días convertidos a Parquet: **239 MB en total frente a 7,3 GB, unos 3,5 MB por día, y 0,013 s en leer un día.**

| | Hoy (14 semanas) | El doble (28 semanas) | Un año (estimado) |
|---|---|---|---|
| Datos originales | 7,3 GB | 14,6 GB | ~27 GB |
| A. Leer todo cada vez | 56 s | ~2 min | ~3,5 min por lectura |
| **C. Parquet por fecha: tamaño** | 239 MB | ~480 MB | ~0,9 GB |
| **C. Parquet: leer todos los días** | ~1 s | ~2 s | ~3 s |

Los valores de "el doble" y "un año" son proyecciones proporcionales, no mediciones. Hay dos motivos por los que C aguanta bien:
- Cada semana solo se procesa el archivo nuevo, unos segundos, sin importar cuánta historia tengas.
- Se trabaja un día a la vez, así que la memoria necesaria no crece con los meses.

**Lo que sí crece, y no es almacenamiento:** el simulador. Hoy son 703 señales × 17.161 combinaciones × 4 escenarios, unos 48 millones de simulaciones; con el doble de señales, unos 96 millones. Eso se resuelve en el diseño de la etapa 2, evitando recorrer los ticks una vez por combinación.

## 1. Lo que entendí
- **Qué resuelve:** que un error de tipeo o de descarga no contamine sin que se note las mediciones de SL/TP.
- **Decidido (documento 1):** formato de ticks, nanosegundos enteros, precios en ticks enteros, orden del archivo como desempate, velas iguales a NinjaTrader.
- **Abierto (documento 2):** reglas R y T, y la extracción de ticks por fecha.
- **Confirmado por ti:** el 14-sep y anteriores son Sep-26; desde el 15-sep, Dec-26. Buy = vela "Hora UTC" verde, Sell = roja, "1er Vela (VC)" cualquier color.

## 2. Criterios (en orden de prioridad)
1. No alterar los datos: orden y volumen idénticos a NinjaTrader.
2. Que nada falle en silencio (por ejemplo, datos viejos tras una nueva descarga).
3. No descartar señales sin un motivo real.
4. Sencillez y facilidad de mantenimiento.
5. Velocidad.

## 3. Comprobado con tus datos (hecho verificado)
| Comprobación | Resultado |
|---|---|
| Registro | 703 señales, 68 fechas, 29-jun a 2-oct, 14 semanas. R1–R11: 0 incumplimientos |
| Archivos de ticks | 15 archivos, 7,3 GB, unos 150 millones de líneas, 0 líneas mal formadas. Lectura completa: 56 s |
| Tus 6 velas del Data Box | 6 de 6 exactas, incluido el volumen |
| Tus 2 mediciones de recorrido | Exactas |
| Ejemplos 1 y 2 de MFE/MAE | Coinciden; solo Hora MFE (1 min) del ejemplo 2 varía (14:01:47.672 frente a .740), lo que ya avisas por el gráfico de 10 ticks |
| T3, T5, T6, T7, T8 | 0 casos en las 68 fechas |
| T9 (salto mayor a 60 ticks) | 19 fechas, 201 señales si se aplica por fecha; solo **45** tienen el salto dentro de su propio recorrido |
| T10 (hueco de 10 a 60 s) | 25-sep: 36 s en el minuto +68 y 10 s en el +69. 10-jul: exactamente 10,000 s en el minuto +62,7 |
| T11 (hueco mayor a 60 s) | Solo 17-jul: 390 s, del minuto +83,5 al +90. Ese día ninguna señal pasa del +64 |
| T12 (volumen bajo) | Solo 14-sep (44 %, 10 señales). 3-jul y 7-sep están bajos, pero no tienen señales |
| Ticks seguidos idénticos | Cerca del 40 %. Son reales: las velas solo cuadran conservándolos, así que **nunca se deben eliminar** |
| Vela real contra registro | Fuera de "1er Vela (VC)", 686 de 688 con el color correcto. Se salen ID 675 e ID 702 |

**Inferencia:** los saltos de T9 son movimientos reales; la evidencia y sus límites están en la respuesta 1.

**Dato a tener en cuenta:** las columnas Condiciones Estructura, Condiciones Continuidad, SE, SC, D y Notas tienen "-" en las 703 señales. R4 pasa, pero esas columnas hoy no permiten ningún análisis.

## 4. Investigación
- **Buscado:** formato de exportación de NinjaTrader, limpieza de datos de ticks, herramientas para archivos grandes y fecha de rollover.
- **Encontrado:**
  - El formato de exportación coincide con lo que documentas ([foro NinjaTrader](https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/94196-historical-data-export-formats)).
  - La limpieza posterior suele dañar los datos, porque muchas anomalías son mercado real ([Databento](https://databento.com/blog/data-cleaning)); por eso T9 solo debe avisar. También se recomienda conservar el original intacto ([Quantpedia](https://quantpedia.com/working-with-high-frequency-tick-data-cleaning-the-data/)).
  - Polars y DuckDB superan ampliamente a pandas con archivos grandes, y Parquet carga más rápido que CSV ([comparativa](https://www.danilchenko.dev/posts/duckdb-vs-polars/)).
  - El rollover habitual de septiembre 2026 fue el 14-sep ([calendario](https://www.futureshive.com/blog/futures-rollover-dates-explained), fuente secundaria).
  - CME pausa el mercado unos segundos cuando el precio se mueve muy rápido y luego reabre ([Velocity Logic, CME](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457218368/Velocity+Logic)). La duración exacta no aparece en esa página; fuentes secundarias hablan de unos 2 a 10 s ([Topstep](https://help.topstepbrokerage.com/en/articles/15033707-cme-velocity-logic)). No pude confirmar que tus 5 casos sean pausas oficiales; es inferencia por su forma.
- **Descartado:** métodos estadísticos para borrar ticks atípicos (Brownlees-Gallo), porque alteran datos que deben quedar fieles.
- **No pude verificar en una fuente** que la exportación sea UTC. Queda comprobado de forma indirecta: las 6 velas coinciden usando horas UTC.

## 5. Alternativas para manejar los ticks
| Opción | Ventajas | Desventajas / riesgos | Coste |
|---|---|---|---|
| A. Sin extraer: leer los 7,3 GB cada vez | La más simple; nunca desactualizada | 56 s por lectura, demasiado para simular 17.161 combinaciones | Bajo |
| B. Tu propuesta: un .txt por fecha | Se puede abrir y leer | Archivos pesados; sin aviso si vuelves a descargar | Bajo |
| **C. Un Parquet por fecha + registro de origen (recomendada)** | Más liviano y rápido; conserva el orden; detecta descargas nuevas | No se abre con doble clic (a ese tamaño tampoco un .txt sería práctico) | Bajo |
| D. Base de datos DuckDB | Consultas potentes entre muchas fechas | Dos lenguajes; el recorrido tick a tick vuelve a Python; reemplazar una semana es más delicado | Instalar: bajo. Mantener: medio (criterio mío, sin medir) |

*Parquet es un formato de archivo comprimido, por columnas, pensado para datos grandes.*

La extracción deja cerca de un tercio de las líneas, no una décima parte, porque la apertura concentra mucho volumen. Sigue valiendo la pena por la etapa 2.

## 6. Evaluación de tus propuestas (primero los puntos débiles)
| # | Problema | Consecuencia | Solución |
|---|---|---|---|
| 1 | T9, T10 y T11 actúan sobre la fecha completa | Se pierden 12 señales del 17-jul sin motivo y T9 marca 201 cuando importan 45 | Afectan a una señal solo si caen en **su tramo**: desde el inicio de la Vela OP hasta Hora UTC + ventana de ejecución + 12 min |
| 2 | "Solo se extrae la faltante" | Hoy volviste a descargar septiembre: se habría seguido usando la extracción vieja sin avisar | Guardar nombre, tamaño y fecha de cada archivo fuente; si cambia, se vuelve a extraer |
| 3 | T1 dice validar solo lo extraído, pero una línea ilegible no se puede ubicar en ninguna ventana | La regla no se podría cumplir como está escrita | T1 se revisa durante la extracción, sobre el archivo completo |
| 4 | T3 no detecta una misma fecha repetida en dos archivos | Una semana descargada dos veces pasaría si está en archivos separados | Nueva condición: ventana con ticks en más de un archivo = fecha inválida. Se reparte por la hora del tick, no por el nombre (el 15-sep empieza en un archivo y sigue en otro) |
| 5 | R1–R11 no revisan el contenido contra el mercado | Un Tipo o una Hora mal escritos pasan como válidos | Nueva R13: color de la vela "Hora UTC" |
| 6 | "Apertura UTC" se escribe a mano y controla R8 | Desde el 2-nov la apertura es 14:30 UTC; un descuido invalidaría o desplazaría señales | Nueva R12: debe corresponder a las 9:30 de Nueva York de esa fecha |
| 7 | T12 menciona "ventanas de velas" | Quedó de una versión anterior: esta propuesta no las tiene | Eliminar esa frase |
| 8 | R5/R6 con horas de Excel | Excel guarda horas con decimales y una comparación exacta daría falsos errores | Comparar al segundo |

**Fortalezas:** las reglas son claras y los umbrales cuadran con los datos. La ventana −10/+90 cubre lo necesario (hasta +76 como máximo). Separar "Invalidar" de "Notificar" es acertado y coincide con lo investigado.

## 7. Revisión por roles
- **Trader:** un hueco a las 10:53 de Nueva York no afecta una señal de las 10:00; descartarla no tiene lógica de mercado. El 14-sep en Sep-26 se opera con menos liquidez, así que el aviso de volumen debe quedar visible.
- **Estadístico:** descartar por fecha completa quita muestra sin motivo. El control de color no sesga la muestra si solo detecta errores que tú corriges; no debe usarse para filtrar por resultados.
- **Programador:** aplicar por tramo es apenas un poco más complejo que aplicar por fecha y todo sale de una sola función.
- **Conflicto:** el programador preferiría la regla por fecha, más simple; el trader y el estadístico la prefieren por tramo. **Propongo por tramo**, porque el coste es mínimo y evita perder 12 señales. El reporte sigue mostrando el estado de cada fecha.

## 8. Decisiones que apruebas con este documento
1. Mantener R1–R11 y T1–T10 con las aclaraciones de la sección 6.
2. T9, T10 y T11 afectan solo a las señales cuyo tramo tocan.
3. Añadir **R12** (Apertura UTC según calendario de Nueva York): invalida.
4. Añadir **R13** (Buy verde, Sell roja, "1er Vela (VC)" sin control): invalida; si la vela abre y cierra igual, solo notifica. Invalido porque es regla de tu estrategia y el dato erróneo contaminaría el resultado. Cuando corrijas el Excel, la señal se recupera sola.
5. Extraer a Parquet por fecha, con detección de archivos nuevos o cambiados.
6. Ampliar T3 para fechas en más de un archivo y quitar la frase sobrante de T12.

## 9. Diseño técnico
**Herramientas:** Python, **Polars** (lee archivos enormes; ya medido con tus datos), **openpyxl** (lee y escribe Excel), **pytest** (pruebas automáticas) y tzdata (calendario de horarios). Se instalan en un entorno propio dentro de `proyecto\`, sin depender de la carpeta "(BORRAR)". Tus archivos de entrada nunca se modifican.

**Estructura:**
```
proyecto\
  main.py                  → un solo comando: python main.py validar
  config.py                → ventanas, umbrales y valores permitidos
  validacion\registro.py   → lee el Excel; R1–R12
  validacion\extraccion.py → extrae ticks; T1
  validacion\ticks.py      → T2–T12 y tramo de cada señal
  validacion\velas.py      → arma velas; R13
  validacion\reportes.py   → genera los archivos de salida
  tests\
```

**Flujo:**
1. Leer el Excel (encabezados en la fila 2) y aplicar R1–R12.
2. Por cada archivo de ticks nuevo o cambiado: revisar el formato y guardar las ventanas [Apertura −10, Apertura +90) de las fechas con señales.
3. Validar cada fecha y ubicar cada incidente en el tiempo.
4. Asignar a cada señal su estado según su tramo.
5. Armar la vela "Hora UTC" y aplicar R13.
6. Escribir los reportes.

**Cada Parquet guarda:** posición original del tick, tiempo en nanosegundos enteros, Last, Bid y Ask en ticks enteros, y Volume. Sin ordenar, sin eliminar y sin pasar por `datetime`.

**Precisiones de reglas:** T10 = de 10 a 60 s inclusive; T11 = más de 60 s; un tick exactamente en el final de la ventana no entra. La mediana de T12 se calcula solo con fechas que tienen señales. T9 solo notifica y reporta hora, tamaño, pausa previa y volumen de cada salto; ningún tick se borra ni se corrige.

**Salidas:**
- `salida\ticks_extraidos\aaaa_mm_dd.parquet` y el registro de archivos de origen.
- `salida\validaciones\validacion_señales_registradas.xlsx` y `validacion_ticks_extraidos.xlsx`, con Resumen, ID y Motivo (o "Sin señales Invalidas" / "Sin señales validas con notificación"), estado de cada señal y, en ticks, detalle por fecha con la hora y el tamaño de cada incidente.

**Pruebas (solo las que protegen los resultados):**
- Las 6 velas del Data Box y las 2 mediciones, con tus valores reales.
- Un tick exactamente en el cierre pasa a la vela siguiente.
- Los ticks idénticos se conservan y el orden no cambia.
- Huecos de exactamente 10 y 60 s, y los bordes de la ventana.
- Cada regla con un caso que cumple y uno que incumple.
- El cambio de horario en R12.
- Un archivo modificado se vuelve a extraer y uno sin cambios no.

## 10. Verificación al terminar
Una corrida completa debe dar lo que ya medí:
- 703 señales leídas; 0 inválidas por R1–R12.
- R13: exactamente ID 675 e ID 702.
- 17-jul sin invalidar; 62 saltos en 19 fechas y 45 señales con aviso T9; huecos T10 solo el 10-jul y el 25-sep; 14-sep con aviso T12.
- Una segunda corrida no extrae nada.

Cualquier diferencia se investiga antes de darla por buena.

## 11. Pendiente y en riesgo para la etapa 2 (no se resuelve ahora)
- **Contradicción en tu ejemplo 1:** muestra ejecución a las 13:31:00.252, pero el Escenario 1 coloca la orden a los 0,300 s. A las .288 el precio (28882,25) ya había pasado la orden (28882,50), así que según tu regla no se podría colocar en ese momento.
- **Muestra corta:** 14 semanas de una sola época. No permite comprobar que la ventaja se sostenga "en diferentes años y épocas".
- **Riesgo de sobreajuste:** 17.161 combinaciones filtradas con los mismos datos darán ganadoras por azar; hará falta probar fuera de muestra.
- **Deslizamiento en movimientos violentos:** 2 ticks fijos en el SL es optimista cuando el precio salta 60 a 197 ticks de golpe. Conviene medir qué señales quedan expuestas a esos instantes.
- **Replay y en vivo:** ninguna columna indica cómo se registró cada señal, y pueden comportarse distinto.
- **Por definir:** el MFE puede salir negativo por el deslizamiento; hay 25 casos con misma hora en Te 1 y Te 2; las señales 298, 370 y 687 tocaron el precio de la orden antes de cerrar la vela de confirmación; y `resultados_combinaciones` apunta a la carpeta `mfe_mae`.

## 12. Siguiente paso más valioso
Construir esta etapa, revisar contigo las señales 675 y 702, y luego abrir la etapa 2 empezando por la contradicción del ejemplo 1, porque define cómo se simula cada entrada.
