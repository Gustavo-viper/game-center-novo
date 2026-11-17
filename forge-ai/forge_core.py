"""
Forge AI - definição do agente (compartilhada pelo app e pelos scripts).
"""
import anthropic

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


def garantir_agente(client: anthropic.Anthropic, config: dict, atualizar: bool = False) -> dict:
    """Cria o ambiente e o agente se ainda não existirem. Com atualizar=True, publica nova versão do agente."""
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
    if "agent_id" not in config:
        agent = client.beta.agents.create(**AGENT_CONFIG)
        config["agent_id"] = agent.id
    elif atualizar:
        atual = client.beta.agents.retrieve(config["agent_id"])
        client.beta.agents.update(config["agent_id"], version=atual.version, **AGENT_CONFIG)
    return config
