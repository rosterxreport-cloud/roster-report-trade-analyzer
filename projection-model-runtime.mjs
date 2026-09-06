import { NEXT_SEASON_MODEL_V03 } from './projection-model-v0.3.mjs';

const finite = value => Number.isFinite(Number(value));

function standardizedValue(row, model, feature) {
  const mean = Number(model.means[feature] ?? 0);
  const std = Number(model.stds[feature] ?? 1) || 1;
  const value = finite(row?.[feature]) ? Number(row[feature]) : mean;
  return (value - mean) / std;
}

export function predictNextPprPerGame(row, position, artifact = NEXT_SEASON_MODEL_V03) {
  const pos = String(position || row?.position || row?.pos || '').toUpperCase();
  const model = artifact?.models?.[pos];
  if (!model || !model.promoted) return null;

  let ridge = Number(model.intercept || 0);
  for (const feature of model.features || []) {
    ridge += standardizedValue(row, model, feature) * Number(model.coefficients?.[feature] || 0);
  }

  const baseline = finite(row?.ppr_per_game) ? Number(row.ppr_per_game) : ridge;
  const blend = Math.max(0, Math.min(1, Number(model.blendWeight ?? 1)));
  const prediction = baseline * (1 - blend) + ridge * blend;
  return Math.max(0, prediction);
}

export function historyConfidence(row) {
  const games = finite(row?.games) ? Number(row.games) : 0;
  return Math.max(0, Math.min(1, games / 12));
}

export function scoreProjectionFeatureRows(rows, artifact = NEXT_SEASON_MODEL_V03) {
  return (rows || []).map(row => ({
    ...row,
    projected_next_ppr_per_game: predictNextPprPerGame(row, row?.position || row?.pos, artifact),
    history_confidence: historyConfidence(row)
  }));
}

export function getProjectionModelSummary(artifact = NEXT_SEASON_MODEL_V03) {
  return Object.fromEntries(Object.entries(artifact.models || {}).map(([pos, model]) => [pos, {
    promoted: Boolean(model.promoted),
    selectedModel: model.selectedModel,
    blendWeight: model.blendWeight,
    validation: model.validation
  }]));
}
