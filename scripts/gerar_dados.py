"""
Gera os dados do painel "Acompanhamento de despesas" (pasta site/data).

De onde vem cada número:
- PREVISTO: o Fluxo de Caixa modificado por último em "pasta_fluxo" (config.json), aba Base,
  todas as linhas (como as fórmulas SOMASES das abas DFC), por empresa, grupo fechamento, tipo (Operacional/Financiamento) e mês
  (anos definidos em "anos" no config; "auto" = ano anterior, vigente e seguinte, ex.: 2025 a 2027).
- PREVISTO DO SISTEMA: para os meses em "previsto_sistema.meses" (ex.: 2026-11 e 2026-12), o previsto vem
  do relatório de previstos mais recente (aba Base Fluxo), no lugar do fluxo de caixa.
- REALIZADO e LANÇAMENTOS: a BASE TEMPLATE BUDGET modificada por último em "pasta_budget",
  aba Realizado, com Considera = S, conciliado S e N, somando VALOR_V3 por DATA CAIXA.
  - Realizado = CONCILIADO S com data caixa até hoje. "Realizado até" = último dia com título conciliado.
  - CONCILIADO N (ou data futura) aparece como "Programado" e fica fora do realizado.
  - Mês vigente: vira na primeira sexta-feira do mês novo.
  - Títulos em "titulos_liquidos" (config.json) entram pelo valor líquido: pagamento menos o desconto
    do próprio título (conta redutora), numa linha só, no grupo e na data do pagamento.
- CORTE: a sexta-feira mais recente, contando o próprio dia (rodou na sexta = a própria sexta;
  sábado a quinta = a sexta passada). Teste: --data AAAA-MM-DD

Três acessos, cada um com a sua senha e o seu arquivo criptografado:
- Líderes  (scripts/senha.txt)          -> site/data/lideres.enc.json   : os grupos de "grupos"
- Completo (scripts/senha_completo.txt) -> site/data/completo.enc.json  : os grupos + "grupos_completo" + a DRE inteira + a visão empresas
- Empresas (scripts/senha_empresas.txt) -> site/data/empresas.enc.json  : visão das empresas em config.json > "empresas"
  (Salários PJ em categoria própria, em qualquer grupo; demais grupos de despesa operacional em "Demais despesas")
Opções:  --se-mudou   só gera se a BASE TEMPLATE, o fluxo ou o corte mudaram (para o agendador)
"""
import json, sys, datetime, pathlib, os, base64, getpass, fnmatch, hashlib, re, unicodedata
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

def candidatos(pasta, padrao):
    p = pathlib.Path(pasta)
    if not p.is_dir(): sys.exit(f"Pasta não encontrada: {pasta}\nConfira scripts/config.json")
    c = [f for f in p.iterdir() if f.is_file() and not f.name.startswith("~$")
         and fnmatch.fnmatch(f.name.lower(), padrao.lower())]
    if not c: sys.exit(f"Nenhum arquivo '{padrao}' em {pasta}")
    return sorted(c, key=lambda f: f.stat().st_mtime, reverse=True)

def abrir_mais_recente(pasta, padrao, aba):
    for f in candidatos(pasta, padrao):
        try: wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except Exception as e:
            print(f"  (ignorado {f.name}: não abriu - {e})"); continue
        if aba in wb.sheetnames: return f, wb
        wb.close(); print(f"  (ignorado {f.name}: não tem a aba '{aba}')")
    sys.exit(f"Nenhum arquivo em {pasta} tem a aba '{aba}'")

# ---------- corte ----------
hoje = datetime.date.today()
if "--data" in sys.argv: hoje = datetime.date.fromisoformat(sys.argv[sys.argv.index("--data") + 1])
sexta = hoje - datetime.timedelta(days=(hoje.weekday() - 4) % 7)   # sexta mais recente (inclui hoje, se for sexta)
mes_corte = f"{sexta:%Y-%m}"     # MÊS VIGENTE: vira na primeira sexta-feira do mês novo
corte = None                     # REALIZADO ATÉ: último dia com título conciliado (S) na BASE TEMPLATE, limitado a hoje
_anos = cfg.get("anos", "auto")
anos = ({sexta.year - 1, sexta.year, sexta.year + 1} if _anos == "auto" else set(_anos))   # auto: ano anterior, vigente e seguinte

