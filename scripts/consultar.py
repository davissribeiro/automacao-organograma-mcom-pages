#!/usr/bin/env python3
"""Le os ZIPs do DOU baixados, acha os atos do MCom e gera a proposta de mudancas.

Uso: python consultar.py [--zips zips] [--estrutura dados/estrutura.json] [--resp data/responsaveis.json]
                         [--estado dados/estado.json] [--saida propostas] [--desde AAAA-MM-DD]
Nao altera nada do organograma: so grava propostas/pendente.json e pendente.txt (quando ha novidade).
"""
import argparse, glob, json, os, re, sys, zipfile
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
import dou


def ler_zips(pasta):
    atos, total, ultimo = {}, 0, None
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.zip")))
    if not arquivos:
        sys.exit("ERRO: nenhum ZIP em %s. O download falhou." % pasta)
    for z in arquivos:
        with zipfile.ZipFile(z) as zf:
            for nome in zf.namelist():
                if not nome.lower().endswith(".xml"):
                    continue
                dados = zf.read(nome)
                total += 1
                m = re.search(rb'pubDate="(\d\d/\d\d/\d{4})"', dados[:2000])
                if m:
                    d = datetime.strptime(m.group(1).decode(), "%d/%m/%Y").date()
                    if ultimo is None or d > ultimo:
                        ultimo = d
                if "ministério das comunicações" not in dados.decode("utf-8", "ignore").lower():
                    continue
                ato = dou.ler_ato(dados)
                if ato:
                    atos[ato["id"]] = ato
    return list(atos.values()), total, ultimo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zips", default="zips")
    ap.add_argument("--estrutura", default="dados/estrutura.json")
    ap.add_argument("--resp", default="data/responsaveis.json")
    ap.add_argument("--estado", default="dados/estado.json")
    ap.add_argument("--saida", default="propostas")
    ap.add_argument("--desde", default="")
    a = ap.parse_args()

    estado = json.load(open(a.estado, encoding="utf-8"))
    ini = datetime.strptime(a.desde or estado["atualizado_ate"], "%Y-%m-%d").date()
    nos = dou.estado_atual(dou.carregar_estrutura(a.estrutura), dou.carregar_responsaveis(a.resp))

    atos, total, ultimo = ler_zips(a.zips)
    if ultimo is None:
        sys.exit("ERRO: não consegui ler a data dos atos.")
    fim = max(ini, ultimo - timedelta(days=1))
    na_janela = [x for x in atos if x["data"] >= ini]
    ignorados = set(estado.get("ignorados", []))
    mudancas, ledger, revisar = dou.simular(nos, na_janela, ignorados)

    print(f"Atos no DOU (Seção 2): {total} | do MCom ou que citam o MCom: {len(atos)} | "
          f"na janela {dou.data_br(ini)}→{dou.data_br(ultimo)}: {len(na_janela)}")
    print(f"Chefias lidas: {len(ledger)} | mudanças: {len(mudancas)} | para revisão: {len(revisar)}")

    base = estado.get("base", "")
    texto = dou.relatorio(mudancas, ledger, revisar, ini, ultimo, base)
    os.makedirs(a.saida, exist_ok=True)
    detalhe = [texto, "", "AUDITORIA — todas as chefias lidas na janela"]
    for e in ledger:
        detalhe.append(f"{e['data']} | {e['verbo']:8s} | {e['pessoa']} | {e['cargo']} {e['codigo']} | {e['no'] or '-'} | {e['resultado']}")
    open(os.path.join(a.saida, "ultima_consulta.txt"), "w", encoding="utf-8").write("\n".join(detalhe))

    novo_hash = dou.hash_mudancas(mudancas)
    antigo = {}
    pj = os.path.join(a.saida, "pendente.json")
    if os.path.exists(pj):
        antigo = json.load(open(pj, encoding="utf-8"))
    mudou = bool(mudancas) and antigo.get("hash") != novo_hash
    if mudou or (not mudancas and antigo.get("mudancas")):
        json.dump({"gerado_em": date.today().isoformat(), "janela_inicio": ini.isoformat(), "janela_fim": fim.isoformat(), "ultimo_dia_lido": ultimo.isoformat(),
                   "hash": novo_hash, "mudancas": mudancas, "revisar": revisar,
                   "sem_unidade": [e for e in ledger if e["resultado"].startswith("sem unidade")]}, open(pj, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        open(os.path.join(a.saida, "pendente.txt"), "w", encoding="utf-8").write(texto)
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a") as f:
            f.write(f"mudou={'true' if mudou else 'false'}\nqtd={len(mudancas)}\n")
    print("Novidade a notificar." if mudou else "Sem novidade desde a última consulta.")


if __name__ == "__main__":
    main()
