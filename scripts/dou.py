#!/usr/bin/env python3
"""Biblioteca da automacao do organograma do MCom.

Le os atos do DOU (XML da Secao 2), separa os que trocam o responsavel de uma
unidade do organograma e calcula a diferenca em relacao ao estado atual
(dados/estrutura.json + data/responsaveis.json). Quem grava o resultado e o aplicar.py.
"""
import os
import re
import json
import html as _html
import hashlib
import difflib
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

MCOM = "Ministério das Comunicações"
VINCULADAS = ("Agência Nacional", "Empresa Brasileira", "Telecomunicações Brasileiras")
STOP = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na"}
PARTICULAS = {"de", "da", "do", "das", "dos", "e"}


# ---------------------------------------------------------------- textos
def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def chave_unidade(s):
    t = re.sub(r"[^a-z0-9 ]+", " ", sem_acento(s).lower())
    return " ".join(w for w in t.split() if w not in STOP)


def chave_nome(s):
    t = re.sub(r"[^a-z ]+", " ", sem_acento(s).lower())
    return " ".join(t.split())


def mesma_pessoa(a, b):
    A, B = chave_nome(a), chave_nome(b)
    if not A or not B:
        return False
    if A == B:
        return True
    return difflib.SequenceMatcher(None, A, B).ratio() >= 0.9


def formatar_nome(caps):
    partes = []
    for i, w in enumerate(caps.strip().split()):
        w = w.lower()
        if i > 0 and w in PARTICULAS:
            partes.append(w)
        else:
            w = re.sub(r"(^|['\-])([^'\-])", lambda m: m.group(1) + m.group(2).upper(), w)
            partes.append(w)
    return " ".join(partes)


def data_br(d):
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------- estrutura e responsaveis (JSON)
def carregar_estrutura(caminho):
    """dados/estrutura.json: as unidades do organograma como estavam na Planilha de 21/07/2026."""
    obj = json.load(open(caminho, encoding="utf-8"))
    return {n["id"]: dict(n) for n in obj["nos"]}


def carregar_responsaveis(caminho):
    """data/responsaveis.json: so as unidades que mudaram depois da planilha (a pagina le este arquivo)."""
    if os.path.exists(caminho):
        obj = json.load(open(caminho, encoding="utf-8"))
        if isinstance(obj.get("unidades"), dict):
            return obj
    return {"versao": 1, "ate": "", "unidades": {}}


def estado_atual(nos_base, resp):
    """Estrutura da planilha com os responsaveis do JSON por cima."""
    nos = {i: dict(n) for i, n in nos_base.items()}
    for i, u in resp.get("unidades", {}).items():
        if i in nos and isinstance(u, dict) and isinstance(u.get("person"), str):
            nos[i]["person"] = u["person"]
    return nos


