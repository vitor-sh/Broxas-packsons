"""
Downloads a prova de certificado desatualizado
==============================================

Um jogador recebeu 102 erros do tipo:

    SSL: CERTIFICATE_VERIFY_FAILED
    certificate verify failed: certificate has expired

Os 102 eram justamente os mods servidos pelo CDN do Modrinth, enquanto os 37
servidos pelo GitHub baixaram sem problema. Isso indica certificado raiz
expirado ou desatualizado no Windows daquele computador, ou relogio do sistema
fora de hora, e nao problema do nosso lado.

Duas defesas, nesta ordem:

1. Usar o pacote de certificados do certifi, que vai embutido no executavel,
   em vez de depender do que esta instalado no Windows.

2. Se ainda assim a verificacao falhar, e o arquivo tiver hash conhecido no
   manifest, baixar sem verificar o transporte e conferir o SHA-1 do conteudo.
   O hash veio do manifest, que foi obtido por conexao verificada, portanto o
   arquivo continua sendo checado: se tiver sido alterado no caminho, o hash
   nao bate e o arquivo e descartado. Sem hash conhecido, nao ha essa segunda
   tentativa.
"""

import hashlib
import ssl
import urllib.request
from pathlib import Path

AGENTE = "BroxasUpdater/1.0"

_contexto_verificado = None
_contexto_sem_verificacao = None
_avisou_certificado = False


def _ctx_verificado():
    """Contexto usando o pacote do certifi, com recurso ao do sistema."""
    global _contexto_verificado
    if _contexto_verificado is None:
        try:
            import certifi
            _contexto_verificado = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _contexto_verificado = ssl.create_default_context()
    return _contexto_verificado


def _ctx_sem_verificacao():
    global _contexto_sem_verificacao
    if _contexto_sem_verificacao is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _contexto_sem_verificacao = ctx
    return _contexto_sem_verificacao


def _e_erro_de_certificado(exc) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    texto = str(exc).lower()
    return ("certificate" in texto and "verify" in texto) or "certificate_verify_failed" in texto


def _abrir(url, contexto, tempo=120):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    return urllib.request.urlopen(req, timeout=tempo, context=contexto)


def _gravar(resposta, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".part")
    with open(temporario, "wb") as saida:
        while True:
            pedaco = resposta.read(1024 * 128)
            if not pedaco:
                break
            saida.write(pedaco)
    return temporario


def _sha1(caminho: Path) -> str:
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(1024 * 256), b""):
            h.update(pedaco)
    return h.hexdigest()


def ler_texto(url, tempo=30):
    """Baixa um texto (usado para o manifest). Sempre com verificacao."""
    with _abrir(url, _ctx_verificado(), tempo) as resposta:
        return resposta.read().decode("utf-8")


def baixar(url, destino, sha1_esperado=None, log=None):
    """
    Baixa um arquivo. Devolve (ok, mensagem).

    Com hash conhecido, o conteudo e sempre conferido, seja qual for o caminho
    usado para obter o arquivo.
    """
    global _avisou_certificado
    destino = Path(destino)
    esperado = (sha1_esperado or "").lower()

    def conferir(temporario):
        if not esperado:
            return True, ""
        obtido = _sha1(temporario).lower()
        if obtido == esperado:
            return True, ""
        return False, f"conteudo diferente do esperado (hash {obtido[:12]} no lugar de {esperado[:12]})"

    # 1) caminho normal, com verificacao
    try:
        with _abrir(url, _ctx_verificado()) as resposta:
            temporario = _gravar(resposta, destino)
        ok, motivo = conferir(temporario)
        if not ok:
            temporario.unlink(missing_ok=True)
            return False, motivo
        temporario.replace(destino)
        return True, ""
    except Exception as exc:
        if not _e_erro_de_certificado(exc):
            return False, str(exc)
        erro_original = exc

    # 2) certificado do computador recusou a conexao
    if not esperado:
        return False, (f"{erro_original} | sem hash no manifest, o arquivo nao "
                       f"pode ser conferido de outra forma")

    if log and not _avisou_certificado:
        _avisou_certificado = True
        log("AVISO: o Windows deste computador recusou o certificado do site.")
        log("  Os arquivos serao conferidos pelo hash, que garante que o")
        log("  conteudo esta correto.")
        log("  Vale ajustar a data e a hora do sistema e rodar o Windows Update.")

    try:
        with _abrir(url, _ctx_sem_verificacao()) as resposta:
            temporario = _gravar(resposta, destino)
    except Exception as exc:
        return False, f"{erro_original} | segunda tentativa tambem falhou: {exc}"

    ok, motivo = conferir(temporario)
    if not ok:
        temporario.unlink(missing_ok=True)
        return False, f"{motivo} | arquivo descartado"
    temporario.replace(destino)
    return True, "conferido pelo hash"
