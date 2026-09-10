(() => {
  const nativeFetch = window.fetch.bind(window);
  let adjustmentPromise = null;

  function loadAdjustments() {
    if (!adjustmentPromise) {
      adjustmentPromise = nativeFetch('injury-adjustments.json', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : { players: {} })
        .catch(() => ({ players: {} }));
    }
    return adjustmentPromise;
  }

  function clamp(n, min = 0, max = 1) {
    return Math.max(min, Math.min(max, Number(n)));
  }

  function applyAdjustment(player, adj) {
    if (!adj) return player;

    const availability = clamp(adj.availability ?? 1);
    const workload = clamp(adj.workload ?? 1);
    const longTermRisk = clamp(adj.longTermRisk ?? 1);

    // Softer injury model: blend the three risk signals instead of multiplying
    // them together. Availability matters most, workload second, long-term risk
    // third. This prevents moderate concerns from compounding into an excessive
    // trade-value penalty while preserving large discounts for true absences.
    const weightedMultiplier =
      (availability * 0.50) +
      (workload * 0.30) +
      (longTermRisk * 0.20);

    // For ordinary injury situations, cap the value reduction at 8%. Allow a
    // larger penalty only for players whose availability signal reflects a
    // genuine multi-game/IR/PUP-level absence (availability < 0.90).
    const floor = availability < 0.90 ? 0.84 : 0.92;
    const combinedMultiplier = clamp(weightedMultiplier, floor, 1);
    const baseValue = Number(player.value ?? 0);

    return {
      ...player,
      preInjuryValue: player.preInjuryValue ?? baseValue,
      injuryAdjustment: {
        availability,
        workload,
        longTermRisk,
        combinedMultiplier,
        weighting: { availability: 0.50, workload: 0.30, longTermRisk: 0.20 },
        status: adj.status ?? null,
        note: adj.note ?? null,
        expectedReturn: adj.expectedReturn ?? null,
        updatedAt: adj.updatedAt ?? null
      },
      value: Math.round(baseValue * combinedMultiplier * 100) / 100
    };
  }

  function applyToDatabase(db, adjustments) {
    const byName = adjustments?.players ?? {};
    const out = {};
    for (const [scoring, list] of Object.entries(db || {})) {
      out[scoring] = Array.isArray(list)
        ? list.map(player => applyAdjustment(player, byName[player.name]))
        : list;
    }
    return out;
  }

  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : input?.url || '';
    const response = await nativeFetch(input, init);

    if (!/\bplayers\.json(?:\?|$)/.test(url)) return response;

    try {
      const [db, adjustments] = await Promise.all([
        response.clone().json(),
        loadAdjustments()
      ]);
      const adjusted = applyToDatabase(db, adjustments);
      return new Response(JSON.stringify(adjusted), {
        status: response.status,
        statusText: response.statusText,
        headers: { 'Content-Type': 'application/json' }
      });
    } catch {
      return response;
    }
  };

  window.RosterReportInjuryLayer = {
    reload() {
      adjustmentPromise = null;
      return loadAdjustments();
    }
  };
})();
