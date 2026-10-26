# Painel Marketing e Stand · Grupo Carozzo

Página interna com o previsto x realizado de **Marketing (8.)** e **Stand de vendas (8.1.)** por empreendimento (Wellness, Balena e Ícone/Feira), publicada no **GitHub Pages** e protegida por **senha**.

## De onde vêm os números

O script procura sozinho, em cada pasta, o arquivo **modificado por último**:

| Dado | Pasta (definida em `scripts/config.json`) | Arquivo e aba | Regra |
|---|---|---|---|
| **Previsto** | `CONTROLADORIA\FLUXO DE CAIXA CONSOLIDADO` | fluxo de caixa mais recente, aba **Base** | Linhas "Orçado", tipo Operacional, por empresa, grupo fechamento e mês |
| **Realizado** e **lançamentos** | `CONTROLADORIA\DESPESAS` | BASE TEMPLATE BUDGET mais recente, aba **Realizado** | Considera = S, conciliado S e N, VALOR_V3 por DATA CAIXA |

- **Corte:** sexta-feira anterior ao dia em que o .bat roda.
- **Meses anteriores ao corte:** mês fechado, soma o mês inteiro.
- **Mês do corte:** soma do dia 1 até o corte.
- **Títulos com data depois do corte:** aparecem como "Programado" e ficam fora do realizado.
- **Arquivos ignorados:** os temporários do Excel (`~$...`) e os que não têm a aba exigida. O rodapé do painel mostra quais arquivos foram usados.

## Como a proteção funciona

- Os dados são gravados **criptografados** (AES-256-GCM, chave PBKDF2-SHA256 com 600 mil iterações) em `site/data/marketing.enc.json`.
- A página pede a senha e abre os dados **no navegador**. Sem a senha, só aparece a tela de acesso.
- A senha fica em `scripts/senha.txt`, um arquivo local que **não vai para o GitHub**. Para trocar a senha, edite esse arquivo e rode o .bat.

## Estrutura

```
site/index.html                  página com a tela de senha
site/data/marketing.enc.json     dados criptografados (gerados pelo script)
scripts/gerar_dados.py           busca os arquivos, calcula e criptografa
scripts/config.json              pastas, empreendimentos (nome no fluxo e no Sienge) e grupos
scripts/senha.txt                SUA SENHA (local, não vai para o Git)
atualizar_painel.bat             gera os dados, faz o commit e o push (duplo clique)
atualizar_painel_agendado.bat    mesma coisa, sem pausas, para o Agendador de Tarefas
.github/workflows/pages.yml      publica no GitHub Pages a cada push
```

## Atualização

1. Atualize a **BASE TEMPLATE BUDGET**: Dados > Atualizar Tudo, depois **salve**.
2. Se mexeu no previsto, salve também o **fluxo de caixa** na pasta FLUXO DE CAIXA CONSOLIDADO.
3. Dê **duplo clique em `atualizar_painel.bat`**.

O .bat mostra quais arquivos usou e o previsto e o realizado do mês, para você conferir. Em 1 a 2 minutos o painel está atualizado no mesmo link.

**Agendamento (opcional):** no Agendador de Tarefas do Windows, crie uma tarefa semanal que execute `atualizar_painel_agendado.bat`. O resultado de cada execução fica em `atualizacao.log`. Antes de agendar, confira se o `.gitignore` tem a linha `atualizacao.log`.

## Como incluir outro empreendimento ou grupo

Edite `scripts/config.json`:
- `empreendimentos`: informe `empresa_fluxo` (nome da empresa na aba Base do fluxo) e `empresa_sienge` (nome na aba Realizado da BASE TEMPLATE).
- `grupos`: informe o grupo fechamento.
