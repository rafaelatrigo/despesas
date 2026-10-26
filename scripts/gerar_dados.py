"""
Gera site/data/marketing.json a partir do Fluxo de Caixa do Grupo Carozzo.

Regras (as mesmas do bloco das abas DFC):
- Previsto e realizado fechado por mês: aba Base do fluxo (colunas de mês da linha 1),
  filtrando empresa (coluna "Nome empresa"), tipo "Operacional" e o grupo fechamento.
  Mês com linhas "Realizado" = mês fechado; senão usa as linhas "Orçado" como previsto.
- Realizado do mês em aberto: aba Realizado Semanal (colada da BASE TEMPLATE),
  Considera = S, conciliado S e N, DATA CAIXA do 1º dia do mês até o corte.
- Corte = sexta-feira anterior à data em Realizado Semanal!AY2.
- Empresa no Sienge: de-para da própria aba Realizado Semanal (colunas AU:AV).
Os dados são gravados CRIPTOGRAFADOS (AES-256-GCM, chave PBKDF2-SHA256) em
site/data/marketing.enc.json. A senha vem de scripts/senha.txt (não vai para o Git)
ou é pedida na tela. A página pede a mesma senha para abrir.
Uso:  python gerar_dados.py [caminho_do_fluxo.xlsx]   (padrão: scripts/caminho_fluxo.txt)
"""
import json, sys, datetime, pathlib
from collections import defaultdict
try:
    import openpyxl
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("Faltam bibliotecas. Rode:  python -m pip install openpyxl cryptography")
import os, base64, getpass

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
cfg = json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
local = AQUI / "caminho_fluxo.txt"     # arquivo local (não vai para o Git)
if len(sys.argv) > 1 and sys.argv[1].strip():
    arquivo = pathlib.Path(sys.argv[1].strip().strip('"'))
elif local.exists() and local.read_text(encoding="utf-8").strip():
    arquivo = pathlib.Path(local.read_text(encoding="utf-8").strip().strip('"'))
else:
    sys.exit("Informe o caminho do fluxo: crie scripts/caminho_fluxo.txt com o caminho completo do arquivo .xlsx\n"
             "(ou arraste o arquivo do fluxo em cima do atualizar_painel.bat)")
if not arquivo.exists():
    sys.exit(f"Arquivo do fluxo não encontrado: {arquivo}\nConfira o caminho em scripts/caminho_fluxo.txt")

def como_data(v):
    if isinstance(v, datetime.datetime): return v.date()
    if isinstance(v, datetime.date): return v
    if isinstance(v, (int, float)) and v > 30000:
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))
    if isinstance(v, str) and len(v) >= 10:
        try: return datetime.date.fromisoformat(v[:10])
        except ValueError: return None
    return None

def num(v):
    try: return float(v or 0)
    except (TypeError, ValueError): return 0.0

print(f"Lendo {arquivo.name} ...")
wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)

# ---------- Realizado Semanal ----------
ws = wb[cfg["aba_realizado"]]
linhas = ws.iter_rows(values_only=True)
cab = [str(c).strip() if c is not None else "" for c in next(linhas)]
ix = {nome: i for i, nome in enumerate(cab) if nome}
def col(nome):
    if nome not in ix: sys.exit(f"Coluna '{nome}' não encontrada na aba {cfg['aba_realizado']}")
    return ix[nome]
cI, cL, cAG, cAJ, cAP = col("DATA CAIXA"), col("NOME DA EMPRESA"), col("CONSIDERA"), col("VALOR_V3"), col("GRUPO FECHAMENTO")
cH, cR, cX, cO, cP, cG = col("CONCILIADO"), col("NOME_CREDOR"), col("CONTA DO PLANO FINANCEIRO"), col("TITULO"), col("PARCELA"), col("DESCRICAO")
cAU, cAV, cAY = col("Empresa (fluxo)"), col("Empresa (Sienge)"), col("Data atualização (preencher)")

regs, depara, data_atu = [], {}, None
for i, r in enumerate(linhas):
    r = list(r) + [None] * (len(cab) - len(r))
    if i == 0: data_atu = como_data(r[cAY])
    if r[cAU] and r[cAV]: depara[str(r[cAU]).strip()] = str(r[cAV]).strip()
    if r[cI] is None and r[cL] is None: continue
    regs.append(r)
if not data_atu: sys.exit("Preencha a data de atualização em Realizado Semanal!AY2")
corte = data_atu - datetime.timedelta(days=(data_atu.weekday() - 4) % 7 or 7)   # sexta anterior
mes_corte = corte.replace(day=1)
print(f"Data de atualização {data_atu:%d/%m/%Y} | corte {corte:%d/%m/%Y} | {len(regs)} linhas coladas")

grupos = {g["grupo_fechamento"]: g["nome"] for g in cfg["grupos"]}
emps = {e["empresa_fluxo"]: e["nome"] for e in cfg["empreendimentos"]}
sienge = {}
for ef in emps:
    if ef not in depara: sys.exit(f"Empresa '{ef}' sem de-para em {cfg['aba_realizado']}!AU:AV")
    sienge[depara[ef]] = ef

