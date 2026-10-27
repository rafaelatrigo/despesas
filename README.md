# Acompanhamento de despesas · Grupo Carozzo

Painel interno com o previsto x realizado por empreendimento (Wellness, Balena e Ícone/Feira), publicado no **GitHub Pages** e protegido por **senha**.

## Acessos

| Acesso | Senha (arquivo local, não vai para o GitHub) | O que vê |
|---|---|---|
| **Líderes** | `scripts/senha.txt` | Os 8 grupos: 1. Terreno, 2. Custo de obra, 3. Tx adm. obra, 4. Despesas legais, 5. Projetos, 6. IPTU e taxas terreno, 8. Marketing e 8.1. Stand |
| **Completo** (Michelle) | `scripts/senha_completo.txt` | Tudo dos líderes **e a DRE inteira** (Receita Bruta até Lucro Líquido) |

- Cada acesso tem o seu próprio arquivo criptografado: `site/data/lideres.enc.json` e `site/data/completo.enc.json`. A DRE **não está** no arquivo dos líderes.
- As duas senhas precisam ser diferentes e ter pelo menos 12 caracteres.
- Para trocar uma senha, edite o arquivo e rode o .bat.

## De onde vêm os números

O script procura sozinho, em cada pasta, o arquivo **modificado por último**:

| Dado | Pasta (`scripts/config.json`) | Arquivo e aba | Regra |
|---|---|---|---|
| **Previsto** (mês a mês: ano vigente e o seguinte, automático) | `CONTROLADORIA\FLUXO DE CAIXA CONSOLIDADO` | fluxo de caixa mais recente, aba **Base** | Todas as linhas, como as fórmulas SOMASES das abas DFC, por empresa, grupo fechamento, tipo e mês |
| **Previsto do sistema** (só os meses em `previsto_sistema.meses`, hoje nov/26 e dez/26) | `previsto_sistema.pasta` (padrão: `CONTROLADORIA\DESPESAS`) | relatório de previstos mais recente (`*PREVISTO*.xl*`), aba **Base Fluxo** | Substitui o previsto do fluxo nesses meses, por empresa e grupo fechamento. Os outros meses seguem com o fluxo |
| **Realizado** e **lançamentos** | `CONTROLADORIA\DESPESAS` | BASE TEMPLATE BUDGET mais recente, aba **Realizado** | Considera = S, conciliado S e N, VALOR_V3 por DATA CAIXA |

- **Corte:** a sexta-feira mais recente, contando o próprio dia. Se roda na sexta, o corte é a própria sexta; de sábado a quinta, é a sexta passada. Assim, a apresentação de segunda mostra tudo o que foi pago até sexta. O "mês vigente" é o mês do corte, e o "próximo mês" é o seguinte. A troca acontece sozinha na primeira sexta-feira do mês novo. Os anos também viram sozinhos (`"anos": "auto"` no config).
- **Meses:**
  - meses anteriores ao corte são fechados;
  - o mês do corte soma do dia 1 até o corte;
  - os títulos com data depois do corte aparecem como **Programado** e ficam fora do realizado.
- **Ajustes manuais:** valores digitados direto nas fórmulas das abas DFC do fluxo não entram no painel. Exemplos: o `-25000` em Outras Despesas e o `1% do saldo` em Receitas Financeiras do Balena.

## Logo

Coloque o arquivo da logo da Carozzo como **`site/logo.png`**. Use PNG, de preferência com fundo transparente. Enquanto o arquivo não existir, aparece o nome "CAROZZO" em texto.

## Atualização

### Serviço local: botão "Publicar agora" e publicação automática (recomendado)

Instale **uma vez**, com duplo clique em **`instalar_servico.bat`**. O serviço fica rodando em segundo plano e inicia sozinho junto com o Windows.

- **Publicação automática:** a cada minuto, o serviço olha a BASE TEMPLATE e o fluxo mais recentes. Quando um deles é **salvo** e fica 1 minuto sem novas alterações, ele gera os dados e publica. Isso vale também quando outra pessoa salva o arquivo e o OneDrive sincroniza com o seu PC.
- **Botão "Publicar agora":** aparece no painel **só no computador onde o serviço roda**. Ao clicar, o serviço publica na hora. O botão mostra o andamento (Gerando dados... > Enviando ao GitHub... > Publicando no site...) e recarrega o painel sozinho quando o site estiver atualizado, em 1 a 2 minutos.
- **Permissão do navegador:** na primeira vez, o Chrome ou o Edge podem perguntar se o site pode "acessar dispositivos na rede local". Clique em **Permitir**. É assim que o painel conversa com o serviço no seu PC.
- **Registro:** tudo o que o serviço faz fica em `atualizacao.log`.
- **Para parar e remover o serviço:** dê duplo clique em `desinstalar_servico.bat`.
- **Segurança:** o serviço só aceita chamadas do próprio computador e do endereço do painel (`servico_local.origens` no config.json).
- **Agendamento antigo:** se você criou a tarefa no Agendador de Tarefas, pode apagá-la. O serviço substitui o agendamento.

### Outras formas

- `atualizar_painel.bat`: publica na hora, com duplo clique.
- **Botão "Atualizar" no painel:** para todos os usuários, busca a última versão publicada sem pedir a senha de novo.

## Como incluir outro empreendimento ou grupo

Edite `scripts/config.json`:
- **Empreendimento:** em `empreendimentos`, informe `empresa_fluxo` e `empresa_sienge`.
- **Grupo dos líderes:** em `grupos`, informe o grupo fechamento.
- **Estrutura da DRE:** fica no bloco `dre`.
