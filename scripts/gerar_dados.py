"""
Gera os dados do painel Marketing e Stand (site/data/marketing.enc.json).

De onde vem cada número:
- PREVISTO: o Fluxo de Caixa modificado por último na pasta "pasta_fluxo" (config.json),
  aba Base, linhas "Orçado" do tipo Operacional, por empresa, grupo fechamento e mês.
- REALIZADO e LANÇAMENTOS: a BASE TEMPLATE BUDGET modificada por último na pasta
  "pasta_budget" (config.json), aba Realizado, com Considera = S, conciliado S e N,
  somando VALOR_V3 por DATA CAIXA.
  - Meses anteriores ao mês do corte: mês fechado, soma o mês inteiro.
  - Mês do corte: do dia 1 até o corte.
  - Títulos com data depois do corte aparecem como "Programado" e ficam fora do realizado.
- CORTE: a sexta-feira anterior ao dia em que o script roda.
  Para testar outra data:  python gerar_dados.py --data AAAA-MM-DD

Os dados são gravados CRIPTOGRAFADOS (AES-256-GCM, chave PBKDF2-SHA256).
A senha vem de scripts/senha.txt (não vai para o Git) ou é pedida na tela.
"""
import json, sys, datetime, pathlib, os, base64, getpass, fnmatch
from collections import defaultdict
try:
    import openpyxl
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("Faltam bibliotecas. Rode:  python -m pip install openpyxl cryptography")

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
arq_cfg = pathlib.Path(sys.argv[sys.argv.index("--config") + 1]) if "--config" in sys.argv else AQUI / "config.json"
cfg = json.loads(arq_cfg.read_text(encoding="utf-8-sig"))

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

def txt(v): return str(v).strip() if v is not None else ""

