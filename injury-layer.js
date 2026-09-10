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
    const combinedMultiplier = availability * workload * longTermRisk;
    const baseValue = Number(player.value ?? 0);

    return {
      ...player,
      preInjuryValue: player.preInjuryValue ?? baseValue,
      injuryAdjustment: {
        availability,
        workload,
        longTermRisk,
        combinedMultiplier,
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
