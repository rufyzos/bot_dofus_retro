"""
Delays con distribución humana para evasión anti-bot.

DISTRIBUCIONES USADAS:
  - Ex-gaussiana (Gaussiana + exponencial): modela tiempos de reacción humanos.
    Clustering cerca del valor modal + cola derecha natural de pausas largas.
    Usa scipy si está disponible; sino fallback a Gamma (stdlib puro).

  - Gamma: alternativa stdlib sin scipy. Parámetros k (shape) y θ (scale)
    ajustados para que media = base_ms y varianza = (base_ms * jitter)².
    La Gamma tiene cola derecha asimétrica igual que la ex-gaussiana.

  - Drift de sesión: acumula fatiga a lo largo de la sesión desplazando
    lentamente la media de los delays hacia arriba, igual que un jugador
    cansado. El paper arXiv 2508.20578 confirma que la consistencia temporal
    es una señal primaria de detección de bots.

Lo que detectan los anti-cheat:
  - Varianza = 0 (macros exactos)
  - Delays con distribución simétrica o uniforme (no natural)
  - Ausencia de cola derecha (los humanos pausan ocasionalmente más)
  - Periocidad exacta entre acciones repetidas (intervalo constante)
  - Ausencia de descansos mid-sesión (los humanos paran ~cada 20-40 min)
"""

import math
import random
import time

try:
    from scipy.stats import exponnorm
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

# ── Estado de sesión (drift de fatiga) ───────────────────────────────────────
_session_start: float = time.monotonic()
_action_count:  int   = 0


def _gamma_ms(mean: float, cv: float = 0.35) -> float:
    """
    Muestrea de una distribución Gamma con media `mean` y coef. de variación `cv`.
    k = 1/cv²,  theta = mean * cv²
    cv≈0.35 produce una asimetría similar a la ex-gaussiana empírica humana.
    """
    k     = 1.0 / (cv * cv)
    theta = mean * cv * cv
    return random.gammavariate(k, theta)


def _exgauss_ms(mu: float, sigma: float, tau: float) -> float:
    """Ex-gaussiana en ms. Usa scipy si está disponible, sino Gamma."""
    if _HAS_SCIPY:
        K = tau / sigma
        return float(exponnorm.rvs(K, loc=mu, scale=sigma))
    # Fallback: Gamma calibrada para aproximar ex-gaussiana
    return _gamma_ms(mu + tau, cv=0.35)


def _hardware_jitter(ms: float) -> float:
    """±2 ms de ruido de hardware — los dispositivos físicos siempre tienen esto."""
    return ms + random.uniform(-2.0, 2.0)


def _fatigue_drift() -> float:
    """
    Factor multiplicador de fatiga de sesión (1.0 → 1.25 a lo largo de 2h).
    Los humanos se vuelven más lentos gradualmente. Los bots no.
    Progresión logarítmica: rápida al inicio, se estabiliza.
    """
    elapsed_min = (time.monotonic() - _session_start) / 60.0
    drift = 1.0 + 0.25 * math.log1p(elapsed_min / 30.0)
    return min(drift, 1.35)  # cap en +35%


def human_delay(base_ms: float = 300, jitter_pct: float = 0.3) -> float:
    """
    Delay humano con distribución ex-gaussiana/Gamma + drift de fatiga.

    - base_ms    : valor central en milisegundos
    - jitter_pct : ancho relativo de la distribución (0.30 = ±30%)

    Devuelve el tiempo dormido en segundos (útil para tests).
    Mínimo absoluto: 80 ms (debajo no es fisiológicamente realista).
    """
    global _action_count
    _action_count += 1

    # Aplicar drift de fatiga al valor base
    effective_base = base_ms * _fatigue_drift()

    sigma = effective_base * jitter_pct * 0.4
    tau   = effective_base * jitter_pct * 0.6
    ms    = _exgauss_ms(effective_base, sigma, tau)
    ms    = _hardware_jitter(ms)
    ms    = max(80.0, ms)

    # Micro-pausa ocasional (3% de probabilidad): simula distracción momentánea
    # Los humanos miran el chat, la pantalla, etc. Los bots nunca.
    if random.random() < 0.03:
        ms += random.uniform(800, 2500)

    time.sleep(ms / 1000.0)
    return ms / 1000.0


def think_delay() -> float:
    """
    Pausa de 'decisión difícil' (1-4 s con cola derecha).
    Simula que el jugador evalúa la situación antes de actuar.
    """
    ms = _exgauss_ms(mu=1800, sigma=400, tau=600)
    ms = _hardware_jitter(ms)
    ms = max(500.0, ms)
    time.sleep(ms / 1000.0)
    return ms / 1000.0


def session_break_if_due(
        min_interval_min: float = 18.0,
        max_interval_min: float = 42.0,
        min_break_s: float = 90.0,
        max_break_s: float = 480.0,
) -> bool:
    """
    Comprueba si toca un descanso mid-sesión y duerme si es así.

    El paper arXiv 2508.20578 (2025) confirma que la ausencia de descansos
    es una señal primaria de detección: los jugadores humanos paran ~cada
    20-40 min. Los bots no.

    Llámalo en bucles de navegación (entre mapas) o al terminar combates.
    Devuelve True si se hizo una pausa, False si no tocaba.

    Los parámetros son configurables desde config.py:
      BOT_BREAK_INTERVAL_MIN = (18, 42)   # minutos entre descansos
      BOT_BREAK_DURATION_S   = (90, 480)  # duración del descanso en segundos
    """
    import config as _cfg
    interval = getattr(_cfg, "BOT_BREAK_INTERVAL_MIN", (min_interval_min, max_interval_min))
    duration = getattr(_cfg, "BOT_BREAK_DURATION_S",   (min_break_s, max_break_s))

    now = time.monotonic()
    elapsed_min = (now - _session_start) / 60.0

    # El primer descanso ocurre en un momento aleatorio dentro del primer intervalo
    if not hasattr(session_break_if_due, "_next_break_min"):
        session_break_if_due._next_break_min = random.uniform(*interval)

    if elapsed_min >= session_break_if_due._next_break_min:
        break_s = random.uniform(*duration)
        print(f"[Timing] Descanso mid-sesión: {break_s:.0f}s "
              f"(sesión activa {elapsed_min:.1f} min, acción #{_action_count})")
        time.sleep(break_s)
        # Programar el siguiente descanso
        session_break_if_due._next_break_min = elapsed_min + random.uniform(*interval)
        return True

    return False


def using_scipy() -> bool:
    """True si scipy está disponible (distribución ex-gaussiana real)."""
    return _HAS_SCIPY