# ---------- só roda se algo mudou (modo agendado) ----------
assinatura_arq = AQUI / ".assinatura"
if "--se-mudou" in sys.argv:
    f1 = candidatos(cfg["pasta_fluxo"], cfg["padrao_fluxo"])[0]
    f2 = candidatos(cfg["pasta_budget"], cfg["padrao_budget"])[0]
    _ps = cfg.get("previsto_sistema") or {}
    try: f3 = candidatos(_ps["pasta"], _ps["padrao"])[0] if _ps.get("meses") else None
    except SystemExit: f3 = None
    assin = hashlib.sha256(json.dumps([f1.name, f1.stat().st_mtime, f2.name, f2.stat().st_mtime, sexta.isoformat(), hoje.isoformat(),
                                       f3.name if f3 else None, f3.stat().st_mtime if f3 else None,
                                       arq_cfg.read_text(encoding="utf-8-sig")]).encode()).hexdigest()
    if assinatura_arq.exists() and assinatura_arq.read_text().strip() == assin:
        print(f"Sem alterações nas bases desde a última publicação ({f1.name} / {f2.name}). Nada a fazer.")
        sys.exit(0)

def gkey(nome):   # "8.2 COMERCIAL", "8.2. Comercial" e "8.2.COMERCIAL" viram a mesma chave
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", t)

def ordem_dre(g):   # "8.1. STAND" -> 8.1 ; "13. CSC" -> 13
    m = re.match(r"\s*(\d+(?:\.\d+)?)", g["grupo_fechamento"]); return float(m.group(1)) if m else 99
todos_grupos = sorted(cfg["grupos"] + cfg.get("grupos_completo", []), key=ordem_dre)
grupos = {gkey(g["grupo_fechamento"]): g["nome"] for g in todos_grupos}          # todos (acesso completo)
nomes_base = [g["nome"] for g in cfg["grupos"]]                              # só os dos líderes
emp_fluxo = {e["empresa_fluxo"]: e["nome"] for e in cfg["empreendimentos"]}
emp_sienge = {e["empresa_sienge"]: e["nome"] for e in cfg["empreendimentos"]}
linhas_dre = [l for l in cfg["dre"] if "soma" not in l]

# ---------- visão EMPRESAS (Carozzo Desenvolvimento, Altamente Rentável...) definida em config.json > "empresas" ----------
CE = cfg.get("empresas") or {}
emp2_fluxo = {e["empresa_fluxo"]: e["nome"] for e in CE.get("empresas", [])}
emp2_sienge = {e["empresa_sienge"]: e["nome"] for e in CE.get("empresas", [])}
grupos2 = {gkey(g["grupo_fechamento"]): g["nome"] for g in CE.get("grupos", [])}
fora2 = {gkey(g) for g in CE.get("grupos_fora", [])}               # receitas / rateios: não são despesa
pj2 = CE.get("salarios_pj") or {}
pj2_key = gkey(pj2.get("conta_contendo", "")) if pj2 else ""
demais2 = CE.get("demais", "Demais despesas")
cats2 = ([pj2["nome"]] if pj2 else []) + list(dict.fromkeys(grupos2.values())) + [demais2]
def cat_empresa(g, conta, tipo):
    """Categoria da visão empresas. Salários PJ vai para a categoria própria em qualquer grupo em que apareça."""
    if tipo != "Operacional": return None
    if pj2_key and pj2_key in gkey(conta): return pj2["nome"]
    if not g or g in fora2: return None
    return grupos2.get(g, demais2)
def linha_de(grupo, tipo):
    for l in linhas_dre:
        if l["tipo"] == tipo and (l["grupos"] == "*" or grupo in {gkey(x) for x in l["grupos"]}): return l["id"]
    return None

# ---------- PREVISTO: fluxo de caixa mais recente ----------
print("Procurando o fluxo de caixa mais recente...")
f_fluxo, wb = abrir_mais_recente(cfg["pasta_fluxo"], cfg["padrao_fluxo"], cfg["aba_fluxo"])
print(f"  Previsto  <- {f_fluxo.name}  (modificado em {datetime.datetime.fromtimestamp(f_fluxo.stat().st_mtime):%d/%m/%Y %H:%M})")
rows = wb[cfg["aba_fluxo"]].iter_rows(values_only=True)
cab = list(next(rows))
mes_cols = {f"{d:%Y-%m}": i for i, h in enumerate(cab) if (d := como_data(h)) and d.year in anos}
bix = {txt(h): i for i, h in enumerate(cab) if isinstance(h, str)}
for c in ("Nome empresa", "Tipo análise", "Tipo", "GRUPO FECHAMENTO"):
    if c not in bix: sys.exit(f"Coluna '{c}' não encontrada na aba {cfg['aba_fluxo']} de {f_fluxo.name}")
