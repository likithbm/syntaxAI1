// Tiny dependency-free syntax highlighter for yaml / typescript / json. Returns HTML-escaped markup.
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const span = (cls, s) => `<span class="tok-${cls}">${esc(s)}</span>`;

const TS_KEYWORDS = new Set(['import', 'from', 'as', 'export', 'class', 'extends', 'constructor', 'super', 'const', 'let', 'new', 'this', 'return', 'true', 'false', 'null', 'undefined', 'process', 'string']);

function highlightLine(line, lang) {
  if (lang === 'yaml') {
    const c = line.indexOf(' #');
    const isComment = /^\s*#/.test(line);
    if (isComment) return span('c', line);
    let body = c >= 0 ? line.slice(0, c) : line;
    const tail = c >= 0 ? span('c', line.slice(c)) : '';
    const m = body.match(/^(\s*(?:- )?)([A-Za-z0-9_.:/${}-]+)(:)(\s.*)?$/);
    if (m) {
      const val = m[4] || '';
      return esc(m[1]) + span('k', m[2]) + esc(m[3]) + colorValue(val) + tail;
    }
    return colorValue(body) + tail;
  }
  // typescript / json
  let out = '';
  const re = /(\/\/.*$)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_$][\w$]*)|([\s\S])/g;
  let m;
  while ((m = re.exec(line))) {
    if (m[1]) out += span('c', m[1]);
    else if (m[2]) out += span('s', m[2]);
    else if (m[3]) out += span('n', m[3]);
    else if (m[4]) {
      const w = m[4];
      if (lang === 'typescript' && TS_KEYWORDS.has(w)) out += span('k', w);
      else if (lang === 'typescript' && /^[A-Z]/.test(w)) out += span('t', w);
      else out += esc(w);
    } else out += esc(m[5]);
  }
  return out;
}

function colorValue(val) {
  if (!val) return '';
  return val.replace(/^(\s+)(.*)$/, (_, sp, v) => {
    if (/^(true|false|null|~)$/i.test(v)) return esc(sp) + span('n', v);
    if (/^-?\d+(\.\d+)?$/.test(v)) return esc(sp) + span('n', v);
    if (/^['"]/.test(v)) return esc(sp) + span('s', v);
    if (/^[|>]/.test(v)) return esc(sp) + span('t', v);
    return esc(sp) + span('s', v);
  });
}

export function highlight(code, lang) {
  if (lang === 'yaml' || lang === 'typescript' || lang === 'json') {
    return code.split('\n').map((l) => highlightLine(l, lang)).join('\n');
  }
  return esc(code);
}
