// Preserve permanent profile links when the analyzer redraws ranking rows.
// Presentation only: do not read or modify ranking values or scoring state.
(() => {
  const rows = document.getElementById('rankingsRows');
  const source = document.getElementById('playerProfileSlugs');
  if (!rows || !source) return;
  let slugs;
  try { slugs = JSON.parse(source.textContent); } catch { return; }
  const linkNames = () => {
    for (const cell of rows.querySelectorAll('th[scope="row"]')) {
      const name = cell.textContent;
      const slug = Object.hasOwn(slugs, name) ? slugs[name] : null;
      if (typeof slug !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) continue;
      const href = `/players/${slug}/`;
      if (cell.firstElementChild?.getAttribute('href') === href) continue;
      const link = document.createElement('a');
      link.setAttribute('href', href);
      link.textContent = name;
      cell.replaceChildren(link);
    }
  };
  // Observe row replacements only. Linking a descendant cannot retrigger this.
  new MutationObserver(linkNames).observe(rows, { childList: true });
  linkNames();
})();