bC, bB, bJ, bL = bix["Nome empresa"], bix["Tipo análise"], bix["Tipo"], bix["GRUPO FECHAMENTO"]
bK = bix.get("Conta")
prev2 = defaultdict(float)      # visão empresas: (empresa, categoria, mes) -> gasto positivo
prev_g = defaultdict(float)     # (emp, grupo_nome, mes) -> gasto positivo
prev_d = defaultdict(float)     # (emp, linha_dre, mes) -> valor com sinal (entrada +, saída -)
tipo_grupo = defaultdict(lambda: defaultdict(int))   # grupo -> tipo (Operacional/Financiamento) visto no fluxo
for r in rows:
    e, g, tipo = txt(r[bC]), gkey(r[bL]), txt(r[bJ])
    if g and tipo: tipo_grupo[g][tipo] += 1
    if e in emp2_fluxo:
        c2 = cat_empresa(g, r[bK] if bK is not None else "", tipo)
        if c2:
            for m, i in mes_cols.items():
                v = num(r[i])
                if v: prev2[(emp2_fluxo[e], c2, m)] += -v
        continue
    if e not in emp_fluxo: continue   # todas as linhas da Base, como as fórmulas das abas DFC
    lid = linha_de(g, tipo)
    for m, i in mes_cols.items():
        v = num(r[i])
        if not v: continue
        if g in grupos and tipo == "Operacional": prev_g[(emp_fluxo[e], grupos[g], m)] += -v
        if lid: prev_d[(emp_fluxo[e], lid, m)] += v
wb.close()

# ---------- PREVISTO DO SISTEMA (relatório de previstos) para os meses definidos em config ----------
MESES_PT = {"janeiro":1,"fevereiro":2,"março":3,"marco":3,"abril":4,"maio":5,"junho":6,"julho":7,"agosto":8,
            "setembro":9,"outubro":10,"novembro":11,"dezembro":12}
f_prev, meses_sist = None, []
ps = cfg.get("previsto_sistema") or {}
if ps.get("meses"):
    print("Procurando o relatório de previstos do sistema mais recente...")
    try:
        f_prev, wbp = abrir_mais_recente(ps["pasta"], ps["padrao"], ps["aba"])
    except SystemExit as e:
        print(f"  AVISO: {e} -> meses {ps['meses']} continuam com o previsto do fluxo de caixa")
    if f_prev:
        print(f"  Previsto do sistema <- {f_prev.name}  (meses {', '.join(ps['meses'])})")
        rp = wbp[ps["aba"]].iter_rows(values_only=True)
        cabp = [txt(c) for c in next(rp)]
        colm = {}
        for i, h in enumerate(cabp):
            mm = re.match(r"([A-Za-zçÇ]+)\s*/\s*(\d{4})", h)
            if mm and mm.group(1).lower() in MESES_PT:
                k = f"{mm.group(2)}-{MESES_PT[mm.group(1).lower()]:02d}"
                if k in ps["meses"] and k not in colm: colm[k] = i
        meses_sist = sorted(colm)
        faltam = [m for m in ps["meses"] if m not in colm]
        if faltam: print(f"  AVISO: o relatório não tem os meses {faltam} -> ficam com o previsto do fluxo")
        iE, iG = cabp.index(ps.get("coluna_empresa", "Empresa")), cabp.index(ps.get("coluna_grupo", "Grupo Fechamento"))
        # zera o previsto do fluxo nesses meses para os empreendimentos do painel e põe o do sistema
        for dic in (prev_g, prev_d):
            for k in [k for k in dic if k[2] in colm]: del dic[k]
        n = 0
        for r in rp:
            if len(r) <= iG or not r[iE]: continue
            e = re.sub(r"^\s*\d+\s*-\s*", "", txt(r[iE]))          # "8 - CAROZZO WELLNESS ..." -> nome do Sienge
            if e not in emp_sienge: continue
            g = gkey(r[iG])
            cont = tipo_grupo.get(g)
            tipo = max(cont, key=cont.get) if cont else "Operacional"
            lid = linha_de(g, tipo)
            for m, i in colm.items():
                v = num(r[i])
                if not v: continue
                n += 1
                if g in grupos and tipo == "Operacional": prev_g[(emp_sienge[e], grupos[g], m)] += -v
                if lid: prev_d[(emp_sienge[e], lid, m)] += v
        wbp.close()
        print(f"  {n} valores do sistema aplicados")

