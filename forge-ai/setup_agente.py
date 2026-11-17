"""
Forge AI - configuração (rode UMA vez).

Cria na Anthropic:
  1. o "ambiente" (o computador isolado na nuvem onde a IA roda comandos);
  2. o "agente" (modelo + instruções da Forge + ferramentas).

Os IDs ficam salvos em forge_ai_config.json. Rodar de novo ATUALIZA o agente
(nova versão) em vez de criar outro.
"""
import json
from pathlib import Path

import anthropic

CONFIG = Path(__file__).with_name("forge_ai_config.json")

SYSTEM_PROMPT = """Você é a Forge AI, a desenvolvedora sênior da Forge Studios.
Você cria e mantém jogos, sites e apps da Forge.

Como trabalhar:
- Responda sempre em português do Brasil.
- Antes de mudar um projeto, leia os arquivos para entender o padrão que já existe e siga esse padrão.
- Escreva código limpo, comentado onde não for óbvio, e que funcione no navegador e no celular.
- Depois de escrever, teste: rode o código, os testes ou abra a página quando der.
- Se um pedido estiver ambíguo, escolha a opção mais sensata, diga qual escolheu e siga.
- Salve arquivos finais (zips, builds, relatórios) em /mnt/session/outputs/ para o usuário baixar.
- Se um repositório foi montado em /workspace/repo, trabalhe nele.
- No fim, diga em poucas linhas o que fez, o que testou e o que ficou faltando.
"""

AGENT_CONFIG = dict(
    name="Forge AI",
    description="Desenvolvedora de jogos e apps da Forge Studios",
    model={"id": "claude-opus-5-5", "effort": "high"},
    system=SYSTEM_PROMPT,
    tools=[
        {
            "type": "agent_toolset_20260401",  # bash, ler/editar arquivos, buscar no código...
            "default_config": {"enabled": True, "permission_policy": {"type": "auto"}},
            "configs": [
                # Web desligada por padrão. Para ligar, troque para True e rode este script de novo.
                {"name": "web_fetch", "enabled": False},
                {"name": "web_search", "enabled": False},
            ],
        },
    ],
)


def main() -> None:
    client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}

    if "environment_id" not in config:
        env = client.beta.environments.create(
            name="forge-ai-env",
            config={
                "type": "cloud",
                # Rede limitada: só gerenciadores de pacotes (npm, pip...) liberados.
                "networking": {"type": "limited", "allow_package_managers": True, "allow_mcp_servers": True},
            },
        )
        config["environment_id"] = env.id
        print(f"Ambiente criado: {env.id}")

    if "agent_id" in config:
        atual = client.beta.agents.retrieve(config["agent_id"])
        agent = client.beta.agents.update(config["agent_id"], version=atual.version, **AGENT_CONFIG)
        print(f"Agente atualizado: {agent.id} (versão {agent.version})")
    else:
        agent = client.beta.agents.create(**AGENT_CONFIG)
        print(f"Agente criado: {agent.id} (versão {agent.version})")
    config["agent_id"] = agent.id

    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Configuração salva em {CONFIG.name}. Agora rode: python forge_ai.py")


if __name__ == "__main__":
    main()
