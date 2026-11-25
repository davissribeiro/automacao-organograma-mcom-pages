/* Gera o data/fotos.json a partir da página Quem é Quem do MCom.
   COMO USAR: abra https://www.gov.br/mcom/pt-br/acesso-a-informacao/institucional/quem-e-quem no Edge,
   expanda TODAS as áreas (Ministro, Gabinete, Secretaria-Executiva, Assessorias, etc.), role até o fim,
   aperte F12 > Console, cole este arquivo inteiro e dê Enter. O resultado vai para a área de transferência:
   cole no arquivo data/fotos.json do GitHub (lápis > apagar tudo > colar > Commit).
   (Se o Edge pedir, digite  allow pasting  e dê Enter antes de colar.) */
(function () {
  'use strict';
  const semAcento = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  /* Chave do nome: sem acento, minúsculas, só letras e espaços. O painel usa a MESMA regra. */
  const chave = s => semAcento(s).toLowerCase().replace(/\(.*?\)/g, ' ').replace(/[^a-z ]+/g, ' ').replace(/\s+/g, ' ').trim();
  const limparNome = s => String(s || '').replace(/\(.*?\)/g, ' ').replace(/\s+/g, ' ').replace(/[\s.]+$/, '').trim();

  function escolherFoto(origem, src, srcset) {
    const abs = u => { try { return new URL(u, origem).href; } catch (e) { return ''; } };
    if (!src || /user-icon|static\/media/i.test(src)) return '';      /* "Pessoa sem foto" */
    const cands = [];
    String(srcset || '').split(',').forEach(p => {
      const m = /^\s*(\S+)\s+(\d+)w\s*$/.exec(p);
      if (m) cands.push({ w: parseInt(m[2], 10), u: m[1] });
    });
    /* Se a foto que o próprio site exibe (src) tem entre 200 e 600 px, usa ela. Senão, a menor com 200 px ou mais. */
    const doSrc = cands.find(c => c.u === src);
    if (doSrc && doSrc.w >= 200 && doSrc.w <= 600) return abs(src);
    const boas = cands.filter(c => c.w >= 200).sort((a, b) => a.w - b.w);
    return abs(boas.length ? boas[0].u : src);
  }

  function montar(cartoes, origem, hoje) {
    const fotos = {}, semFoto = [], repetidos = [];
    cartoes.forEach(c => {
      const nome = limparNome(c.nome);
      if (!nome || /^\.*\s*vago\.*$/i.test(nome)) return;                /* cargo vago */
      const url = escolherFoto(origem, c.src, c.srcset);
      if (!url) { semFoto.push(nome); return; }
      const k = chave(nome);
      if (!k) return;
      if (fotos[k] && fotos[k].url !== url) repetidos.push(nome);
      fotos[k] = { nome: nome, url: url };
    });
    const ordenado = {};
    Object.keys(fotos).sort().forEach(k => { ordenado[k] = fotos[k]; });
    return { json: { versao: 1, gerado_em: hoje, fonte: 'Quem é Quem do MCom (gov.br)', fotos: ordenado }, semFoto: semFoto, repetidos: repetidos };
  }

  /* No Node (teste) exporta as funções; no navegador, executa. */
  if (typeof document === 'undefined') { if (typeof module !== 'undefined') module.exports = { chave, montar, escolherFoto }; return; }

  const cartoes = Array.from(document.querySelectorAll('article.person-card')).map(a => {
    const img = a.querySelector('.br-avatar img') || a.querySelector('img');
    const h = a.querySelector('h2 a') || a.querySelector('h2');
    return { nome: h ? h.textContent : '', src: img ? img.getAttribute('src') : '', srcset: img ? img.getAttribute('srcset') : '' };
  });
  if (!cartoes.length) { console.warn('[fotos] Nenhum cartão encontrado. Expanda as áreas e role a página antes de colar o script.'); return; }
  const hoje = new Date().toISOString().slice(0, 10);
  const r = montar(cartoes, location.origin, hoje);
  const texto = JSON.stringify(r.json, null, 1);
  try { copy(texto); } catch (e) { console.log(texto); }
  console.info('[fotos] ' + cartoes.length + ' cartões lidos; ' + Object.keys(r.json.fotos).length + ' com foto; sem foto: ' + r.semFoto.length +
    (r.semFoto.length ? ' (' + r.semFoto.join('; ') + ')' : '') + (r.repetidos.length ? '. ATENÇÃO nomes repetidos com fotos diferentes: ' + r.repetidos.join('; ') : '') +
    '. JSON copiado para a área de transferência.');
})();