# ---------- REALIZADO: BASE TEMPLATE BUDGET mais recente ----------
print("Procurando a BASE TEMPLATE BUDGET mais recente...")
f_budget, wb = abrir_mais_recente(cfg["pasta_budget"], cfg["padrao_budget"], cfg["aba_budget"])
print(f"  Realizado <- {f_budget.name}  (modificado em {datetime.datetime.fromtimestamp(f_budget.stat().st_mtime):%d/%m/%Y %H:%M})")
print("  lendo a aba Realizado (pode levar 1-2 minutos)...")
rows = wb[cfg["aba_budget"]].iter_rows(values_only=True)
cab = [txt(c) for c in next(rows)]
ix = {n: i for i, n in enumerate(cab) if n}
def col(n):
    if n not in ix: sys.exit(f"Coluna '{n}' não encontrada na aba {cfg['aba_budget']} de {f_budget.name}")
    return ix[n]
cI, cL, cAG, cAJ, cAP, cAM = (col("DATA CAIXA"), col("NOME DA EMPRESA"), col("CONSIDERA"), col("VALOR_V3"),
                              col("GRUPO FECHAMENTO"), col("TIPO FINANCEIRO"))
cH, cR, cX, cO, cP = col("CONCILIADO"), col("NOME_CREDOR"), col("CONTA DO PLANO FINANCEIRO"), col("TITULO"), col("PARCELA")
cRed = ix.get("REDUTORA")
real_g, real_d = defaultdict(float), defaultdict(float)
real2, lanc2 = defaultdict(float), []
# Títulos que entram pelo valor líquido (pagamento menos o desconto do próprio título), definidos em config.json
liq = {(txt(t.get("empresa")), txt(t["titulo"])): t for t in cfg.get("titulos_liquidos", [])}
pend = defaultdict(list)   # (empresa, título, parcela) -> linhas do título
# Títulos lançados numa empresa que devem aparecer em outra (ex.: pago pela Carozzo DI, mas é do Wellness): config.json > "titulos_realocados"
realoc = {(txt(t["empresa"]), txt(t["titulo"])): txt(t["para"]) for t in cfg.get("titulos_realocados", [])}
def lancar(r, valor, sufixo_conta=""):
    e = txt(r[cL]); d = como_data(r[cI])
    global corte
    realizado = txt(r[cH]) == "S" and d <= hoje          # realizado = conciliado S com data caixa até hoje
    situ = "Conciliado" if realizado else "Programado"   # conciliado N (ou data futura) = programado
    if realizado and (corte is None or d > corte): corte = d
    if e in emp2_sienge:     # visão empresas
        c2 = cat_empresa(gkey(r[cAP]), r[cX], txt(r[cAM]))
        if not c2: return
        if realizado: real2[(emp2_sienge[e], c2, f"{d:%Y-%m}")] += -valor
        lanc2.append({"data": d.isoformat(), "empreendimento": emp2_sienge[e], "grupo": c2, "credor": txt(r[cR]),
                      "conta": txt(r[cX]) + sufixo_conta, "titulo": f"{txt(r[cO])}/{txt(r[cP])}".strip("/"),
                      "valor": round(-valor, 2), "situacao": situ})
        return
    g, tipo, m, en = gkey(r[cAP]), txt(r[cAM]), f"{d:%Y-%m}", emp_sienge[e]
    if realizado:
        if g in grupos: real_g[(en, grupos[g], m)] += -valor
        if tipo == "Financiamento": real_d[(en, "financ", m)] += valor
        else:
            lid = linha_de(g, "Operacional")
            if lid: real_d[(en, lid, m)] += valor
    if g in grupos:   # todos os meses dos anos do config (o painel cruza tabela x gráfico)
        lanc.append({"data": d.isoformat(), "empreendimento": en, "grupo": grupos[g], "credor": txt(r[cR]),
                     "conta": txt(r[cX]) + sufixo_conta, "titulo": f"{txt(r[cO])}/{txt(r[cP])}".strip("/"),
                     "valor": round(-valor, 2), "situacao": situ})
