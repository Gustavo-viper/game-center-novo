"""
Forge AI - chat no terminal.

Uso:
    python forge_ai.py                                   # sessão vazia
    python forge_ai.py https://github.com/dono/repo      # monta um repositório (precisa de GITHUB_TOKEN)
    python forge_ai.py https://github.com/dono/repo minha-branch

Comandos dentro do chat:
    /sair      encerra e baixa os arquivos que a IA salvou em /mnt/session/outputs/
"""
import json
import os
import sys
from pathlib import Path

import anthropic

CONFIG = Path(__file__).with_name("forge_ai_config.json")
SAIDA = Path(__file__).with_name("saida")
LIMITE_DOLARES_POR_SESSAO = 5  # trava de gasto: a sessão pausa ao chegar nesse valor


def criar_sessao(client, config, repo_url=None, branch="main"):
    resources = []
    if repo_url:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("Para montar um repositório, defina a variável GITHUB_TOKEN.")
        resources.append({
            "type": "github_repository",
            "url": repo_url,
            "mount_path": "/workspace/repo",
            "authorization_token": token,
            "checkout": {"type": "branch", "name": branch},
        })
    return client.beta.sessions.create(
        agent=config["agent_id"],  # sempre a versão mais recente do agente
        environment_id=config["environment_id"],
        title="Forge AI" + (f" - {repo_url}" if repo_url else ""),
        resources=resources,
        budget={
            "type": "limit",
            "max_list_cost": {"amount": str(LIMITE_DOLARES_POR_SESSAO * 100), "currency": "USD"},
        },
    )


def resumo_ferramenta(event) -> str:
    entrada = event.input or {}
    detalhe = entrada.get("command") or entrada.get("path") or entrada.get("file_path") or ""
    if not detalhe:
        detalhe = json.dumps(entrada, ensure_ascii=False)
    return f"{event.name}: {str(detalhe)[:120]}"


def perguntar_permissao(event) -> bool:
    print(f"\n[A IA quer executar] {resumo_ferramenta(event)}")
    if getattr(event, "evaluation", None):
        print(f"  motivo da pausa: {event.evaluation}")
    return input("  Permitir? (s/n) ").strip().lower().startswith("s")


def tratar_evento(client, session_id, event) -> bool:
    """Processa um evento. Retorna True quando a IA terminou o turno."""
    t = event.type
    if t == "agent.message":
        for block in event.content:
            if block.type == "text":
                print(block.text, end="", flush=True)
    elif t in ("agent.tool_use", "agent.mcp_tool_use"):
        if event.evaluated_permission == "ask":
            resultado = "allow" if perguntar_permissao(event) else "deny"
            client.beta.sessions.events.send(
                session_id=session_id,
                events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": resultado}],
            )
        else:
            print(f"\n  > {resumo_ferramenta(event)}", flush=True)
    elif t == "session.error":
        print(f"\n[erro] {getattr(event, 'error', event)}")
    elif t == "session.status_idle":
        motivo = event.stop_reason.type
        if motivo == "requires_action":
            return False  # esperando uma confirmação; continua ouvindo
        if motivo == "budget_reached":
            print(f"\n[limite de US$ {LIMITE_DOLARES_POR_SESSAO} desta sessão atingido]")
        return True
    elif t == "session.status_terminated":
        print("\n[sessão encerrada]")
        return True
    return False


def enviar_e_ouvir(client, session_id, texto, vistos: set):
    """Envia a mensagem e mostra a resposta até a IA terminar. Reconecta se a conexão cair."""
    enviado = False
    for _tentativa in range(5):
        try:
            with client.beta.sessions.events.stream(session_id=session_id) as stream:
                if not enviado:
                    client.beta.sessions.events.send(
                        session_id=session_id,
                        events=[{"type": "user.message", "content": [{"type": "text", "text": texto}]}],
                    )
                    enviado = True
                else:
                    # Reconexão: recupera eventos perdidos enquanto a conexão estava fora.
                    for event in client.beta.sessions.events.list(session_id=session_id, order="asc"):
                        if event.id not in vistos:
                            vistos.add(event.id)
                            if tratar_evento(client, session_id, event):
                                return
                for event in stream:
                    if event.id in vistos:
                        continue
                    vistos.add(event.id)
                    if tratar_evento(client, session_id, event):
                        return
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            print("\n[conexão caiu, reconectando...]")
    print("\n[não consegui reconectar; a sessão continua na nuvem]")


def baixar_saidas(client, session_id):
    arquivos = client.beta.files.list(scope_id=session_id, betas=["managed-agents-2026-04-01"])
    if not arquivos.data:
        return
    SAIDA.mkdir(exist_ok=True)
    for f in arquivos.data:
        destino = SAIDA / Path(f.filename).name
        client.beta.files.download(f.id).write_to_file(destino)
        print(f"  baixado: {destino}")


def main():
    if not CONFIG.exists():
        sys.exit("Rode primeiro: python setup_agente.py")
    config = json.loads(CONFIG.read_text())
    client = anthropic.Anthropic()

    repo_url = sys.argv[1] if len(sys.argv) > 1 else None
    branch = sys.argv[2] if len(sys.argv) > 2 else "main"
    session = criar_sessao(client, config, repo_url, branch)
    print(f"Forge AI pronta. Sessão {session.id}")
    print(f"Acompanhe no navegador: https://platform.claude.com/workspaces/default/sessions/{session.id}")
    print("Digite seu pedido (ou /sair).\n")

    vistos: set = set()
    while True:
        try:
            texto = input("\nvocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            texto = "/sair"
        if not texto:
            continue
        if texto == "/sair":
            print("Baixando arquivos gerados...")
            baixar_saidas(client, session.id)
            print("Até mais!")
            break
        print("\nforge-ai> ", end="")
        try:
            enviar_e_ouvir(client, session.id, texto, vistos)
        except KeyboardInterrupt:
            client.beta.sessions.events.send(session_id=session.id, events=[{"type": "user.interrupt"}])
            print("\n[interrompido]")
        except anthropic.APIStatusError as e:
            print(f"\n[erro da API {e.status_code}] {e.message}")


if __name__ == "__main__":
    main()
