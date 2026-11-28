// Staging-only signed scheduler relay. Permanent credentials never enter pg_net.
const projectUrl = Deno.env.get("SUPABASE_URL")!;
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const allowedRunner = "https://roster-report-trade-analyzer-git-feat-5550b3-the-roster-report.vercel.app/api/dfs-refresh/";
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {status, headers: {"Content-Type": "application/json", "Cache-Control": "no-store"}});
async function db(path: string, body: unknown, method = "POST") {
 const response = await fetch(projectUrl + "/rest/v1/" + path, {method, headers: {apikey: serviceKey, Authorization: "Bearer " + serviceKey, "Content-Type": "application/json", Prefer: "return=minimal"}, body: JSON.stringify(body), signal: AbortSignal.timeout(10000), redirect: "error"});
 if (!response.ok) throw Error("Private scheduler database request failed");
 const text = await response.text();
 return text ? JSON.parse(text) : null;
}
async function run(nonce: string, config: Record<string,string>) {
 try {
  const response = await fetch(allowedRunner, {method: "POST", headers: {Authorization: "Bearer " + config.runnerToken, "x-vercel-protection-bypass": config.bypass, "Content-Type": "application/json"}, body: "{}", redirect: "error", signal: AbortSignal.timeout(285000)});
  const text = await response.text();
  let receipt;
  try { receipt = text.length <= 65536 ? JSON.parse(text) : {state: "invalid-receipt"}; } catch { receipt = {state: "invalid-receipt"}; }
  await db("dfs_schedule_runs?nonce=eq." + nonce, {finished_at: new Date().toISOString(), status: response.ok ? "completed" : "failed", http_status: response.status, receipt}, "PATCH");
 } catch {
  await db("dfs_schedule_runs?nonce=eq." + nonce, {finished_at: new Date().toISOString(), status: "failed", receipt: {state: "failed", reason: "Private runner unavailable; existing expiry remains enforced"}}, "PATCH");
 }
}
Deno.serve(async (req: Request) => {
 if (req.method !== "POST") return json({error: "Unauthorized"}, 401);
 const time = req.headers.get("x-dfs-time") || "";
 const nonce = req.headers.get("x-dfs-nonce") || "";
 const signature = req.headers.get("x-dfs-signature") || "";
 if (!/^\d{10}$/.test(time) || Math.abs(Date.now()/1000 - Number(time)) > 90 || !/^[a-f0-9-]{36}$/.test(nonce) || !/^[a-f0-9]{64}$/.test(signature)) return json({error: "Unauthorized"}, 401);
 try {
  const config = await db("rpc/dfs_private_cron_config", {});
  if (!config.signingKey || !config.runnerToken || !config.bypass || config.runnerUrl !== allowedRunner) return json({error: "Staging scheduler unavailable"}, 503);
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", encoder.encode(config.signingKey), {name: "HMAC", hash: "SHA-256"}, false, ["verify"]);
  const bytes = Uint8Array.from(signature.match(/../g)!, pair => parseInt(pair, 16));
  if (!await crypto.subtle.verify("HMAC", key, bytes, encoder.encode(time + "." + nonce))) return json({error: "Unauthorized"}, 401);
  if (!await db("rpc/dfs_claim_cron_nonce", {p_nonce: nonce, p_time: Number(time)})) return json({error: "Replay or expired trigger"}, 409);
  await db("dfs_schedule_runs", {nonce, status: "running"});
  EdgeRuntime.waitUntil(run(nonce, config));
  return json({state: "accepted", nonce}, 202);
 } catch { return json({error: "Staging scheduler unavailable"}, 503); }
});
