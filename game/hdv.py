"""
HDV (Hôtel de Vente) — automatización de venta y compra en el mercado.

Basado en docs/dofus-retro-148-hdv.md.

Flujo VENDER:
  1. Ir al mapa del HDV correcto (Navigator)
  2. Interactuar con PNJ (DialogManager)
  3. EHP — pedir precio medio del ítem
  4. Decidir precio según estrategia (config.HDV_PRICE_STRATEGY)
  5. ES  — poner en venta (con validación de lote OBLIGATORIA)
  6. EV  — salir

Flujo COMPRAR:
  1. EHT — seleccionar categoría
  2. EHl/EHS — buscar ítem
  3. EHB — comprar si precio ≤ umbral

Anti-detección: refrescos espaciados y aleatorios (human_delay).

IMPORTANTE: la actuación (abrir/cerrar HDV, confirmar) es por clicks en UI —
no inyectamos paquetes C→S. Este módulo gestiona ESTADO y LÓGICA DE DECISIÓN.
"""

from __future__ import annotations
import threading
from dataclasses import dataclass, field
from typing import Callable

import config
from utils.timing import human_delay


TAXA_PCT = 0.02   # Taxa de HDV unificado Dofus Retro 1.42+ = 2%


@dataclass
class HdvLot:
    item_uid: str    # ID del lote/objeto en venta
    model_id: str    # ID de plantilla
    qty: int         # 1, 10 ó 100
    price: int       # precio del lote


@dataclass
class HdvPriceInfo:
    model_id: str
    avg_price: int         # precio medio (EHP)
    lots: list[HdvLot] = field(default_factory=list)


