# HDV (Hôtel de Vente) en Dofus Retro 1.48 — referencia para bot

**Fecha:** Junio 2026 · Compra, venta y arbitraje automatizado en el mercado

---

## 1. Por qué el HDV es la pieza económica clave

Para un bot de farmeo, el HDV es donde se **convierte el botín en kamas**. Un bot que recolecta/combate pero no vende automáticamente obliga a intervención manual constante. Automatizar el HDV cierra el ciclo: farmear → vender → repetir. Además habilita estrategias puramente económicas (comprar barato/vender caro en el tiempo).

Pero el HDV es de las partes **más delicadas** de automatizar, por tres razones: la mecánica de lotes es propensa a errores caros, los precios cambian constantemente, y el comportamiento repetitivo de refresco de precios es **una firma clásica de bot** (la propia comunidad lo dice: "personne ne refresh les prix en boucle sauf les bots").

---

## 2. Reglas del HDV que el bot debe conocer (Retro 1.48)

Antes del código, la mecánica del juego — porque condiciona toda la lógica:

### Lotes
- Los objetos se venden en **lotes de 1, 10 o 100** unidades. **Error clásico y carísimo:** poner el precio de 1 unidad cuando el lote es de 10 → vendes 10 al precio de 1. Tu bot debe **multiplicar/dividir explícitamente** y validar el tipo de lote antes de confirmar.
- El cliente preselecciona el lote automáticamente según cantidad (>100→x100, >10→x10), lo que provoca esos errores. Tu bot no debe fiarse del default: fija el lote explícitamente.

### Límites de objetos en venta (1.42+)
- El número de slots de venta ahora **depende directamente de tu nivel de personaje** (a mayor nivel, más objetos puedes poner en venta), no de un tope fijo por ciudad.
- Astrub mantiene su restricción de **nivel ≤ 60** para los ítems.

### Taxas (coste de poner en venta, 1.42+)
- Con la unificación, la taxa se **homogeneizó a 2%** en el HDV unificado.
- La taxa se paga **al poner en venta**. **Novedad 1.42 relevante para el bot:** ahora se puede **modificar el precio de un ítem SIN retirarlo de la venta** (antes había que quitar y volver a poner). Esto cambia el flujo de "refrescar precio" y reduce fricción.

### Duración
- Los objetos quedan en venta **2 semanas** (72h en Astrub). Si no se venden, vuelven a la **banque del vendedor**.

### Tipos de HDV (uno por categoría)
- Hay HDV separados por oficio/categoría: recursos, animales, documentos, pergaminos, escudos (Pandala), piedras de alma, etc. **No hay HDV para Dofus.** Tu bot debe ir al HDV correcto según el ítem.

### Unificación de HDV (¡cambio clave en 1.42+!)
- **Desde la actualización 1.42 (dic. 2023), los HDV de Bonta, Brakmar y Astrub están UNIFICADOS en una sola instancia.** Un ítem puesto en venta en una ciudad se ve y se compra desde las otras. Esto es lo contrario de la era clásica/1.29 (donde cada HDV era independiente), y era una petición histórica de la comunidad que Ankama finalmente implementó.
- **Consecuencia para el bot:** **NO hay arbitraje geográfico entre ciudades** — es el mismo mercado en las tres. No tiene sentido comprar en Brakmar para vender en Bonta. La estrategia de "flip inter-ciudad" del planteamiento clásico **queda anulada en 1.48**.
- Astrub sigue limitado a nivel 60 máximo; el resto de ítems se comparten entre las grandes ciudades.
- El arbitraje que sí queda posible es **temporal** (comprar barato ahora, vender cuando el precio suba) o frente al **precio PNJ** (algunos ítems/equipos se venden caro a PNJ), no geográfico.

---

## 3. Paquetes del HDV (del mapeo de protocolo)

Recordatorio de los IDs relevantes (sufijo `K`=éxito, `E`=error). El HDV usa el namespace **`EH`** (Exchange-bigStore) dentro de los intercambios.

### Abrir y navegar
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `EHT` | ExchangeBigStoreType | Seleccionar **tipo/categoría** de ítem |
| S→C | `EHL` | BigStoreTypeItemsList | Lista de ítems de ese tipo |
| S→C | `EHM+`/`EHM-` | items movement add/remove | Stream de altas/bajas en la lista por tipo |
| C→S | `EHl` | BigStoreItemList | Pedir **lista de un ítem concreto** (sus lotes/precios) |
| S→C | `EHl` | BigStoreItemsList | Los lotes disponibles de ese ítem |
| S→C | `EHm+`/`EHm-` | item lots add/remove | Stream de lotes |