lanc = []; n_lidas = 0; maxc = max(cI, cL, cAG, cAJ, cAP, cAM, cH, cR, cX, cO, cP, cRed or 0)
for r in rows:
    n_lidas += 1
    if len(r) <= maxc: r = tuple(r) + (None,) * (maxc + 1 - len(r))
    e = txt(r[cL])
    if realoc:
        _t = re.sub(r"\.0$", "", txt(r[cO]))
        if (e, _t) in realoc:
            r = list(r); r[cL] = realoc[(e, _t)]; r = tuple(r); e = r[cL]
    if (e not in emp_sienge and e not in emp2_sienge) or txt(r[cAG]) != "S": continue
    d = como_data(r[cI])
    if not d or d.year not in anos: continue
    tit = re.sub(r"\.0$", "", txt(r[cO]))
    if (e, tit) in liq or ("", tit) in liq:
        pend[(e, tit, txt(r[cP]))].append(r); continue
    lancar(r, num(r[cAJ]))
for (e, tit, parc), linhas in pend.items():
    # o desconto (conta redutora) é abatido do pagamento: entra uma linha só, no grupo e na data do pagamento
    principais = [r for r in linhas if cRed is None or txt(r[cRed]) != "S"] or linhas
    princ = max(principais, key=lambda r: abs(num(r[cAJ])))
    liquido = sum(num(r[cAJ]) for r in linhas)
    print(f"  Título {tit}/{parc} ({e}): {-num(princ[cAJ]):,.2f} pago - descontos = {-liquido:,.2f} considerado")
    lancar(princ, liquido, " (líquido do desconto)")
wb.close()
print(f"  {n_lidas} linhas lidas")

# ---------- séries ----------
meses = sorted(mes_cols)
if corte is None: corte = sexta
mes_real = f"{corte:%Y-%m}"
def status(m):   # fechado: antes do mês vigente; em andamento: mês vigente (e o mês do último conciliado, se já virou); previsto: futuro
    return "fechado" if m < mes_corte else ("em andamento" if m <= max(mes_corte, mes_real) else "previsto")
serie = [{"empreendimento": e, "grupo": g, "mes": m, "previsto": round(prev_g[(e, g, m)], 2),
          "realizado": None if status(m) == "previsto" else round(real_g[(e, g, m)], 2), "status": status(m)}
         for e in emp_fluxo.values() for g in grupos.values() for m in meses]
dre = [{"empreendimento": e, "linha": l["id"], "mes": m, "previsto": round(prev_d[(e, l["id"], m)], 2),
        "realizado": None if status(m) == "previsto" else round(real_d[(e, l["id"], m)], 2), "status": status(m)}
       for e in emp_fluxo.values() for l in linhas_dre for m in meses]
base = {"gerado_em": datetime.datetime.now().isoformat(timespec="minutes"),
        "data_atualizacao": hoje.isoformat(), "corte": corte.isoformat(), "mes_atual": mes_corte,
        "fontes": {"previsto": f_fluxo.name, "realizado": f_budget.name,
                   "previsto_sistema": f_prev.name if f_prev else None, "meses_sistema": meses_sist},
        "empreendimentos": list(emp_fluxo.values()), "grupos": list(grupos.values()),
        "serie": serie, "lancamentos": sorted(lanc, key=lambda x: x["data"], reverse=True)}
so_base = lambda lista: [x for x in lista if x["grupo"] in nomes_base]
serie2 = [{"empreendimento": e, "grupo": g, "mes": m, "previsto": round(prev2[(e, g, m)], 2),
           "realizado": None if status(m) == "previsto" else round(real2[(e, g, m)], 2), "status": status(m)}
          for e in emp2_fluxo.values() for g in cats2 for m in meses]
visao_empresas = {"unidade": "Empresa", "unidades": "Empresas", "empreendimentos": list(emp2_fluxo.values()),
                  "grupos": cats2, "grupos_base": cats2, "serie": serie2,
                  "lancamentos": sorted(lanc2, key=lambda x: x["data"], reverse=True), "dre": None}
pacotes = {"lideres": dict(base, perfil="lideres", grupos=[n for n in grupos.values() if n in nomes_base],
                           grupos_base=nomes_base, serie=so_base(serie), lancamentos=so_base(base["lancamentos"])),
           "completo": dict(base, perfil="completo", grupos_base=nomes_base, dre=dre,
                            dre_estrutura=[{k: v for k, v in l.items() if k in ("id", "nome", "soma", "pai", "antes")} for l in cfg["dre"]])}