# ---------------------------------------------------------------- leitura dos atos
def _paragrafos(texto):
    t = re.sub(r"</p>|<br\s*/?>", "\n", texto or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    out = []
    for linha in t.split("\n"):
        linha = re.sub(r"\s+", " ", _html.unescape(linha).replace("\u00a0", " ")).strip()
        if linha:
            out.append(linha)
    return out


def ler_ato(dados):
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError:
        return None
    a = raiz if raiz.tag == "article" else raiz.find(".//article")
    if a is None:
        return None
    try:
        data = datetime.strptime(a.get("pubDate", ""), "%d/%m/%Y").date()
    except ValueError:
        return None
    ident = _paragrafos(a.findtext("body/Identifica") or "")
    return {
        "id": str(a.get("idMateria", "")),
        "data": data,
        "orgao": a.get("artCategory", ""),
        "tipo": a.get("artType", ""),
        "titulo": " ".join(ident)[:140],
        "paragrafos": _paragrafos(a.findtext("body/Texto") or ""),
    }


def escopo(ato):
    partes = ato["orgao"].split("/")
    if partes[0].strip() == MCOM:
        if len(partes) > 1 and partes[1].strip().startswith(VINCULADAS):
            return "vinculada"
        return "mcom"
    if MCOM.lower() in " ".join(ato["paragrafos"]).lower():
        return "citado"
    return "outro"


VERBO = re.compile(
    r"^(?:Art\.?\s*\d+\s*[º°]?\s*[\.\-–]?\s*|N[º°o]\s*[\d\.]+\s*[-–]\s*)?"
    r"(Nomear|Exonerar|Designar|Dispensar)\b[\s,]*(.*)$", re.I | re.S)
SUBST = re.compile(r"encargo|substitut[oa]s? eventua|substitui[cç][aã]o", re.I)
GRAT = re.compile(r"Gratifica[cç][aã]o", re.I)
SAI_ANTERIOR = re.compile(r"ficando\s+(?:exonerad|dispensad)[oa]", re.I)
CARGO_RE = re.compile(
    r"(?:Cargo Comissionado Executivo|Cargo em Comiss[aã]o|Fun[cç][aã]o Comissionada Executiva|"
    r"Fun[cç][aã]o Comissionada|Fun[cç][aã]o de Confian[cç]a|Cargo de Natureza Especial|cargo)\s+(?:d[eao]s?\s+)?"
    r"(.+?),\s*c[oó]digo\s+((?:CCE|FCE|DAS|FCPE|CNE)[\s\d\.\-]*\d)(.*)$", re.I | re.S)
NOME_RE = re.compile(r"([A-ZÀ-Ý][A-ZÀ-Ý'\.\- ]+?)\s*(?:,|\s+SIAPE|\s+CPF|\s+matr|\s+para\b|\s+d[oa]\s+(?:cargo|fun))")
CHEFIA_RE = re.compile(r"^(Chefe|Coordenador|Diretor|Subsecret|Secret[aá]ri|Ouvidor|Corregedor|Consultor|Gerente|Presidente)", re.I)


def _cadeia(cauda):
    c = re.split(r"\(Processo|,\s*ficando|\.\s|\.$", cauda)[0]
    c = re.sub(r"\bdeste Minist[eé]rio\b", "", c, flags=re.I).strip(" ,.")
    c = re.sub(r"^(?:d[aoe]s?|n[ao]s?)\s+", "", c, flags=re.I)
    partes = re.split(r",\s+(?:d[aoe]s?|n[ao]s?)\s+", c)
    return [p.strip(" ,.") for p in partes if p.strip(" ,.")]


def extrair_itens(paragrafos):
    itens = []
    for par in paragrafos:
        m = VERBO.match(par)
        if not m:
            continue
        verbo, resto = m.group(1).lower(), m.group(2)
        limpo = re.sub(r"\ba pedido\b\s*,?", " ", resto, flags=re.I)
        limpo = re.sub(r"\ba (?:contar|partir) de [^,]+,", " ", limpo, flags=re.I).lstrip(" ,")
        nm = NOME_RE.match(limpo)
        cm = CARGO_RE.search(limpo)
        item = {"verbo": verbo, "pessoa": formatar_nome(nm.group(1)) if nm else None,
                "cargo": None, "codigo": None, "cadeia": [], "texto": par[:320],
                "sai_anterior": bool(SAI_ANTERIOR.search(par)), "classe": "OUTRO"}
        if SUBST.search(par):
            item["classe"] = "SUBSTITUTO"
        elif GRAT.search(par) and not cm:
            item["classe"] = "GRATIFICACAO"
        elif cm:
            item["cargo"] = re.sub(r"\s+", " ", cm.group(1)).strip()
            item["codigo"] = re.sub(r"\s+", " ", cm.group(2)).strip()
            item["cadeia"] = _cadeia(cm.group(3))
            item["classe"] = "CHEFIA" if CHEFIA_RE.match(item["cargo"]) else "ASSESSORIA"
        itens.append(item)
    return itens


# ---------------------------------------------------------------- cargo -> unidade
REGRAS = [
    (r"^Secret[áa]ri[oa]-Executiv[oa] Adjunt[oa]$", "Secretário Executivo Adjunto"),
    (r"^Secret[áa]ri[oa]-Executiv[oa]$", "Secretaria-Executiva"),
    (r"^Coordenador[a]?-Geral\s+(?:d[eao]s?\s+)?(.+)$", r"Coordenação-Geral de \1"),
    (r"^Coordenador[a]?\s+(?:d[eao]s?\s+)?(.+)$", r"Coordenação de \1"),
    (r"^Diretor[a]?\s+(?:d[eao]s?\s+)?(Departamento\s.+)$", r"\1"),
    (r"^Subsecret[áa]ri[oa]\s+(?:d[eao]s?\s+)?(.+)$", r"Subsecretaria de \1"),
    (r"^Secret[áa]ri[oa]\s+(?:d[eao]s?\s+)?(.+)$", r"Secretaria de \1"),
    (r"^Chefe\s+(?:d[eao]s?\s+)?(.+)$", r"\1"),
]


def unidade_do_cargo(cargo):
    c = re.sub(r"\s+", " ", cargo or "").strip()
    for padrao, modelo in REGRAS:
        m = re.match(padrao, c, re.I)
        if m:
            return m.expand(modelo)
    return None


def localizar_no(nos, cargo, cadeia):
    """Devolve (id_do_no, confianca, observacao). id None = nao achou."""
    alvo = unidade_do_cargo(cargo)
    if not alvo:
        return None, None, "cargo sem regra de correspondência"
    k = chave_unidade(alvo)
    cands = [n for n in nos.values() if n.get("relation") != "vinculada" and chave_unidade(n["name"]) == k]
    if not cands:
        return None, None, "nenhuma unidade com esse nome no organograma"
    pai_ato = chave_unidade(cadeia[0]) if cadeia else ""

    def pai_confere(n):
        p = nos.get(n.get("parent"))
        if not p or p["id"] == "ministro" or not pai_ato:
            return True
        return chave_unidade(p["name"]) == pai_ato

    certos = [n for n in cands if pai_confere(n)]
    if len(certos) == 1:
        return certos[0]["id"], "alta", ""
    if len(cands) == 1:
        return cands[0]["id"], "média", "unidade superior do ato difere da do organograma"
    return None, None, "mais de uma unidade com esse nome"


# ---------------------------------------------------------------- simulacao
def _ordem(ato):
    i = ato["id"]
    return (ato["data"], int(i) if i.isdigit() else 0)


def simular(nos, atos, ignorados=()):
    estado = {i: (n.get("person") or "") for i, n in nos.items()}
    inicial = dict(estado)
    toques = {}      # no -> lista de atos que mexeram
    confianca = {}
    ledger, revisar = [], []
    for ato in sorted(atos, key=_ordem):
        if ato["id"] in ignorados:
            continue
        esc = escopo(ato)
        corpo = " ".join(ato["paragrafos"])
        itens = extrair_itens(ato["paragrafos"])
        ref = {"id": ato["id"], "data": data_br(ato["data"]), "titulo": ato["titulo"]}
        if esc == "mcom":
            if ato["tipo"].lower().startswith("retifica") and re.search(r"Nomear|Designar|Exonerar|Dispensar", corpo) \
                    and re.search(r"Coordenador|Chefe|Diretor|Secret", corpo):
                revisar.append({**ref, "motivo": "retificação que menciona cargo de chefia", "trecho": corpo[:300]})
            if re.search(r"Tornar sem efeito", corpo, re.I) and re.search(r"Nomear|Designar|Exonerar|Dispensar|Portaria", corpo) \
                    and not itens:
                revisar.append({**ref, "motivo": "ato torna sem efeito outra publicação", "trecho": corpo[:300]})
        elif esc == "citado":
            for it in itens:
                if it["classe"] == "CHEFIA" and MCOM.lower() in it["texto"].lower() or it["classe"] == "CHEFIA" and not it["cadeia"]:
                    revisar.append({**ref, "motivo": f"outro órgão ({ato['orgao'].split('/')[0]}) cita o MCom em ato de pessoal", "trecho": it["texto"]})
            continue
        if esc != "mcom":
            continue
        for it in itens:
            if it["classe"] != "CHEFIA":
                continue
            if not it["pessoa"]:
                revisar.append({**ref, "motivo": "chefia sem nome identificado", "trecho": it["texto"]})
                continue
            no, conf, obs = localizar_no(nos, it["cargo"], it["cadeia"])
            entrada = {**ref, "verbo": it["verbo"], "pessoa": it["pessoa"], "cargo": it["cargo"],
                       "codigo": it["codigo"], "no": no, "resultado": ""}
            if not no:
                entrada["resultado"] = "sem unidade no organograma: " + obs
                ledger.append(entrada)
                continue
            atual = estado[no]
            if it["verbo"] in ("nomear", "designar"):
                if mesma_pessoa(atual, it["pessoa"]):
                    entrada["resultado"] = "já refletido"
                else:
                    estado[no] = it["pessoa"]
                    entrada["resultado"] = "muda"
                    toques.setdefault(no, []).append(ref)
                    confianca[no] = conf if confianca.get(no) != "média" else "média"
                if it["sai_anterior"]:
                    for outro, pessoa in list(estado.items()):
                        if outro != no and mesma_pessoa(pessoa, it["pessoa"]):
                            estado[outro] = ""
                            toques.setdefault(outro, []).append(ref)
                            confianca.setdefault(outro, conf)
            else:
                if mesma_pessoa(atual, it["pessoa"]):
                    estado[no] = ""
                    entrada["resultado"] = "muda"
                    toques.setdefault(no, []).append(ref)
                    confianca[no] = conf if confianca.get(no) != "média" else "média"
                else:
                    entrada["resultado"] = "já refletido" if not atual else "ocupante atual é outra pessoa"
            ledger.append(entrada)
    mudancas = []
    for no, depois in estado.items():
        antes = inicial[no]
        if (antes or depois) and not (antes == depois or mesma_pessoa(antes, depois) and antes and depois):
            n = nos[no]
            atos_ref = []
            for r in toques.get(no, []):
                if r not in atos_ref:
                    atos_ref.append(r)
            mudancas.append({"no": no, "sigla": n["acronym"], "unidade": n["name"], "de": antes, "para": depois,
                             "confianca": confianca.get(no, "alta"), "topo": (n.get("level") or 0) <= 2,
                             "atos": atos_ref})
    def _k(m):
        d = m["atos"][0]["data"] if m["atos"] else "00/00/0000"
        return ("-".join(reversed(d.split("/"))), m["sigla"])
    mudancas.sort(key=_k)
    for i, m in enumerate(mudancas, 1):
        m["n"] = i
    return mudancas, ledger, revisar


def hash_mudancas(mudancas):
    base = "|".join(f"{m['no']}:{m['de']}>{m['para']}" for m in sorted(mudancas, key=lambda x: x["no"]))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- aplicar no JSON
def _iso(data_br_txt, padrao):
    m = re.match(r"^(\d\d)/(\d\d)/(\d{4})$", data_br_txt or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else padrao


def aplicar_no_json(resp, nos_base, nos_atual, mudancas, ate_iso):
    """Grava em resp as mudancas. Devolve (resp, aplicadas, puladas).
    Unidade que volta a ser igual a planilha sai do arquivo (a pagina ja a tem embutida)."""
    unidades = dict(resp.get("unidades", {}))
    aplicadas, puladas = [], []
    for m in mudancas:
        n = nos_atual.get(m["no"])
        if not n:
            puladas.append((m, "unidade não existe no organograma"))
            continue
        atual = n.get("person") or ""
        if not (atual == m["de"] or mesma_pessoa(atual, m["de"])):
            puladas.append((m, f"o estado atual da unidade é “{atual or '(vago)'}”, e não “{m['de'] or '(vago)'}”"))
            continue
        base = (nos_base.get(m["no"]) or {}).get("person") or ""
        if (not m["para"] and not base) or (m["para"] and base and mesma_pessoa(m["para"], base)):
            unidades.pop(m["no"], None)
        else:
            ult = max(m["atos"], key=lambda a: (_iso(a["data"], ""), a["id"])) if m["atos"] else None
            unidades[m["no"]] = {"person": m["para"], "sigla": m["sigla"],
                                 "desde": _iso(ult["data"], ate_iso) if ult else ate_iso,
                                 "ato": ult["id"] if ult else ""}
        n["person"] = m["para"]
        aplicadas.append(m)
    novo = {"versao": 1, "ate": ate_iso, "unidades": {k: unidades[k] for k in sorted(unidades)}}
    return novo, aplicadas, puladas


# ---------------------------------------------------------------- relatorio
def relatorio(mudancas, ledger, revisar, janela_ini, janela_fim, base_txt, aplicado=False, puladas=None):
    L = []
    L.append("RESPONSÁVEIS DO ORGANOGRAMA DO MCOM ATUALIZADOS COM ATOS DO DOU" if aplicado
             else "MUDANÇAS DO DOU AINDA NÃO APLICADAS NO ORGANOGRAMA DO MCOM")
    L.append(f"Atos do DOU lidos de {data_br(janela_ini)} até {data_br(janela_fim)}.")
    L.append(f"Base de comparação: {base_txt}")
    L.append("")
    if mudancas:
        L.append(f"{'MUDANÇAS APLICADAS' if aplicado else 'MUDANÇAS PENDENTES'} ({len(mudancas)})")
        L.append("")
        for m in mudancas:
            L.append(f"{m['n']}. {m['sigla']} — {m['unidade']}")
            L.append(f"   Antes:  {m['de'] or '(vago)'}")
            L.append(f"   Depois: {m['para'] or '(vago)'}")
            for a in m["atos"]:
                L.append(f"   Ato:    {a['titulo']} (DOU {a['data']}, id {a['id']})")
            nota = f"Confiança: {m['confianca']}"
            if m["confianca"] != "alta":
                nota += " — conferir se a unidade está certa"
            if m["topo"]:
                nota += " | unidade de topo: a foto é removida e o ramal é mantido"
            elif m["de"] and m["para"]:
                nota += " | a foto antiga é removida"
            L.append("   " + nota)
            L.append("")
    elif not puladas:
        L.append("Nenhuma mudança de responsável encontrada.")
        L.append("")
    if puladas:
        L.append(f"NÃO APLICADAS ({len(puladas)})")
        for m, motivo in puladas:
            L.append(f"- {m['sigla']}: {m['de'] or '(vago)'} → {m['para'] or '(vago)'} — {motivo}")
        L.append("")
    if revisar:
        L.append(f"PARA REVISÃO MANUAL ({len(revisar)})")
        for r in revisar:
            L.append(f"- {r['data']} | {r['titulo']} (id {r['id']}) — {r['motivo']}")
            L.append(f"    {r['trecho'][:220]}")
        L.append("")
    sem = [e for e in ledger if e["resultado"].startswith("sem unidade")]
    if sem:
        L.append(f"CHEFIAS QUE NÃO ACHARAM UNIDADE NO ORGANOGRAMA ({len(sem)})")
        for e in sem:
            L.append(f"- {e['data']} | {e['verbo']} {e['pessoa']} | {e['cargo']} {e['codigo']} — {e['resultado']}")
        L.append("")
    if aplicado:
        L.append("A página do organograma lê o arquivo data/responsaveis.json sozinha: não é preciso colar nada no Pages.")
        L.append("Para conferir: abra o organograma, F12 > Console e procure por [organograma].")
    else:
        L.append("Estas mudanças continuam pendentes e serão tentadas de novo na próxima consulta.")
    return "\n".join(L)
