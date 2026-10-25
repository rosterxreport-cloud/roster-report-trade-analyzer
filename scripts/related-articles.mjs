export function relatedArticles(player, articles, esc) {
  const matches = articles.filter(a => a.players?.[player.name] && /^https:\/\/rosterxreport\.substack\.com\/p\/[a-z0-9-]+$/.test(a.url) && /^\d{4}-\d{2}-\d{2}$/.test(a.date))
    .sort((a,b) => Number(b.players[player.name] === 'featured') - Number(a.players[player.name] === 'featured') || b.date.localeCompare(a.date)).slice(0,3);
  if (!matches.length) return '';
  return `<section aria-label="Related Roster Report articles"><h2>Read more about ${esc(player.name)}</h2><ul>${matches.map(a => {
    const url = new URL(a.url);
    url.search = new URLSearchParams({utm_source:'toolkit',utm_medium:'referral',utm_campaign:'player_articles',utm_content:player.slug});
    return `<li><a href="${esc(url.href)}">${esc(a.title)}</a><br><small><time datetime="${a.date}">${a.date}</time> · ${a.players[player.name] === 'featured' ? 'Featured analysis' : 'Mentioned in this article'}</small></li>`;
  }).join('')}</ul></section>`;
}
