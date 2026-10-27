"""
Serviço local do painel "Acompanhamento de despesas".

Fica rodando em segundo plano no PC da Rafaela (inicia junto com o Windows) e faz duas coisas:
1. Botão "Publicar agora" do painel: o painel (aberto neste PC) chama http://127.0.0.1:<porta>/publicar
   e este serviço gera os dados, faz commit e push. O GitHub Pages publica em 1-2 minutos.
2. Publicação automática: a cada minuto olha a BASE TEMPLATE e o fluxo mais recentes nas pastas do
   config.json. Quando um deles foi salvo (e ficou 1 minuto sem mudar), publica sozinho.

Só aceita chamadas deste computador (127.0.0.1) e do endereço do painel definido em config.json.
Registro em: atualizacao.log (pasta do painel).
"""
import json, sys, time, threading, subprocess, pathlib, datetime, fnmatch
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
args_cfg = ["--config", sys.argv[sys.argv.index("--config") + 1]] if "--config" in sys.argv else []
arq_cfg = pathlib.Path(args_cfg[1]) if args_cfg else AQUI / "config.json"
LOG = RAIZ / "atualizacao.log"

def cfg():
    return json.loads(arq_cfg.read_text(encoding="utf-8-sig"))

def log(msg):
    linha = f"[{datetime.datetime.now():%d/%m/%Y %H:%M:%S}] {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(linha + "\n")
    except OSError: pass
    print(linha, flush=True)

estado = {"executando": False, "etapa": "parado", "inicio": None, "fim": None,
          "resultado": None, "mensagem": "", "origem": None}
trava = threading.Lock()

def rodar(cmd):
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    saida = (r.stdout or "") + (r.stderr or "")
    if saida.strip(): log(saida.strip()[-3000:])
    return r.returncode, saida

def publicar(origem, so_se_mudou):
    with trava:
        if estado["executando"]: return False
        estado.update(executando=True, etapa="gerando", inicio=datetime.datetime.now().isoformat(timespec="seconds"),
                      fim=None, resultado=None, mensagem="", origem=origem)
    threading.Thread(target=_publicar, args=(origem, so_se_mudou), daemon=True).start()
    return True

def _publicar(origem, so_se_mudou):
    log(f"==== publicação iniciada ({origem}) ====")
    try:
        cmd = [sys.executable, str(AQUI / "gerar_dados.py"), *args_cfg] + (["--se-mudou"] if so_se_mudou else [])
        rc, saida = rodar(cmd)
        if rc != 0: raise RuntimeError("erro ao gerar os dados (veja atualizacao.log)")
        if "Nada a fazer" in saida:
            estado.update(resultado="sem_mudanca", mensagem="As bases não mudaram desde a última publicação."); return
        estado["etapa"] = "enviando"
        rodar(["git", "pull", "--quiet", "origin", "main"])
        rodar(["git", "add", "-A"])
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=RAIZ,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0:
            estado.update(resultado="sem_mudanca", mensagem="Nada novo para enviar."); return
        rc, _ = rodar(["git", "commit", "-m", f"Atualiza dados do painel ({origem}) {datetime.datetime.now():%d/%m/%Y %H:%M}"])
        if rc != 0: raise RuntimeError("erro no commit (veja atualizacao.log)")
        rc, _ = rodar(["git", "push", "-u", "origin", "HEAD:main"])
        if rc != 0: raise RuntimeError("erro ao enviar para o GitHub (veja atualizacao.log)")
        estado.update(resultado="ok", mensagem="Enviado. O GitHub Pages publica em 1-2 minutos.")
    except Exception as e:
        estado.update(resultado="erro", mensagem=str(e)); log(f"ERRO: {e}")
    finally:
        estado.update(executando=False, etapa="parado", fim=datetime.datetime.now().isoformat(timespec="seconds"))
        log(f"==== fim: {estado['resultado']} - {estado['mensagem']} ====")

# ---------- observador das pastas ----------
def mais_recente(pasta, padrao):
    p = pathlib.Path(pasta)
    if not p.is_dir(): return None
    c = [f for f in p.iterdir() if f.is_file() and not f.name.startswith("~$")
         and fnmatch.fnmatch(f.name.lower(), padrao.lower())]
    return max(c, key=lambda f: f.stat().st_mtime) if c else None

def assinatura_pastas(c):
    out = []
    for pasta, padrao in ((c["pasta_budget"], c["padrao_budget"]), (c["pasta_fluxo"], c["padrao_fluxo"])):
        f = mais_recente(pasta, padrao)
        out.append((f.name, f.stat().st_mtime) if f else None)
    return out

def observar():
    c = cfg(); sl = c.get("servico_local", {})
    intervalo = int(sl.get("intervalo_segundos", 60)); espera = int(sl.get("estabilizar_segundos", 60))
    ultima = assinatura_pastas(c); mudou_em = None
    log(f"Observando as pastas a cada {intervalo}s. Publicação automática {espera}s depois de salvar.")
    publicar("início do serviço", so_se_mudou=True)          # publica se algo mudou enquanto estava desligado
    while True:
        time.sleep(intervalo)
        try:
            atual = assinatura_pastas(cfg())
            if atual != ultima:
                ultima, mudou_em = atual, time.time()
                log(f"Mudança detectada: {[a[0] for a in atual if a]} - aguardando {espera}s sem novas alterações")
            elif mudou_em and time.time() - mudou_em >= espera:
                if publicar("base salva", so_se_mudou=True): mudou_em = None
        except Exception as e:
            log(f"Observador: {e}")

# ---------- servidor HTTP local ----------
class Handler(BaseHTTPRequestHandler):
    def origem_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in cfg().get("servico_local", {}).get("origens", [])
    def cors(self):
        o = self.headers.get("Origin")
        if o and self.origem_ok():
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
    def responder(self, cod, dados):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(cod); self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corpo))); self.end_headers(); self.wfile.write(corpo)
    def do_OPTIONS(self):
        self.send_response(204 if self.origem_ok() else 403); self.cors(); self.end_headers()
    def do_GET(self):
        if not self.origem_ok(): return self.responder(403, {"erro": "origem não autorizada"})
        if self.path.startswith("/status"): return self.responder(200, {"servico": "painel-despesas", **estado})
        self.responder(404, {"erro": "não encontrado"})
    def do_POST(self):
        if not self.origem_ok(): return self.responder(403, {"erro": "origem não autorizada"})
        if self.path.startswith("/publicar"):
            iniciou = publicar("botão Publicar agora", so_se_mudou=False)
            return self.responder(202 if iniciou else 409, {"iniciado": iniciou, **estado})
        self.responder(404, {"erro": "não encontrado"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    porta = int(cfg().get("servico_local", {}).get("porta", 8732))
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    except OSError:
        log(f"A porta {porta} já está em uso - o serviço provavelmente já está rodando."); sys.exit(0)
    log(f"Serviço local iniciado em http://127.0.0.1:{porta}")
    threading.Thread(target=observar, daemon=True).start()
    srv.serve_forever()
