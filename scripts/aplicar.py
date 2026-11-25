#!/usr/bin/env python3
"""Grava em data/responsaveis.json as mudancas de propostas/pendente.json.

Uso: python aplicar.py [--ids todas|1,3] [--ignorar-atos 24333468,...]
A pagina do organograma le data/responsaveis.json do GitHub; nao ha mais HTML para colar no Pages.
"""
import argparse, json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import dou


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estrutura", default="dados/estrutura.json")
    ap.add_argument("--resp", default="data/responsaveis.json")
    ap.add_argument("--pendente", default="propostas/pendente.json")
    ap.add_argument("--estado", default="dados/estado.json")
    ap.add_argument("--historico", default="dados/historico.json")
    ap.add_argument("--ids", default="todas")
    ap.add_argument("--ignorar-atos", default="")
    a = ap.parse_args()

    estado = json.load(open(a.estado, encoding="utf-8"))
    novos_ign = [x.strip() for x in a.ignorar_atos.replace(",", " ").split() if x.strip()]
    if novos_ign:
        estado["ignorados"] = sorted(set(estado.get("ignorados", [])) | set(novos_ign))
        print("Atos ignorados daqui para frente:", ", ".join(novos_ign))

    if not os.path.exists(a.pendente):
        json.dump(estado, open(a.estado, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Não há propostas pendentes.")
        return
    pend = json.load(open(a.pendente, encoding="utf-8"))
    todas = pend["mudancas"]
    quer = todas if a.ids.strip().lower() == "todas" else [m for m in todas if str(m["n"]) in set(a.ids.replace(",", " ").split())]
    quer = [m for m in quer if not any(x["id"] in novos_ign for x in m["atos"])]

    nos_base = dou.carregar_estrutura(a.estrutura)
    resp = dou.carregar_responsaveis(a.resp)
    nos_atual = dou.estado_atual(nos_base, resp)
    lido = datetime.strptime(pend.get("ultimo_dia_lido", pend["janela_fim"]), "%Y-%m-%d").date()
    novo, aplicadas, puladas = dou.aplicar_no_json(resp, nos_base, nos_atual, quer, lido.isoformat())
    for m, motivo in puladas:
        print(f"PULADA {m['n']} ({m['sigla']}): {motivo}")
    for m in aplicadas:
        print(f"OK {m['n']}: {m['sigla']}: {m['de'] or '(vago)'} -> {m['para'] or '(vago)'}")

    if any(i not in nos_base for i in novo["unidades"]):
        sys.exit("ERRO: o JSON ficou com uma unidade que não existe na estrutura. Nada foi gravado.")
    os.makedirs(os.path.dirname(a.resp) or ".", exist_ok=True)
    json.dump(novo, open(a.resp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if aplicadas:
        hist = json.load(open(a.historico, encoding="utf-8")) if os.path.exists(a.historico) else []
        hist.append({"aplicado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "mudancas": aplicadas})
        json.dump(hist, open(a.historico, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # aviso (vira a Issue que chega no seu e-mail)
    ini_aviso = datetime.strptime(pend["janela_inicio"], "%Y-%m-%d").date()
    pasta = os.path.dirname(a.pendente) or "."
    os.makedirs(pasta, exist_ok=True)
    open(os.path.join(pasta, "aviso.txt"), "w", encoding="utf-8").write(
        dou.relatorio(aplicadas, pend.get("sem_unidade", []), pend.get("revisar", []), ini_aviso, lido,
                      estado.get("base", ""), aplicado=True, puladas=puladas))
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a") as f:
            f.write(f"avisar=true\nqtd={len(aplicadas)}\n")

    ids_aplicados = {m["n"] for m in aplicadas}
    restantes = [m for m in todas if m["n"] not in ids_aplicados and not any(x["id"] in novos_ign for x in m["atos"])]
    if not restantes:
        estado["atualizado_ate"] = pend["janela_fim"]
        for nome in ("pendente.json", "pendente.txt"):
            f = os.path.join(pasta, nome)
            if os.path.exists(f):
                os.remove(f)
        print("Tudo resolvido. Próximas consultas leem a partir de", pend["janela_fim"])
    else:
        pend["mudancas"] = restantes
        pend["hash"] = dou.hash_mudancas(restantes)
        json.dump(pend, open(a.pendente, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(os.path.join(pasta, "pendente.txt"), "w", encoding="utf-8").write(
            dou.relatorio(restantes, [], pend.get("revisar", []), ini_aviso, lido, estado.get("base", "")))
        print(f"Ainda pendentes: {len(restantes)} (a data-base do estado não avança).")
    json.dump(estado, open(a.estado, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
