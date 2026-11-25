#!/usr/bin/env python3
"""Baixa os ZIPs da Secao 2 do DOU (Base de Dados da Imprensa Nacional), sem navegador.

A pagina troca ano/mes recarregando com ?ano=AAAA e ?ano=AAAA&mes=NomeDoMes, e o download
so funciona com o cabecalho Referer apontando para a propria pagina (sem ele o site devolve 502).

Uso: python baixar_dou.py --auto            (mes atual; mais o anterior nos 7 primeiros dias do mes)
     python baixar_dou.py 112026 102026     (meses no formato MMAAAA)
Saida: zips/S02MMAAAA_NN.zip. Termina com erro se nenhum mes tiver ZIP valido.
"""
import sys, re, os, subprocess, html as H, time, urllib.parse, unicodedata
from datetime import datetime, timedelta, timezone

BASE = "https://www.in.gov.br"
PAGINA = BASE + "/acesso-a-informacao/dados-abertos/base-de-dados"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
MAX_POR_MES = 40


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def curl(url, saida, tentativas=3):
    cmd = ["curl", "-sS", "-L", "--max-time", "240", "-A", UA, "-e", PAGINA,
           "-H", "Accept: text/html,application/zip,application/octet-stream,*/*",
           "-H", "Accept-Language: pt-BR,pt;q=0.9", "-o", saida,
           "-w", "%{http_code}|%{content_type}|%{size_download}", url]
    ultimo = ("erro", "", 0)
    for i in range(tentativas):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=260)
            p = (r.stdout or "").split("|")
            ultimo = (p[0], p[1] if len(p) > 1 else "", int(p[2]) if len(p) > 2 and p[2].isdigit() else 0)
        except Exception as e:
            ultimo = ("erro", str(e)[:80], 0)
        if ultimo[0] in ("200", "404"):
            break
        time.sleep(5 * (i + 1))
    return ultimo


def ler(url, arq):
    cod, tipo, n = curl(url, arq)
    txt = open(arq, encoding="utf-8", errors="replace").read() if os.path.exists(arq) else ""
    return cod, tipo, n, txt


def opcoes(html, select_id):
    m = re.search(r'<select[^>]*id="%s"[^>]*>(.*?)</select>' % re.escape(select_id), html, re.S)
    if not m:
        return None
    out = []
    for om in re.finditer(r"<option([^>]*)>(.*?)</option>", m.group(1), re.S):
        t = H.unescape(re.sub(r"<[^>]+>", "", om.group(2))).strip()
        if t and "disabled" not in om.group(1) and norm(t) != "selecione":
            out.append(t)
    return out


def links_zip(html, cod, secao="S02"):
    achados = []
    for m in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', html):
        h = H.unescape(m.group(1))
        if re.search(r"%s%s" % (secao, cod), h, re.I) and ".zip" in h.lower():
            if h.startswith("/"):
                h = BASE + h
            if "download=true" not in h:
                h += ("&" if "?" in h else "?") + "download=true"
            if h not in achados:
                achados.append(h)
    return achados


def stamp(h):
    m = re.search(r"[?&]t=(\d+)", h)
    return int(m.group(1)) if m else 0


def candidatos_mes(mm, opts):
    nome = MESES[int(mm) - 1]
    out = []
    for o in (opts or []):
        if norm(o) == norm(nome) or o.lstrip("0") == str(int(mm)):
            out.append(o)
    for c in (nome, str(int(mm)), mm):
        if c not in out:
            out.append(c)
    return out


def processar(cod):
    mm, aaaa = cod[:2], cod[2:]
    print(f"\n===== {cod} (mes {mm}, ano {aaaa}) =====")
    for d in ("zips", "paginas"):
        os.makedirs(d, exist_ok=True)
    u1 = f"{PAGINA}?ano={aaaa}"
    c, t, n, h1 = ler(u1, f"paginas/ano_{aaaa}.html")
    print(f"[1] {u1} -> HTTP {c} | {n} bytes")
    ops = opcoes(h1, "mes-dados")
    todos = links_zip(h1, cod)
    if not todos:
        for cand in candidatos_mes(mm, ops):
            u2 = f"{PAGINA}?ano={aaaa}&mes={urllib.parse.quote(cand)}"
            c, t, n, h2 = ler(u2, f"paginas/{cod}.html")
            ls = links_zip(h2, cod)
            print(f"[2] mes={cand!r}: HTTP {c} | {n} bytes | links S02{cod}: {len(ls)}")
            if ls:
                todos = ls
                break
    if not todos:
        print(f"NENHUM link S02{cod} encontrado.")
        return 0
    todos.sort(key=stamp, reverse=True)
    ok = 0
    for i, l in enumerate(todos[:MAX_POR_MES], 1):
        arq = f"zips/S02{cod}_{i:02d}.zip"
        c, t, n = curl(l, arq)
        valido = subprocess.run(["unzip", "-tq", arq], capture_output=True).returncode == 0
        print(f"   link {i}: HTTP {c} | {n} bytes | {'ZIP VALIDO' if valido else 'ignorado (nao e ZIP)'}")
        if valido:
            ok += 1
        elif os.path.exists(arq):
            os.remove(arq)
    return ok


def meses_auto():
    agora = datetime.now(timezone.utc) - timedelta(hours=3)
    lista = [agora.strftime("%m%Y")]
    if agora.day <= 7:
        ant = agora.replace(day=1) - timedelta(days=1)
        lista.append(ant.strftime("%m%Y"))
    return lista


if __name__ == "__main__":
    args = sys.argv[1:]
    meses = meses_auto() if (not args or args == ["--auto"]) else args
    print("Meses:", " ".join(meses))
    resultados = [(m, processar(m)) for m in meses]
    print("\nZIPs validos por mes:", ", ".join(f"{m}={n}" for m, n in resultados))
    if all(n == 0 for _, n in resultados):
        sys.exit("ERRO: nenhum ZIP valido baixado (" + " ".join(m for m, _ in resultados) + ").")
