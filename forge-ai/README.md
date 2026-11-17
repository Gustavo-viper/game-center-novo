# Forge AI

IA da Forge Studios que programa jogos, sites e apps. Você conversa com ela pelo terminal. Ela roda em um computador isolado na nuvem da Anthropic (Managed Agents), onde pode criar arquivos, rodar comandos, instalar pacotes e testar o código.

## 1. Instalar (uma vez)

```bash
cd forge-ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Crie uma chave de API em https://platform.claude.com (menu **API Keys**) e defina a variável de ambiente:

```bash
export ANTHROPIC_API_KEY="sua-chave"     # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sua-chave"
```

## 2. Criar o agente (uma vez)

```bash
python setup_agente.py
```

O script gera o `forge_ai_config.json` com os IDs do agente e do ambiente. Esses IDs não são secretos e podem ir para o Git, assim o time todo usa o mesmo agente.

## 3. Usar

```bash
python forge_ai.py
```

Exemplo de pedido:

```
você> Crie um jogo da cobrinha em HTML/JS que funcione no celular e salve o zip em /mnt/session/outputs/
```

Quando você digita `/sair`, os arquivos que a IA salvou em `/mnt/session/outputs/` são baixados para `forge-ai/saida/`.

### Trabalhar em um repositório do GitHub

```bash
export GITHUB_TOKEN="seu-token"   # token do GitHub com acesso ao repositório
python forge_ai.py https://github.com/gustavo-viper/game-center-novo main
```

O repositório fica em `/workspace/repo` dentro da sessão.

## Personalizar

Tudo fica em `setup_agente.py`. Depois de mudar, rode `python setup_agente.py` de novo para criar uma nova versão do agente:

- `SYSTEM_PROMPT`: os padrões e as regras da Forge.
- `model`: hoje é `claude-opus-5-5` com `effort: "high"`. Use `"medium"` para gastar menos ou `"xhigh"` para tarefas difíceis.
- **Internet**: vem desligada. Para a IA pesquisar na web, mude `web_fetch` e `web_search` para `True`.

Em `forge_ai.py`, `LIMITE_DOLARES_POR_SESSAO` (padrão US$ 5) pausa a sessão quando o gasto chega nesse valor.

## Custos e observações

- Claude Opus 5.5: US$ 4 por milhão de tokens de entrada e US$ 20 por milhão de saída. Cada sessão também cobra US$ 0,08 por hora de execução.
- Managed Agents ainda está em beta.
- O histórico das sessões fica salvo na sua conta até você apagar. Para ver cada sessão no navegador, use o link que o script mostra ao iniciar.
- Quando um comando parecer arriscado, a IA pausa e pergunta `Permitir? (s/n)`.
