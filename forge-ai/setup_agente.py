"""
Forge AI - configuração (rode UMA vez).

Cria na Anthropic o "ambiente" (computador isolado na nuvem) e o "agente"
(modelo + instruções da Forge + ferramentas), definidos em forge_core.py.
Os IDs ficam salvos em forge_ai_config.json. Rodar de novo ATUALIZA o agente
(nova versão) em vez de criar outro.
"""
import json
from pathlib import Path

import anthropic

from forge_core import garantir_agente

CONFIG = Path(__file__).with_name("forge_ai_config.json")


def main() -> None:
    client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    config = garantir_agente(client, config, atualizar=True)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Agente pronto: {config['agent_id']} (ambiente {config['environment_id']})")
    print(f"Configuração salva em {CONFIG.name}. Agora rode: python forge_ai.py")


if __name__ == "__main__":
    main()