def mais_recente(pasta, padrao, aba):
    """Arquivo modificado por último na pasta que bate com o padrão e tem a aba exigida."""
    p = pathlib.Path(pasta)
    if not p.is_dir(): sys.exit(f"Pasta não encontrada: {pasta}\nConfira scripts/config.json")
    cands = [f for f in p.iterdir() if f.is_file() and not f.name.startswith("~$")
             and fnmatch.fnmatch(f.name.lower(), padrao.lower())]
    if not cands: sys.exit(f"Nenhum arquivo '{padrao}' em {pasta}")
    for f in sorted(cands, key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except Exception as e:
            print(f"  (ignorado {f.name}: não abriu - {e})"); continue
        if aba in wb.sheetnames:
            return f, wb
        wb.close(); print(f"  (ignorado {f.name}: não tem a aba '{aba}')")
    sys.exit(f"Nenhum arquivo em {pasta} tem a aba '{aba}'")

# ---------- data de corte ----------
hoje = datetime.date.today()
if "--data" in sys.argv:
    hoje = datetime.date.fromisoformat(sys.argv[sys.argv.index("--data") + 1])
corte = hoje - datetime.timedelta(days=(hoje.weekday() - 4) % 7 or 7)   # sexta anterior
mes_corte = f"{corte:%Y-%m}"
ano = corte.year

grupos = {g["grupo_fechamento"]: g["nome"] for g in cfg["grupos"]}
emp_fluxo = {e["empresa_fluxo"]: e["nome"] for e in cfg["empreendimentos"]}
emp_sienge = {e["empresa_sienge"]: e["nome"] for e in cfg["empreendimentos"]}

# ---------- PREVISTO: fluxo de caixa mais recente ----------
print("Procurando o fluxo de caixa mais recente...")
f_fluxo, wb = mais_recente(cfg["pasta_fluxo"], cfg["padrao_fluxo"], cfg["aba_fluxo"])
print(f"  Previsto  <- {f_fluxo.name}  (modificado em {datetime.datetime.fromtimestamp(f_fluxo.stat().st_mtime):%d/%m/%Y %H:%M})")
linhas = wb[cfg["aba_fluxo"]].iter_rows(values_only=True)
cab = list(next(linhas))
mes_cols = {f"{d:%Y-%m}": i for i, h in enumerate(cab) if (d := como_data(h)) and d.year == ano}
bix = {txt(h): i for i, h in enumerate(cab) if isinstance(h, str)}
for c in ("Nome empresa", "Tipo análise", "Tipo", "GRUPO FECHAMENTO"):
    if c not in bix: sys.exit(f"Coluna '{c}' não encontrada na aba {cfg['aba_fluxo']} de {f_fluxo.name}")
bC, bB, bJ, bL = bix["Nome empresa"], bix["Tipo análise"], bix["Tipo"], bix["GRUPO FECHAMENTO"]
prev = defaultdict(float)
for r in linhas:
    e, g = txt(r[bC]), txt(r[bL])
    if e not in emp_fluxo or g not in grupos or txt(r[bJ]) != "Operacional" or txt(r[bB]) != "Orçado": continue
    for m, i in mes_cols.items():
        v = num(r[i])
        if v: prev[(emp_fluxo[e], grupos[g], m)] += -v
wb.close()

# ---------- REALIZADO: BASE TEMPLATE BUDGET mais recente ----------
print("Procurando a BASE TEMPLATE BUDGET mais recente...")
f_budget, wb = mais_recente(cfg["pasta_budget"], cfg["padrao_budget"], cfg["aba_budget"])
print(f"  Realizado <- {f_budget.name}  (modificado em {datetime.datetime.fromtimestamp(f_budget.stat().st_mtime):%d/%m/%Y %H:%M})")
print("  lendo a aba Realizado (pode levar 1-2 minutos)...")
linhas = wb[cfg["aba_budget"]].iter_rows(values_only=True)
cab = [txt(c) for c in next(linhas)]
ix = {n: i for i, n in enumerate(cab) if n}
def col(n):
    if n not in ix: sys.exit(f"Coluna '{n}' não encontrada na aba {cfg['aba_budget']} de {f_budget.name}")
    return ix[n]
cI, cL, cAG, cAJ, cAP = col("DATA CAIXA"), col("NOME DA EMPRESA"), col("CONSIDERA"), col("VALOR_V3"), col("GRUPO FECHAMENTO")
cH, cR, cX, cO, cP = col("CONCILIADO"), col("NOME_CREDOR"), col("CONTA DO PLANO FINANCEIRO"), col("TITULO"), col("PARCELA")
real = defaultdict(float); lanc = []; n_lidas = 0
for r in linhas:
    n_lidas += 1
    if len(r) <= max(cI, cL, cAG, cAJ, cAP): continue
    e, g = txt(r[cL]), txt(r[cAP])
    if e not in emp_sienge or g not in grupos or txt(r[cAG]) != "S": continue
    d = como_data(r[cI])
    if not d or d.year != ano: continue
    gasto = -num(r[cAJ]); m = f"{d:%Y-%m}"
    if d <= corte: real[(emp_sienge[e], grupos[g], m)] += gasto
    if m >= mes_corte:
        situ = "Programado" if d > corte else ("Conciliado" if txt(r[cH]) == "S" else "Não conciliado")
        lanc.append({"data": d.isoformat(), "empreendimento": emp_sienge[e], "grupo": grupos[g],
                     "credor": txt(r[cR]), "conta": txt(r[cX]),
                     "titulo": f"{txt(r[cO])}/{txt(r[cP])}".strip("/"),
                     "valor": round(gasto, 2), "situacao": situ})
wb.close()
print(f"  {n_lidas} linhas lidas")

# ---------- série mensal ----------
meses = sorted(mes_cols)
serie = []
for e in emp_fluxo.values():
    for g in grupos.values():
        for m in meses:
            k = (e, g, m)
            if m < mes_corte:   st = "fechado"
            elif m == mes_corte: st = "em andamento"
            else:               st = "previsto"
            serie.append({"empreendimento": e, "grupo": g, "mes": m, "previsto": round(prev[k], 2),
                          "realizado": None if st == "previsto" else round(real[k], 2), "status": st})

saida = {"gerado_em": datetime.datetime.now().isoformat(timespec="minutes"),
         "data_atualizacao": hoje.isoformat(), "corte": corte.isoformat(), "mes_atual": mes_corte,
         "fontes": {"previsto": f_fluxo.name, "realizado": f_budget.name},
         "empreendimentos": list(emp_fluxo.values()), "grupos": list(grupos.values()),
         "serie": serie, "lancamentos": sorted(lanc, key=lambda x: x["data"], reverse=True)}

# ---------- criptografia ----------
arq_senha = AQUI / "senha.txt"
senha = arq_senha.read_text(encoding="utf-8-sig").strip() if arq_senha.exists() else ""
if not senha:
    senha = getpass.getpass("Senha do painel (não aparece ao digitar): ").strip()
if len(senha) < 12:
    sys.exit("Use uma senha com pelo menos 12 caracteres.")
ITER = 600_000
salt, iv = os.urandom(16), os.urandom(12)
chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(senha.encode("utf-8"))
ct = AESGCM(chave).encrypt(iv, json.dumps(saida, ensure_ascii=False).encode("utf-8"), None)
b64 = lambda b: base64.b64encode(b).decode("ascii")
destino = RAIZ / "site" / "data" / "marketing.enc.json"
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(json.dumps({"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b64(salt),
                               "iv": b64(iv), "dados": b64(ct)}), encoding="utf-8")
aberto = RAIZ / "site" / "data" / "marketing.json"
if aberto.exists(): aberto.unlink()   # nunca publicar a versão sem criptografia

print(f"\nCorte: {corte:%d/%m/%Y} (sexta anterior a {hoje:%d/%m/%Y})")
print(f"Mês em andamento {corte:%m/%Y} (R$ mil, gasto positivo):")
for s in serie:
    if s["mes"] == mes_corte:
        print(f"  {s['empreendimento']:<26}{s['grupo']:<25} previsto {s['previsto']/1000:8.1f}   realizado {s['realizado']/1000:8.1f}")
print(f"\nOK: {destino}  ({len(lanc)} lançamentos)")
