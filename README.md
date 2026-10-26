# Painel Marketing e Stand · Grupo Carozzo

Página interna com o previsto x realizado de **Marketing (8.)** e **Stand de vendas (8.1.)** por empreendimento (Wellness, Balena e Ícone/Feira), publicada no **GitHub Pages** e protegida por **senha**.

As regras são as mesmas do bloco das abas DFC do Fluxo de Caixa:
- **Previsto e meses fechados:** vêm da aba **Base** do fluxo.
- **Mês em andamento:** vem da aba **Realizado Semanal**, com Considera = S e conciliado S e N, até a sexta-feira anterior à data em **AY2**.

## Como a proteção funciona

- O script grava os dados **criptografados** (AES-256-GCM, chave derivada da senha com PBKDF2-SHA256 e 600 mil iterações) em `site/data/marketing.enc.json`.
- A página pede a senha e descriptografa os dados **no navegador**. A senha nunca é enviada para nenhum servidor.
- Sem a senha, quem abrir o link ou olhar o repositório vê só a tela de senha e um arquivo ilegível.
- **Use uma senha forte** (mínimo de 12 caracteres, de preferência uma frase) e compartilhe só com a equipe. Se a senha vazar, troque-a em `scripts/senha.txt` e rode o .bat de novo.
- A senha e o caminho do fluxo ficam em arquivos **locais**, que o `.gitignore` impede de ir para o GitHub.

## Estrutura

```
site/index.html                   página com a tela de senha (sem dependências externas)
site/data/marketing.enc.json      dados criptografados (gerados pelo script)
scripts/gerar_dados.py            lê o fluxo, gera e criptografa os dados
scripts/config.json               empreendimentos e grupos exibidos
scripts/senha.txt                 SUA SENHA (local, não vai para o Git)
scripts/caminho_fluxo.txt         caminho do fluxo no seu PC (local, não vai para o Git)
atualizar_painel.bat              gera os dados, faz o commit e o push (duplo clique)
.github/workflows/pages.yml       publica no GitHub Pages a cada push
```

## Configuração (uma vez só)

### 1. Programas no seu PC

- **Python 3:** baixe em python.org e marque "Add python.exe to PATH" na instalação. Depois rode:
  `python -m pip install openpyxl cryptography`
- **Git:** baixe em git-scm.com.

### 2. Repositório

1. Crie o repositório em https://github.com/new com o nome `painel-marketing`.
   - **Conta GitHub gratuita:** o GitHub Pages só funciona com repositório **Public**. Pode criar público sem problema: os dados vão criptografados e a senha não vai para o GitHub.
   - **Conta ou organização paga (Pro, Team ou Enterprise):** dá para criar o repositório **Private**.
2. Clone o repositório numa pasta do seu PC e copie para dentro dela todos os arquivos deste pacote.
3. Dentro da pasta `scripts`, crie dois arquivos de texto:
   - `senha.txt`: só a senha, numa linha.
   - `caminho_fluxo.txt`: o caminho completo do fluxo, por exemplo
     `C:\Users\Carozzo\OneDrive - Carozzo\...\Fluxo_de_caixa_Grupo_Carozzo.xlsx`
4. Dê **duplo clique em `atualizar_painel.bat`**. Na primeira vez, se o .bat não conseguir enviar, rode no terminal, dentro da pasta, `git add .`, `git commit -m "Painel inicial"` e `git push`.

### 3. Ligar o GitHub Pages

1. No repositório, vá em **Settings > Pages**.
2. Em **Source**, escolha **GitHub Actions**.
3. Em **Actions**, confira se o workflow "Publicar painel no GitHub Pages" rodou. Se não rodou, clique em **Run workflow**.
4. O endereço do painel aparece em **Settings > Pages**, no formato `https://SEU-USUARIO.github.io/painel-marketing/`.

## Atualização semanal

1. Atualize o fluxo como de costume: cole a aba Realizado na Realizado Semanal, troque a data em AY2 e salve.
2. Dê **duplo clique em `atualizar_painel.bat`**.
3. Em 1 a 2 minutos, o painel está atualizado no mesmo link. O .bat mostra o previsto e o realizado do mês para você conferir com o bloco do fluxo.

**Para automatizar:** no **Agendador de Tarefas** do Windows, crie uma tarefa semanal (por exemplo, segunda às 10h) que execute `atualizar_painel.bat`. Com o `senha.txt` criado, o .bat roda sem pedir nada.

## Como incluir outro empreendimento ou grupo

Edite `scripts/config.json`:
- `empreendimentos`: use o nome da empresa como aparece na aba Base do fluxo.
- `grupos`: use o grupo fechamento.

A empresa precisa estar no de-para da aba Realizado Semanal (colunas AU:AV).