class HdvManager:
    def __init__(self):
        self._price_info: dict[str, HdvPriceInfo] = {}  # model_id → info
        self._price_event = threading.Event()
        self._lots_event  = threading.Event()

        # Lotes propios en venta: model_id → lista de nuestros HdvLot activos.
        # Se puebla cuando el servidor confirma una venta (ESK) y se borra
        # cuando el mismo item_uid desaparece de la lista EHl (vendido).
        self._own_lots: dict[str, list[HdvLot]] = {}

        # Callbacks para acciones que requieren la UI (clicks)
        self.on_sell_ready:  Callable[[str, int, int], None] | None = None
        self.on_buy_ready:   Callable[[str, int], None] | None = None
        self.on_sell_ok:     Callable[[], None] | None = None
        self.on_sell_error:  Callable[[str], None] | None = None
        self.on_buy_ok:      Callable[[], None] | None = None
        self.on_buy_error:   Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Handlers de paquetes S→C
    # ------------------------------------------------------------------

    def handle_ehp(self, fields: list[str]):
        """EHP — precio medio. Formato: EHP<model_id>|<avg_price>"""
        if len(fields) < 2:
            return
        model_id = fields[0]
        try:
            avg = int(fields[1])
        except ValueError:
            return
        info = self._price_info.setdefault(
            model_id, HdvPriceInfo(model_id=model_id, avg_price=0))
        info.avg_price = avg
        print(f"[HDV] Precio medio model={model_id}: {avg} kamas")
        self._price_event.set()

    def handle_ehl_response(self, fields: list[str]):
        """EHl S→C — lotes de un ítem. Formato: EHl<model_id>|<uid>;<qty>;<price>|..."""
        if not fields:
            return
        model_id = fields[0]
        info = self._price_info.setdefault(
            model_id, HdvPriceInfo(model_id=model_id, avg_price=0))
        info.lots = []
        for f in fields[1:]:
            parts = f.split(";")
            if len(parts) < 3:
                continue
            try:
                lot = HdvLot(
                    item_uid=parts[0],
                    model_id=model_id,
                    qty=int(parts[1]),
                    price=int(parts[2]),
                )
                info.lots.append(lot)
            except ValueError:
                continue
        info.lots.sort(key=lambda l: l.price)
        print(f"[HDV] Lotes model={model_id}: {len(info.lots)} lotes")

        # Detectar lotes propios que ya se vendieron (no aparecen en EHl)
        own = self._own_lots.get(model_id, [])
        if own:
            active_uids = {lot.item_uid for lot in info.lots}
            sold = [l for l in own if l.item_uid not in active_uids]
            if sold:
                for s in sold:
                    print(f"[HDV] Lote propio vendido: uid={s.item_uid} qty={s.qty} price={s.price}")
                self._own_lots[model_id] = [l for l in own if l.item_uid in active_uids]

        self._lots_event.set()

    def handle_esk(self, fields: list[str]):
        """
        ESK — venta exitosa.
        Formato confirmado: ESK<item_uid>;<model_id>;<qty>;<price>
        Registramos el lote en _own_lots para no autocompetir.
        """
        print("[HDV] Venta confirmada (ESK)")
        # Parsear para registrar el lote propio recién puesto en venta
        if fields:
            parts = fields[0].split(";") if ";" in fields[0] else fields
            if len(parts) >= 4:
                try:
                    lot = HdvLot(
                        item_uid=parts[0],
                        model_id=parts[1],
                        qty=int(parts[2]),
                        price=int(parts[3]),
                    )
                    model_id = lot.model_id
                    self._own_lots.setdefault(model_id, []).append(lot)
                    print(f"[HDV] Lote propio registrado: uid={lot.item_uid} "
                          f"qty={lot.qty} price={lot.price}")
                except (ValueError, IndexError):
                    pass
        if self.on_sell_ok:
            self.on_sell_ok()

    def handle_ese(self, fields: list[str]):
        """ESE — error en venta."""
        reason = fields[0] if fields else "?"
        print(f"[HDV] Error en venta (ESE): {reason}")
        if self.on_sell_error:
            self.on_sell_error(reason)

    def handle_ebk(self, fields: list[str]):
        """EBK — compra exitosa."""
        print("[HDV] Compra confirmada (EBK)")
        if self.on_buy_ok:
            self.on_buy_ok()

    def handle_ebe(self, fields: list[str]):
        """EBE — error en compra."""
        reason = fields[0] if fields else "?"
        print(f"[HDV] Error en compra (EBE): {reason}")
        if self.on_buy_error:
            self.on_buy_error(reason)

    # ------------------------------------------------------------------
    # Lógica de decisión de precio
    # ------------------------------------------------------------------

    def already_selling(self, model_id: str, qty: int) -> HdvLot | None:
        """
        Devuelve el primer lote propio en venta del mismo model_id y qty,
        o None si no tenemos ninguno activo.
        """
        for lot in self._own_lots.get(str(model_id), []):
            if lot.qty == qty:
                return lot
        return None

    def compute_sell_price(self, model_id: str, qty: int) -> int | None:
        """
        Calcula el precio de venta según config.HDV_PRICE_STRATEGY.

        "middle_pct"  → precio_medio × config.HDV_MIDDLE_PCT  (recomendado)
        "-1kama"      → lote más barato - 1  (clásico, más firma de bot)
        "fixed"       → config.HDV_FIXED_PRICES[model_id]

        Devuelve el precio por LOT (ya ajustado por qty), o None si:
          - no hay datos suficientes, o
          - D1: ya tenemos un lote propio competitivo en venta (evitar auto-undercutting).

        D1 "Never undercut yourself":
          Si ya tenemos un lote del mismo ítem/qty en venta, comprobar si sigue
          siendo competitivo (dentro del TOP-3 más baratos del mercado). Si lo
          es, devuelve None para indicar "no pongas otro — espera a que el tuyo
          se venda". Si nuestro lote ya no es competitivo (hay varios más baratos
          que superan la posición), se calcula un nuevo precio para mover el stock.
        """
        model_id = str(model_id)
        info = self._price_info.get(model_id)
        strategy = getattr(config, "HDV_PRICE_STRATEGY", "middle_pct")

        # D1 — comprobar lote propio antes de calcular nuevo precio
        own_lot = self.already_selling(model_id, qty)
        if own_lot is not None and info is not None and info.lots:
            market_same_qty = sorted(
                [l for l in info.lots if l.qty == qty],
                key=lambda l: l.price,
            )
            # Posición de nuestro lote en el mercado (0-indexed)
            own_pos = next(
                (i for i, l in enumerate(market_same_qty)
                 if l.item_uid == own_lot.item_uid),
                len(market_same_qty),  # si ya no está, asumimos vendido
            )
            # Si nuestro lote está entre los 3 más baratos → no tocar
            if own_pos < 3:
                print(f"[HDV] D1: lote propio uid={own_lot.item_uid} "
                      f"en posición #{own_pos + 1} del mercado — omitiendo venta duplicada")
                return None
            # Si está fuera del top-3, calculamos precio nuevo para ser competitivos
            print(f"[HDV] D1: lote propio en pos #{own_pos + 1} — necesita actualización")

        if strategy == "middle_pct":
            if info is None or info.avg_price == 0:
                print(f"[HDV] Sin precio medio para model={model_id} — precio indeterminado")
                return None
            pct = getattr(config, "HDV_MIDDLE_PCT", 0.95)
            base = int(info.avg_price * pct)
            return max(1, base * qty)

        elif strategy == "-1kama":
            if info is None or not info.lots:
                return None
            same_qty_lots = [l for l in info.lots if l.qty == qty]
            if not same_qty_lots:
                return None
            cheapest = min(l.price for l in same_qty_lots)
            return max(1, cheapest - 1)

        elif strategy == "fixed":
            prices = getattr(config, "HDV_FIXED_PRICES", {})
            base = prices.get(model_id)
            if base is None:
                return None
            return base * qty

        return None

    def net_income(self, sell_price: int) -> int:
        """Ingreso neto tras descontar la taxa 2%."""
        return int(sell_price * (1 - TAXA_PCT))

    def validate_lot(self, qty: int) -> int:
        """
        Valida y normaliza el tamaño de lote a 1, 10 ó 100.
        CRÍTICO: un lote equivocado = pérdida directa de kamas.
        """
        if qty >= 100:
            return 100
        elif qty >= 10:
            return 10
        return 1

    # ------------------------------------------------------------------
    # Espera de respuestas de servidor (con timeout)
    # ------------------------------------------------------------------

    def wait_for_price(self, timeout: float = 5.0) -> bool:
        self._price_event.clear()
        return self._price_event.wait(timeout=timeout)

    def wait_for_lots(self, timeout: float = 5.0) -> bool:
        self._lots_event.clear()
        return self._lots_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # Registro de handlers
    # ------------------------------------------------------------------

    def register_handlers(self, dispatcher):
        from protocol.messages import EHP, EHl, ESK, ESE, EBK, EBE
        from protocol.dispatcher import DIRECTION_SERVER
        dispatcher.on(EHP, self.handle_ehp,          DIRECTION_SERVER)
        dispatcher.on(EHl, self.handle_ehl_response,  DIRECTION_SERVER)
        dispatcher.on(ESK, self.handle_esk,           DIRECTION_SERVER)
        dispatcher.on(ESE, self.handle_ese,           DIRECTION_SERVER)
        dispatcher.on(EBK, self.handle_ebk,           DIRECTION_SERVER)
        dispatcher.on(EBE, self.handle_ebe,           DIRECTION_SERVER)
        print("[HDV] Handlers registrados: EHP, EHl, ESK, ESE, EBK, EBE")


# Instancia global compartida
hdv = HdvManager()
