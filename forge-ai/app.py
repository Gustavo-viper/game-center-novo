"""
Forge AI - aplicativo de desktop (vira "Forge AI.exe" com PyInstaller).

A janela é uma página HTML (ui/index.html) exibida pelo pywebview.
O JavaScript chama os métodos da classe Api; o Python devolve os eventos
da IA chamando forge.evento(...) na página.
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import anthropic
import webview

from forge_core import garantir_agente

APP_NOME = "Forge AI"
LIMITE_DOLARES_POR_SESSAO = 5


def pasta_recursos() -> Path:
    # Dentro do .exe (PyInstaller) os arquivos ficam em sys._MEIPASS.
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def pasta_dados() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    pasta = Path(base) / "ForgeAI"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


ARQ_CONFIG = pasta_dados() / "config.json"


def ler_config() -> dict:
    try:
        return json.loads(ARQ_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_config(config: dict) -> None:
    ARQ_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


def resumo_ferramenta(event) -> str:
    entrada = event.input or {}
    detalhe = entrada.get("command") or entrada.get("path") or entrada.get("file_path") or ""
    if not detalhe:
        detalhe = json.dumps(entrada, ensure_ascii=False)
    return f"{event.name}: {str(detalhe)[:160]}"


def mensagem_de_erro(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Chave de API inválida. Clique em ⚙ Chave de API e cole uma chave nova."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "Sua conta não tem acesso a este recurso (Managed Agents). Veja as permissões no platform.claude.com."
    if isinstance(e, anthropic.RateLimitError):
        return "Muitos pedidos ao mesmo tempo. Espere um pouco e tente de novo."
    if isinstance(e, anthropic.APIConnectionError):
        return "Sem conexão com a internet ou com a Anthropic."
    if isinstance(e, anthropic.APIStatusError):
        return f"Erro da API ({e.status_code}): {e.message}"
    return f"Erro inesperado: {e}"


class Api:
    """Métodos chamados pela página via window.pywebview.api.<nome>()."""

    def __init__(self):
        self.janela = None
        self.config = ler_config()
        self.session_id = None
        self.vistos: set = set()
        self.ocupado = False
        self._trava = threading.Lock()

    # ---------- comunicação Python -> página ----------
    def _emitir(self, tipo: str, **dados) -> None:
        if self.janela:
            payload = json.dumps({"tipo": tipo, **dados}, ensure_ascii=False)
            self.janela.evaluate_js(f"forge.evento({payload})")

    def _cliente(self) -> anthropic.Anthropic:
        chave = self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        return anthropic.Anthropic(api_key=chave)

    # ---------- chamados pela página ----------
    def estado(self) -> dict:
        tem_chave = bool(self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY"))
        return {"tem_chave": tem_chave, "sessao": self.session_id}

    def salvar_chave(self, chave: str) -> dict:
        chave = (chave or "").strip()
        if not chave:
            return {"ok": False, "erro": "Cole a chave de API."}
        try:
            anthropic.Anthropic(api_key=chave).models.retrieve("claude-opus-5-5")
        except Exception as e:  # noqa: BLE001 - mostramos a mensagem amigável
            return {"ok": False, "erro": mensagem_de_erro(e)}
        self.config["api_key"] = chave
        salvar_config(self.config)
        return {"ok": True}

    def nova_conversa(self) -> dict:
        if self.ocupado:
            return {"ok": False, "erro": "Espere a IA terminar (ou clique em Parar)."}
        self.session_id = None
        self.vistos = set()
        return {"ok": True}

    def enviar(self, texto: str) -> dict:
        texto = (texto or "").strip()
        if not texto:
            return {"ok": False}
        with self._trava:
            if self.ocupado:
                return {"ok": False, "erro": "A IA ainda está trabalhando."}
            self.ocupado = True
        threading.Thread(target=self._turno, args=(texto,), daemon=True).start()
        return {"ok": True}

    def responder_permissao(self, tool_use_id: str, permitir: bool) -> None:
        try:
            self._cliente().beta.sessions.events.send(
                session_id=self.session_id,
                events=[{
                    "type": "user.tool_confirmation",
                    "tool_use_id": tool_use_id,
                    "result": "allow" if permitir else "deny",
                }],
            )
        except Exception as e:  # noqa: BLE001
            self._emitir("erro", texto=mensagem_de_erro(e))

    def parar(self) -> None:
        if self.session_id and self.ocupado:
            try:
                self._cliente().beta.sessions.events.send(
                    session_id=self.session_id, events=[{"type": "user.interrupt"}]
                )
            except Exception as e:  # noqa: BLE001
                self._emitir("erro", texto=mensagem_de_erro(e))

    def baixar_arquivos(self) -> dict:
        if not self.session_id:
            return {"ok": False, "erro": "Nenhuma conversa aberta ainda."}
        try:
            client = self._cliente()
            arquivos = client.beta.files.list(scope_id=self.session_id, betas=["managed-agents-2026-04-01"])
            if not arquivos.data:
                return {"ok": False, "erro": "A IA ainda não salvou arquivos em /mnt/session/outputs/."}
            destino = Path.home() / "Downloads" / "Forge AI" / self.session_id
            destino.mkdir(parents=True, exist_ok=True)
            for f in arquivos.data:
                client.beta.files.download(f.id).write_to_file(destino / Path(f.filename).name)
            self._abrir_pasta(destino)
            return {"ok": True, "pasta": str(destino), "quantidade": len(arquivos.data)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "erro": mensagem_de_erro(e)}

    def abrir_no_navegador(self) -> None:
        if self.session_id:
            import webbrowser
            webbrowser.open(f"https://platform.claude.com/workspaces/default/sessions/{self.session_id}")

    # ---------- trabalho em segundo plano ----------
    @staticmethod
    def _abrir_pasta(pasta: Path) -> None:
        if sys.platform == "win32":
            os.startfile(pasta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pasta)])
        else:
            subprocess.Popen(["xdg-open", str(pasta)])

    def _garantir_sessao(self, client: anthropic.Anthropic) -> None:
        if self.session_id:
            return
        if "agent_id" not in self.config or "environment_id" not in self.config:
            self._emitir("status", texto="Preparando a Forge AI pela primeira vez...")
            self.config = garantir_agente(client, self.config)
            salvar_config(self.config)
        self._emitir("status", texto="Abrindo um computador na nuvem para esta conversa...")
        session = client.beta.sessions.create(
            agent=self.config["agent_id"],
            environment_id=self.config["environment_id"],
            title="Forge AI (app)",
            budget={
                "type": "limit",
                "max_list_cost": {"amount": str(LIMITE_DOLARES_POR_SESSAO * 100), "currency": "USD"},
            },
        )
        self.session_id = session.id
        self._emitir("sessao", id=session.id)

    def _tratar(self, event) -> bool:
        """Retorna True quando a IA terminou o turno."""
        t = event.type
        if t == "agent.message":
            texto = "".join(b.text for b in event.content if b.type == "text")
            if texto:
                self._emitir("mensagem", texto=texto)
        elif t == "agent.thinking":
            self._emitir("status", texto="Pensando...")
        elif t in ("agent.tool_use", "agent.mcp_tool_use"):
            if event.evaluated_permission == "ask":
                self._emitir("permissao", id=event.id, resumo=resumo_ferramenta(event),
                             motivo=str(getattr(event, "evaluation", "") or ""))
            else:
                self._emitir("ferramenta", resumo=resumo_ferramenta(event))
        elif t == "session.error":
            erro = getattr(event, "error", None)
            self._emitir("erro", texto=str(getattr(erro, "message", None) or erro))
        elif t == "session.status_idle":
            motivo = event.stop_reason.type
            if motivo == "requires_action":
                return False
            if motivo == "budget_reached":
                self._emitir("erro", texto=f"Limite de US$ {LIMITE_DOLARES_POR_SESSAO} desta conversa atingido. Comece uma nova conversa.")
            return True
        elif t == "session.status_terminated":
            self.session_id = None
            self._emitir("erro", texto="A sessão foi encerrada. A próxima mensagem abre uma nova conversa.")
            return True
        return False

    def _turno(self, texto: str) -> None:
        try:
            client = self._cliente()
            self._garantir_sessao(client)
            self._emitir("status", texto="Trabalhando...")
            enviado = False
            for _ in range(5):
                try:
                    with client.beta.sessions.events.stream(session_id=self.session_id) as stream:
                        if not enviado:
                            client.beta.sessions.events.send(
                                session_id=self.session_id,
                                events=[{"type": "user.message", "content": [{"type": "text", "text": texto}]}],
                            )
                            enviado = True
                        else:  # reconexão: recupera eventos perdidos
                            for event in client.beta.sessions.events.list(session_id=self.session_id, order="asc"):
                                if event.id not in self.vistos:
                                    self.vistos.add(event.id)
                                    if self._tratar(event):
                                        return
                        for event in stream:
                            if event.id in self.vistos:
                                continue
                            self.vistos.add(event.id)
                            if self._tratar(event):
                                return
                except (anthropic.APIConnectionError, anthropic.APITimeoutError):
                    self._emitir("status", texto="Conexão caiu, reconectando...")
            self._emitir("erro", texto="Não consegui reconectar. A IA continua trabalhando na nuvem.")
        except Exception as e:  # noqa: BLE001
            self._emitir("erro", texto=mensagem_de_erro(e))
        finally:
            self.ocupado = False
            self._emitir("fim")


def main() -> None:
    api = Api()
    janela = webview.create_window(
        APP_NOME,
        url=str(pasta_recursos() / "ui" / "index.html"),
        js_api=api,
        width=1100,
        height=760,
        min_size=(720, 520),
        background_color="#16130f",
        text_select=True,
    )
    api.janela = janela
    webview.start(icon=str(pasta_recursos() / "assets" / "forge.png"))


if __name__ == "__main__":
    main()