real_aberto = defaultdict(float)   # (empresa, grupo, 'AAAA-MM') -> gasto (positivo)
lanc = []
for r in regs:
    emp_s, grp = str(r[cL] or "").strip(), str(r[cAP] or "").strip()
    if emp_s not in sienge or grp not in grupos or str(r[cAG] or "").strip() != "S": continue
    d = como_data(r[cI])
    if not d or d < mes_corte: continue
    gasto = -num(r[cAJ])
    situ = "Programado" if d > corte else ("Conciliado" if str(r[cH]).strip() == "S" else "Não conciliado")
    if d <= corte: real_aberto[(sienge[emp_s], grp, f"{d:%Y-%m}")] += gasto
    lanc.append({"data": d.isoformat(), "empreendimento": emps[sienge[emp_s]], "grupo": grupos[grp],
                 "credor": (r[cR] or "").strip() if isinstance(r[cR], str) else (r[cR] or ""),
                 "conta": r[cX] or "", "titulo": f"{r[cO] or ''}/{r[cP] or ''}".strip("/"),
                 "valor": round(gasto, 2), "situacao": situ})

# ---------- Base (previsto e meses fechados) ----------
ws = wb[cfg["aba_base"]]
linhas = ws.iter_rows(values_only=True)
cab = list(next(linhas))
mes_cols = {}
for i, h in enumerate(cab):
    d = como_data(h)
    if d and d.year == cfg["ano"]: mes_cols[f"{d:%Y-%m}"] = i
bix = {str(h).strip(): i for i, h in enumerate(cab) if isinstance(h, str)}
bC, bB, bJ, bL = bix["Nome empresa"], bix["Tipo análise"], bix["Tipo"], bix["GRUPO FECHAMENTO"]
real_f, prev = defaultdict(float), defaultdict(float)
for r in linhas:
    e, g = r[bC], r[bL]
    if e not in emps or g not in grupos or r[bJ] != "Operacional": continue
    alvo = real_f if r[bB] == "Realizado" else prev
    for m, i in mes_cols.items():
        v = num(r[i])
        if v: alvo[(e, g, m)] += -v
wb.close()

meses = sorted(mes_cols)
serie = []
for e in emps:
    for g in grupos:
        for m in meses:
            k = (e, g, m)
            fechado = m < f"{mes_corte:%Y-%m}" and abs(real_f[k]) > 0.005
            item = {"empreendimento": emps[e], "grupo": grupos[g], "mes": m,
                    "previsto": round(prev[k], 2), "realizado": None, "status": "previsto"}
            if fechado or (m < f"{mes_corte:%Y-%m}" and abs(prev[k]) < 0.005):
                item.update(realizado=round(real_f[k], 2), status="fechado")
            elif m <= f"{mes_corte:%Y-%m}":
                item.update(realizado=round(real_aberto[k], 2), status="em andamento")
            serie.append(item)

saida = {"gerado_em": datetime.datetime.now().isoformat(timespec="minutes"),
         "data_atualizacao": data_atu.isoformat(), "corte": corte.isoformat(),
         "mes_atual": f"{mes_corte:%Y-%m}",
         "empreendimentos": list(emps.values()), "grupos": list(grupos.values()),
         "serie": serie, "lancamentos": sorted(lanc, key=lambda x: x["data"], reverse=True)}
# ---------- criptografia ----------
arq_senha = AQUI / "senha.txt"
senha = arq_senha.read_text(encoding="utf-8").strip() if arq_senha.exists() else ""
if not senha:
    senha = getpass.getpass("Senha do painel (não aparece ao digitar): ").strip()
if len(senha) < 12:
    sys.exit("Use uma senha com pelo menos 12 caracteres.")
ITER = 600_000
salt, iv = os.urandom(16), os.urandom(12)
chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(senha.encode("utf-8"))
ct = AESGCM(chave).encrypt(iv, json.dumps(saida, ensure_ascii=False).encode("utf-8"), None)
b64 = lambda b: base64.b64encode(b).decode("ascii")
pacote = {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b64(salt), "iv": b64(iv), "dados": b64(ct)}
destino = RAIZ / "site" / "data" / "marketing.enc.json"
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(json.dumps(pacote), encoding="utf-8")
aberto = RAIZ / "site" / "data" / "marketing.json"
if aberto.exists(): aberto.unlink()   # nunca publicar a versão sem criptografia

# resumo no terminal para conferência com o bloco do fluxo (R$ mil)
print(f"\nMês em andamento {mes_corte:%m/%Y} (R$ mil, gasto positivo):")
for s in serie:
    if s["mes"] == f"{mes_corte:%Y-%m}":
        print(f"  {s['empreendimento']:<26}{s['grupo']:<17} previsto {s['previsto']/1000:8.1f}   realizado {s['realizado']/1000:8.1f}")
print(f"\nOK: {destino}  ({len(lanc)} lançamentos)")