### Buscar
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `EHS` | BigStoreSearch | Buscar por nombre (4 letras mínimo) |
| S→C | `EHSK`/`EHSE` | Search success/error | Resultado |

### Comprar
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `EHB` | ExchangeBigStoreBuy | **Comprar** un lote |
| S→C | `EBK`/`EBE` | Buy success/error | Resultado de compra |

### Vender (a través del modo intercambio con el HDV)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `ES` | ExchangeMovementSell | **Poner en venta** (con cantidad/lote y precio) |
| S→C | `ESK`/`ESE` | Sell success/error | Resultado de venta |

### Precio de referencia (clave para fijar precio)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `EHP` | GetItemMiddlePriceInBigStore | Pedir **precio medio** del ítem |
| S→C | `EHP` | ItemMiddlePrice | El precio medio que devuelve el servidor |

> `EHP` es tu mejor amigo para vender: el servidor te da un **precio medio** sobre el que basar tu estrategia, sin tener que parsear toda la lista.

### Abrir el HDV (vía PNJ)
El HDV se abre hablando con el PNJ del HDV (`DC` DialogCreate → `DR` DialogResponse), que dispara la interfaz de intercambio big-store. El cierre es `EV` (ExchangeLeave).

---

## 4. Flujos completos (secuencias de paquetes)

### Flujo VENDER
```
1. Caminar al mapa del HDV correcto (según categoría del ítem)
2. DC  -> hablar con el PNJ del HDV          (S->C: DCK)
3. DR  -> elegir "Vender"                    (abre interfaz big-store)
4. EHP -> pedir precio medio del ítem        (S->C: EHP precio)
5. [decidir precio según estrategia, sección 5]
6. ES  -> poner en venta (ítem, lote x1/x10/x100, precio)
7.       (S->C: ESK éxito / ESE error)        ← validar SIEMPRE
8. EV  -> salir del HDV
```

### Flujo COMPRAR
```
1. Caminar al HDV correcto
2. DC -> PNJ -> DR "Comprar"
3. EHT -> seleccionar categoría              (S->C: EHL lista de ítems)
4. EHl o EHS -> ítem concreto / búsqueda     (S->C: EHl lotes y precios)
5. [evaluar si el precio cumple tu umbral]
6. EHB -> comprar el lote elegido            (S->C: EBK éxito / EBE error)
7. EV -> salir
```

### Flujo ARBITRAJE TEMPORAL (flip) — NO geográfico en 1.48
> Nota: en 1.48 el HDV está unificado entre ciudades, así que **no hay arbitraje geográfico**. El arbitraje viable es **temporal** o frente a PNJ.
```
1. En el HDV unificado: EHl/EHS -> leer precios mínimos
2. Comparar contra precio medio (EHP) o contra precio PNJ conocido
3. Si precio_actual < umbral_rentable: EHB comprar
4. Esperar a que el precio suba / revender más caro: ES
   (descontar la taxa 2% del margen)
```

---

## 5. Estrategias de fijación de precio

La lógica de "a cuánto vendo" es el corazón del bot HDV. Opciones (de simple a sofisticada):

### 5.1 "-1 kama bajo el más barato" (la clásica)
Lees el lote más barato actual y pones el tuyo a **1 kama menos** para ser prioritario en la cola de venta. Es lo que hace la mayoría de bots (MoonBot lo cita explícitamente: "sells at -1 kama below the lowest price").
- **Pro:** vendes rápido.
- **Contra:** es la firma de bot más reconocible; alimenta guerras de precios a la baja; pagas taxa cada refresco. La comunidad lo detecta de inmediato.

### 5.2 Precio fijo / suelo
Fijas un precio mínimo bajo el cual no vendes. Si el mercado está por debajo, esperas. Evita malvender.
- **Pro:** protege márgenes, menos refrescos (menos firma de bot).
- **Contra:** vendes más lento.

### 5.3 Porcentaje del precio medio
Vendes a, por ejemplo, **95% del precio medio** (`EHP`). Equilibra velocidad y margen sin entrar en guerra de -1 kama.

### 5.4 Lote inteligente
Elegir x1/x10/x100 según el ítem: recursos baratos de alto volumen → x100; ítems caros → x1. Maximiza ventas y minimiza taxa por unidad.