if emp2_fluxo:
    pacotes["empresas"] = dict(base, perfil="empresas", **visao_empresas)
    pacotes["completo"]["visoes"] = {"empresas": visao_empresas}       # a Michelle vê as duas visões
# categorias que o acesso completo (Michelle) não vê, nas duas visões: config.json > "completo_ocultar" (a DRE fica inteira)
ocultar = set(cfg.get("completo_ocultar", []))
def _sem(pac):
    pac = dict(pac)
    for k in ("grupos", "grupos_base"): pac[k] = [g for g in pac[k] if g not in ocultar]
    for k in ("serie", "lancamentos"): pac[k] = [x for x in pac[k] if x["grupo"] not in ocultar]
    return pac
if ocultar:
    pacotes["completo"] = _sem(pacotes["completo"])
    if "visoes" in pacotes["completo"]:
        pacotes["completo"]["visoes"] = {k: _sem(v) for k, v in pacotes["completo"]["visoes"].items()}

# ---------- criptografia ----------
def ler_senha(nome, rotulo, obrigatoria):
    a = AQUI / nome
    s = a.read_text(encoding="utf-8-sig").strip() if a.exists() else ""
    if not s and obrigatoria: s = getpass.getpass(f"Senha de acesso {rotulo} (não aparece ao digitar): ").strip()
    if s and len(s) < 12: sys.exit(f"A senha em {nome} precisa ter pelo menos 12 caracteres.")
    return s
senhas = {"lideres": ler_senha("senha.txt", "dos líderes", True),
          "completo": ler_senha("senha_completo.txt", "completo (Michelle)", False),
          "empresas": ler_senha("senha_empresas.txt", "empresas", False)}
_us = [s_ for s_ in senhas.values() if s_]
if len(_us) != len(set(_us)):
    sys.exit("As senhas dos acessos (senha.txt, senha_completo.txt e senha_empresas.txt) precisam ser diferentes entre si.")
pasta_dados = RAIZ / "site" / "data"; pasta_dados.mkdir(parents=True, exist_ok=True)
b64 = lambda b: base64.b64encode(b).decode("ascii")
ITER = 600_000
for perfil, dados in pacotes.items():
    destino = pasta_dados / f"{perfil}.enc.json"
    if not senhas[perfil]:
        if destino.exists(): destino.unlink()
        print(f"  (acesso {perfil}: sem senha no arquivo de senha - não gerado)"); continue
    salt, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(senhas[perfil].encode("utf-8"))
    ct = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False).encode("utf-8"), None)
    destino.write_text(json.dumps({"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b64(salt),
                                   "iv": b64(iv), "dados": b64(ct)}), encoding="utf-8")
for antigo in ("marketing.enc.json", "marketing.json"):   # formatos antigos / sem criptografia
    if (pasta_dados / antigo).exists(): (pasta_dados / antigo).unlink()
json.dump({"gerado_em": base["gerado_em"]}, open(pasta_dados / "versao.json", "w"))
if "--se-mudou" in sys.argv: assinatura_arq.write_text(assin)

print(f"\nRealizado até {corte:%d/%m/%Y} (último título conciliado na BASE TEMPLATE, até {hoje:%d/%m/%Y})")
print(f"Mês vigente {sexta:%m/%Y} (vira na primeira sexta do mês) - R$ mil, gasto positivo:")
for s in serie:
    if s["mes"] == mes_corte and s["grupo"] in nomes_base and (abs(s["previsto"]) + abs(s["realizado"])) > 0.5:
        print(f"  {s['empreendimento']:<26}{s['grupo']:<25} previsto {s['previsto']/1000:9.1f}   realizado {s['realizado']/1000:9.1f}")
for s in serie2:
    if s["mes"] == mes_corte and (abs(s["previsto"]) + abs(s["realizado"])) > 0.5:
        print(f"  {s['empreendimento']:<26}{s['grupo']:<25} previsto {s['previsto']/1000:9.1f}   realizado {s['realizado']/1000:9.1f}")
print(f"\nOK: dados gerados em {pasta_dados}  ({len(lanc)} lançamentos dos empreendimentos, {len(lanc2)} das empresas)")
