"""
Delays con distribución humana para evasión anti-bot.

La distribución ex-gaussiana (Gaussiana + exponencial) modela con precisión
los tiempos de reacción humanos: clustering cerca del valor modal con una
cola derecha natural de pausas ocasionales más largas.

Si scipy está instalado se usa exgauss; si no, fallback a uniforme (stdlib puro).

Valores empíricos de reacción humana en juegos:
  - Mediana global: ~273 ms  (81M clicks en HumanBenchmark)
  - Rango competitivo: 200-320 ms
  - Mínimo fisiológico: ~120 ms (no anticipatorio)

Lo que detectan los anti-cheat:
  - Varianza = 0 (macros exactos)
  - Ausencia de jitter de hardware (±1-3 ms de ruido)
  - Reacción < 100 ms de forma consistente
"""

import random
import time

try:
    from scipy.stats import exponnorm
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def _exgauss_ms(mu: float, sigma: float, tau: float) -> float:
    """
    Genera un tiempo ex-gaussiano en ms.
    mu    = centro de la campana (ms)
    sigma = desviación estándar de la componente Gaussiana (ms)
    tau   = media de la componente exponencial (ms) — controla la cola derecha
    """
    if _HAS_SCIPY:
        K = tau / sigma
        return float(exponnorm.rvs(K, loc=mu, scale=sigma))
    # Fallback stdlib: aproximación simple con normal + exponencial
    gaussian = random.gauss(mu, sigma)
    exponential = random.expovariate(1.0 / tau) if tau > 0 else 0
    return gaussian + exponential


def _add_hardware_jitter(ms: float) -> float:
    """±2 ms de ruido de hardware — los dispositivos físicos siempre tienen esto."""
    return ms + random.uniform(-2.0, 2.0)


def human_delay(base_ms: float = 300, jitter_pct: float = 0.3):
    """
    Delay humano con distribución ex-gaussiana centrada en base_ms.

    jitter_pct controla el ancho de la distribución:
      sigma = base_ms * jitter_pct * 0.4   (componente gaussiana)
      tau   = base_ms * jitter_pct * 0.6   (cola exponencial)

    Mínimo absoluto: 80 ms (debajo no es fisiológicamente realista).
    """
    sigma = base_ms * jitter_pct * 0.4
    tau   = base_ms * jitter_pct * 0.6
    ms    = _exgauss_ms(base_ms, sigma, tau)
    ms    = _add_hardware_jitter(ms)
    ms    = max(80.0, ms)  # mínimo fisiológico
    time.sleep(ms / 1000.0)


def think_delay():
    """
    Pausa de 'decisión difícil' (1-4 s con cola derecha).
    Simula que el jugador evalúa la situación — los bots nunca hacen esto
    correctamente porque siempre reaccionan en tiempo constante.
    """
    ms = _exgauss_ms(mu=1800, sigma=400, tau=600)
    ms = max(500.0, ms)
    time.sleep(ms / 1000.0)


def using_scipy() -> bool:
    """True si scipy está disponible (distribución ex-gaussiana real)."""
    return _HAS_SCIPY