> **Recomendación anti-detección:** evita la 5.1 pura y constante. El refresco compulsivo de precios "-1 kama" cada pocos minutos es el patrón que los moderadores y jugadores asocian directamente con bots. Combina precio-medio + refrescos espaciados y aleatorios.

---

## 6. Cálculo de rentabilidad (lo que tu bot debe computar)

Antes de cada operación, descuenta costes:

```
Vender:
  ingreso_neto = precio_venta - (precio_venta × 0.02)   # taxa unificada 2% en 1.48
  (modificar precio sin retirar ya es posible en 1.42+, pero re-listar paga taxa)

Comprar para flip temporal:
  margen = precio_venta_neto - precio_compra - taxa_venta(2%)
  solo opera si margen > umbral_minimo
```

El **arbitraje geográfico ya no aplica** (HDV unificado), así que no hay coste de viaje entre ciudades que descontar. El factor temporal (cuánto tarda en venderse) sí importa.

---

## 7. Integración con el resto del bot

- **Tras recolectar/combatir:** cuando los pods se llenan (`Ow` ItemsWeight), el bot decide ir a banco o a HDV. Patrón común: depositar recursos valiosos en HDV, basura en banco o destruir.
- **Multicuenta — mula mercader:** una cuenta dedicada a vender mientras las demás farmean. Ojo: el **modo mercader** (placement físico en mapa) es distinto del HDV y **desconecta la cuenta**; además en monocuenta está **prohibido tener una cuenta en modo mercader mientras juegas con otra**. Para multicuenta en HDV, usa el HDV directo (no modo mercader) o una mula que entra, vende y sale.
- **Gestión de inventario:** parsea `OAK`/`OR`/`OQ` para saber qué tienes y cuánto antes de decidir qué poner en venta.

---

## 8. Checklist de implementación HDV

1. [ ] Mapa de categoría→HDV (qué ítem se vende en qué HDV y dónde está).
2. [ ] Apertura vía PNJ (`DC`/`DR`) y cierre (`EV`).
3. [ ] Lectura de precios: `EHl`/`EHS` (lotes) + `EHP` (precio medio).
4. [ ] **Validación de lote** (x1/x10/x100) antes de `ES` — evita el error caro.
5. [ ] Estrategia de precio configurable (precio-medio recomendado sobre -1 kama).
6. [ ] Cálculo de rentabilidad con taxa unificada 2% (1.48).
7. [ ] Validar `ESK`/`EBK` (éxito) vs `ESE`/`EBE` (error) en cada operación.
8. [ ] Refrescos espaciados y aleatorios (anti-detección).
9. [ ] Integración con pods (`Ow`) y inventario (`OAK`/`OQ`).

---

## 9. Riesgos específicos del HDV

- **Error de lote = pérdida directa de kamas.** Es el fallo más caro y común. Doble validación obligatoria.
- **Refresco de precios = firma de bot.** El patrón "-1 kama en bucle" es lo que la comunidad y moderadores asocian con bots de recursos bajo nivel. Espacia y randomiza.
- **Mercado dinámico:** un precio leído hace 30 s puede estar obsoleto. Re-lee justo antes de operar.
- **Modo mercader prohibido en monocuenta** mientras juegas otra cuenta (sanción específica).
- **Manipulación de mercado**: tirar precios agresivamente puede llamar la atención de moderadores (los precios "irrealistas" están vigilados).

---

## 10. Recursos

- **Mapeo de paquetes (reporte previo)** — namespace `EH`/`Exchange` completo.
- **`kralamoure/retroproto`** — `msgcli/`, `msgsvr/` definen los campos exactos de `ES`, `EHB`, `EHP`, `EHl`, `EHS`.
- **MoonBot / AnkaBot** — referencia funcional de venta automática (-1 kama, lote inteligente, precio medio).
- **Wikis Retro** (dofusretro.jeuxonline, dofux.org) — reglas de HDV: lotes, taxas, límites, ubicaciones de cada HDV.
- **APIs de datos** (dofapi, moon-bot wiki) — IDs de ítems para cruzar nombres y categorías.

---

*Este material describe la mecánica del HDV para interoperabilidad. Su uso para automatización en servidores oficiales de Ankama infringe sus condiciones de uso. El refresco automático de precios y la manipulación de mercado son especialmente visibles para moderadores y otros jugadores.*
