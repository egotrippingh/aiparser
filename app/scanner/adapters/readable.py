"""Read-only, link-aware text from provider answer DOM nodes."""

from __future__ import annotations

# The function only reads the supplied subtree.  ``raw`` fields intentionally
# retain the previous innerText representation for matching and LLM analysis.
SERIALIZE_JS = r"""(el, mode) => {
  const safeHref = element => {
    const raw = element.getAttribute('href');
    if (!raw || !raw.trim()) return '';
    try {
      const url = new URL(element.href);
      return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.href : '';
    } catch (_) { return ''; }
  };
  const hidden = node => !node || node.hidden || node.getAttribute('aria-hidden') === 'true' ||
    getComputedStyle(node).display === 'none' || ['hidden', 'collapse'].includes(getComputedStyle(node).visibility) || ['BUTTON', 'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(node.tagName);
  const clean = value => {
    const lines = []; let fence = '';
    for (const line of value.replace(/\r\n?/g, '\n').split('\n')) {
      if (/^[ \t]*`{3,}$/.test(line)) { fence = fence === line ? '' : fence || line; lines.push(line); continue; }
      if (fence) { lines.push(line); continue; }
      const prose = line.replace(/[ \t]+$/g, '');
      if (!prose && lines.at(-1) === '' && lines.at(-2) === '') continue;
      lines.push(prose);
    }
    return lines.join('\n').trim();
  };
  const raw = node => (node.innerText || '').trim();
  const serialize = (root, skipped = new Set()) => {
    // The supplied legacy example proves these text boundaries, not provider CSS.
    const lines = raw(root).split('\n'), review = 'Оставить отзыв';
    let boundary = null;
    if (/^[0-5][.,]\d$/.test(lines[0]?.trim()) && lines.some(line => line.trim() === 'Use two fingers to move the map') && lines.filter(line => line.trim() === review).length === 1 && lines.slice(lines.findIndex(line => line.trim() === review) + 1).some(line => line.trim())) {
      const nodes = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (nodes.nextNode()) if (nodes.currentNode.nodeValue.trim() === review) boundary = nodes.currentNode;
    }
    let afterMap = !boundary;
    const walk = (node, inCode = false) => {
      if (node === boundary) { afterMap = true; return ''; }
      if (node.nodeType === Node.TEXT_NODE) {
        if (!afterMap) return '';
        const value = node.nodeValue || '';
        if (inCode) return value;
        if (!value.trim() && [node.previousSibling, node.nextSibling].some(sibling => /^(P|DIV|LI|UL|OL|H[1-6]|PRE|SECTION|ARTICLE|ASIDE)$/.test(sibling?.tagName))) return '';
        return value.replace(/\s+/g, ' ');
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return '';
      if (hidden(node) || skipped.has(node)) { if (boundary && node.contains(boundary)) afterMap = true; return ''; }
      const tag = node.tagName;
      const code = inCode || tag === 'CODE' || tag === 'PRE';
      if (tag === 'TABLE' && !code && afterMap) {
        const rows = [...node.rows].filter(row => !hidden(row) && !hidden(row.parentElement));
        const cells = rows.map(row => [...row.cells].filter(cell => !hidden(cell) && !skipped.has(cell))).filter(row => row.length);
        if (!cells.length) return '';
        const rectangular = cells.every(row => row.length === cells[0].length && row.every(cell => cell.colSpan === 1 && cell.rowSpan === 1 && !cell.querySelector('table, pre') && ![...cell.querySelectorAll('code')].some(code => /[\r\n]/.test(code.textContent || ''))));
        const caption = node.caption && !hidden(node.caption) ? clean(walk(node.caption)) + '\n\n' : '';
        // ponytail: merged/nested cells retain row text; never guess their grid.
        if (!rectangular) return '\n' + caption + cells.map(row => row.map(cell => clean(walk(cell))).join('\n\n')).join('\n\n') + '\n';
        const values = cells.map(row => row.map(cell => clean(walk(cell)).replace(/[\r\n]+/g, ' ').replace(/\\/g, '\\\\').replace(/\|/g, '\\|')));
        const hasHeader = cells[0].every(cell => cell.tagName === 'TH');
        const header = hasHeader ? values.shift() : cells[0].map(() => '');
        const line = row => '| ' + row.join(' | ') + ' |';
        return '\n' + caption + [line(header), line(header.map(() => '---')), ...values.map(line)].join('\n') + '\n';
      }
      let body = [...node.childNodes].map(child => walk(child, code)).join('');
      if (tag === 'BR') return afterMap ? '\n' : '';
      if (!body.trim()) return '';
      if (tag === 'A' && !code) {
        const href = safeHref(node);
        return href ? `[${clean(body).replace(/\s+/g, ' ').replace(/[\\\[\]]/g, '\\$&')}](<${href}>)` : body;
      }
      if (tag === 'PRE' || (tag === 'CODE' && node.parentElement?.tagName !== 'PRE' && /[\r\n]/.test(body))) {
        const fence = '`'.repeat(Math.max(3, ...[...body.matchAll(/`+/g)].map(match => match[0].length + 1)));
        return '\n' + fence + '\n' + body + '\n' + fence + '\n';
      }
      if (tag === 'CODE' && node.parentElement?.tagName !== 'PRE') return '`' + body.replace(/\\/g, '\\\\').replace(/`/g, '\\`') + '`';
      if ((tag === 'STRONG' || tag === 'B') && !code) return '**' + clean(body) + '**';
      if (/^H[1-6]$/.test(tag)) return '\n' + '#'.repeat(+tag[1]) + ' ' + clean(body) + '\n';
      if (tag === 'LI') {
        const parent = node.parentElement;
        const ordered = parent?.tagName === 'OL';
        let number = 0;
        if (ordered) {
          number = +(parent.getAttribute('start') || 1);
          for (const item of [...parent.children].filter(child => child.tagName === 'LI')) {
            number = +(item.getAttribute('value') || number);
            if (item === node) break;
            number++;
          }
        }
        const content = clean(body);
        const leadingBlock = /^(?:`{3,}(?:\n|$)|\| |(?:[-*]|\d+\.) )/.test(content);
        return (ordered ? number + '. ' : '- ') + (leadingBlock ? '\n  ' : '') + content.replace(/\n/g, '\n  ') + '\n';
      }
      if (tag === 'UL' || tag === 'OL') return '\n' + clean(body) + '\n';
      return /^(P|DIV|SECTION|ARTICLE|UL|OL|BLOCKQUOTE)$/.test(tag) ? '\n' + body + '\n' : body;
    };
    return clean(walk(root));
  };
  if (mode === 'alice') {
    const markdown = [...el.querySelectorAll('.FuturisMarkdown')]
      .filter(node => !node.parentElement.closest('.FuturisMarkdown'));
    if (!markdown.length) return {main: raw(el), cards: '', display_main: serialize(el), display_cards: ''};
    const footnotes = [...el.querySelectorAll('.FuturisFootnote, .FuturisFootnoteGroup')]
      .filter(node => !node.parentElement.closest('.FuturisFootnote, .FuturisFootnoteGroup'))
      .filter(node => raw(node));
    let remaining = raw(el);
    const main = [];
    for (const node of markdown) {
      let value = raw(node);
      const position = remaining.indexOf(value);
      if (position >= 0) remaining = remaining.slice(0, position) + '\n' + remaining.slice(position + value.length);
      for (const footnote of footnotes) value = value.split(raw(footnote)).join(' ');
      main.push(value.replace(/[ \t]+/g, ' ').trim());
    }
    const cards = [remaining.replace(/\n{2,}/g, '\n').trim(), ...footnotes.map(raw)].filter(Boolean).join('\n');
    const displayCards = [serialize(el, new Set([...markdown, ...footnotes])), ...footnotes.map(node => serialize(node))].filter(Boolean).join('\n');
    return {main: main.join('\n\n'), cards, display_main: clean(markdown.map(node => serialize(node, new Set(footnotes))).join('\n\n')), display_cards: displayCards};
  }
  if (mode === 'google') {
    const visible = node => { const rect = node.getBoundingClientRect(); return rect.width > 0 && rect.height > 0; };
    const external = node => [...node.querySelectorAll('a[href^="http"]')].filter(anchor => !/(^|\.)google\./.test(anchor.hostname));
    const box = el.getBoundingClientRect();
    const candidates = [...el.querySelectorAll('[data-xid^="aim-aside"]')].filter(visible).concat(
      [...el.querySelectorAll('div, ul, section')].filter(visible).filter(node => {
        const rect = node.getBoundingClientRect();
        return rect.left > box.left + box.width * .45 && external(node).length >= 2;
      }),
    );
    const cards = candidates.filter((node, index) => candidates.indexOf(node) === index && !candidates.some(other => other !== node && other.contains(node)));
    let main = raw(el);
    const cardText = [];
    for (const node of cards) {
      const value = raw(node), position = main.indexOf(value);
      if (position < 0) continue;
      cardText.push(value);
      main = main.slice(0, position) + main.slice(position + value.length);
    }
    return {main, cards: cardText.join('\n\n'), display_main: serialize(el, new Set(cards)), display_cards: clean(cards.map(node => serialize(node)).join('\n\n'))};
  }
  return {raw: raw(el), display: serialize(el)};
}"""


async def readable(locator, mode: str = "plain") -> dict:
    return await locator.evaluate(SERIALIZE_JS, mode)
