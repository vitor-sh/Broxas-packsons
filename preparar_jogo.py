"""
Preparacao do jogo antes de abrir o launcher
============================================

Duas coisas que poupam trabalho de quem vai jogar:

1. Coloca o servidor na lista de multijogador (servers.dat), preservando os
   servidores que a pessoa ja tem. Assim ninguem precisa digitar o IP.
2. Deixa o perfil do Forge pre-selecionado no launcher (TLauncher e launcher
   oficial), para nao haver risco de entrar na versao errada.

O servers.dat e um arquivo NBT, o formato binario do proprio Minecraft, entao
aqui tem um leitor e um gravador minimos. Antes de qualquer alteracao e feita
uma copia de seguranca do arquivo original.
"""

import gzip
import json
import shutil
import struct
from pathlib import Path

# ---------------------------------------------------------------------
# NBT: leitura
# ---------------------------------------------------------------------

FIM = 0
BYTE = 1
CURTO = 2
INT = 3
LONGO = 4
FLUTUANTE = 5
DUPLO = 6
VETOR_BYTES = 7
TEXTO = 8
LISTA = 9
COMPOSTO = 10
VETOR_INT = 11
VETOR_LONGO = 12


class LeitorNBT:
    def __init__(self, dados: bytes):
        self.d = dados
        self.p = 0

    def _ler(self, formato):
        tamanho = struct.calcsize(formato)
        valor = struct.unpack_from(formato, self.d, self.p)[0]
        self.p += tamanho
        return valor

    def texto(self):
        n = self._ler(">H")
        s = self.d[self.p:self.p + n].decode("utf-8", errors="replace")
        self.p += n
        return s

    def carga(self, tipo):
        if tipo == BYTE:
            return self._ler(">b")
        if tipo == CURTO:
            return self._ler(">h")
        if tipo == INT:
            return self._ler(">i")
        if tipo == LONGO:
            return self._ler(">q")
        if tipo == FLUTUANTE:
            return self._ler(">f")
        if tipo == DUPLO:
            return self._ler(">d")
        if tipo == TEXTO:
            return self.texto()
        if tipo == VETOR_BYTES:
            n = self._ler(">i")
            v = self.d[self.p:self.p + n]
            self.p += n
            return bytearray(v)
        if tipo == VETOR_INT:
            n = self._ler(">i")
            return [self._ler(">i") for _ in range(n)]
        if tipo == VETOR_LONGO:
            n = self._ler(">i")
            return [self._ler(">q") for _ in range(n)]
        if tipo == LISTA:
            tipo_itens = self._ler(">b")
            n = self._ler(">i")
            itens = [self.carga(tipo_itens) for _ in range(max(0, n))]
            return {"__lista__": True, "tipo": tipo_itens, "itens": itens}
        if tipo == COMPOSTO:
            saida = {}
            ordem = []
            while True:
                t = self._ler(">b")
                if t == FIM:
                    break
                nome = self.texto()
                saida[nome] = {"tipo": t, "valor": self.carga(t)}
                ordem.append(nome)
            return {"__composto__": True, "campos": saida, "ordem": ordem}
        raise ValueError(f"tipo NBT desconhecido: {tipo}")

    def raiz(self):
        t = self._ler(">b")
        if t != COMPOSTO:
            raise ValueError("arquivo NBT nao comeca com um composto")
        nome = self.texto()
        return nome, self.carga(COMPOSTO)


# ---------------------------------------------------------------------
# NBT: gravacao
# ---------------------------------------------------------------------

class GravadorNBT:
    def __init__(self):
        self.partes = []

    def _p(self, formato, valor):
        self.partes.append(struct.pack(formato, valor))

    def texto(self, s):
        b = s.encode("utf-8")
        self._p(">H", len(b))
        self.partes.append(b)

    def carga(self, tipo, valor):
        if tipo == BYTE:
            self._p(">b", int(valor))
        elif tipo == CURTO:
            self._p(">h", int(valor))
        elif tipo == INT:
            self._p(">i", int(valor))
        elif tipo == LONGO:
            self._p(">q", int(valor))
        elif tipo == FLUTUANTE:
            self._p(">f", float(valor))
        elif tipo == DUPLO:
            self._p(">d", float(valor))
        elif tipo == TEXTO:
            self.texto(valor)
        elif tipo == VETOR_BYTES:
            self._p(">i", len(valor))
            self.partes.append(bytes(valor))
        elif tipo == VETOR_INT:
            self._p(">i", len(valor))
            for v in valor:
                self._p(">i", v)
        elif tipo == VETOR_LONGO:
            self._p(">i", len(valor))
            for v in valor:
                self._p(">q", v)
        elif tipo == LISTA:
            itens = valor["itens"]
            tipo_itens = valor["tipo"] if itens else valor.get("tipo", COMPOSTO)
            self._p(">b", tipo_itens)
            self._p(">i", len(itens))
            for item in itens:
                self.carga(tipo_itens, item)
        elif tipo == COMPOSTO:
            campos = valor["campos"]
            for nome in valor.get("ordem") or list(campos):
                if nome not in campos:
                    continue
                info = campos[nome]
                self._p(">b", info["tipo"])
                self.texto(nome)
                self.carga(info["tipo"], info["valor"])
            self._p(">b", FIM)
        else:
            raise ValueError(f"tipo NBT desconhecido ao gravar: {tipo}")

    def arquivo(self, nome_raiz, composto):
        self._p(">b", COMPOSTO)
        self.texto(nome_raiz)
        self.carga(COMPOSTO, composto)
        return b"".join(self.partes)


def composto(pares):
    """Monta um composto NBT a partir de uma lista de (nome, tipo, valor)."""
    campos = {}
    ordem = []
    for nome, tipo, valor in pares:
        campos[nome] = {"tipo": tipo, "valor": valor}
        ordem.append(nome)
    return {"__composto__": True, "campos": campos, "ordem": ordem}


# ---------------------------------------------------------------------
# Lista de servidores
# ---------------------------------------------------------------------

def _normalizar_ip(ip: str) -> str:
    ip = (ip or "").strip().lower()
    if ip.endswith(":25565"):
        ip = ip[:-6]
    return ip


def garantir_servidor(game_dir, nome_servidor, ip_servidor, log=None):
    """
    Garante que o servidor esteja na lista de multijogador.
    Devolve (mudou, mensagem).
    """
    def aviso(msg):
        if log:
            log(msg)

    caminho = Path(game_dir) / "servers.dat"
    raiz_nome = ""
    lista = None

    if caminho.exists():
        try:
            bruto = caminho.read_bytes()
            if bruto[:2] == b"\x1f\x8b":
                bruto = gzip.decompress(bruto)
            raiz_nome, raiz = LeitorNBT(bruto).raiz()
            campo = raiz["campos"].get("servers")
            if campo and campo["tipo"] == LISTA:
                lista = campo["valor"]
            else:
                lista = {"__lista__": True, "tipo": COMPOSTO, "itens": []}
                raiz["campos"]["servers"] = {"tipo": LISTA, "valor": lista}
                if "servers" not in raiz["ordem"]:
                    raiz["ordem"].append("servers")
        except Exception as exc:
            aviso(f"  Nao consegui ler a lista de servidores: {exc}")
            return False, "servers.dat existente nao pode ser lido; nada foi alterado"
    else:
        lista = {"__lista__": True, "tipo": COMPOSTO, "itens": []}
        raiz = composto([("servers", LISTA, lista)])

    # Ja esta na lista?
    alvo = _normalizar_ip(ip_servidor)
    for item in lista["itens"]:
        try:
            atual = item["campos"].get("ip", {}).get("valor", "")
        except Exception:
            continue
        if _normalizar_ip(atual) == alvo:
            return False, "o servidor ja estava na sua lista"

    lista["itens"].append(composto([
        ("ip", TEXTO, ip_servidor),
        ("name", TEXTO, nome_servidor),
    ]))
    lista["tipo"] = COMPOSTO

    # copia de seguranca antes de gravar
    if caminho.exists():
        try:
            shutil.copy2(caminho, caminho.with_suffix(".dat.bak"))
        except Exception:
            pass

    try:
        dados = GravadorNBT().arquivo(raiz_nome, raiz)
        temporario = caminho.with_suffix(".dat.novo")
        temporario.write_bytes(dados)
        temporario.replace(caminho)
    except Exception as exc:
        return False, f"nao consegui gravar a lista de servidores: {exc}"

    return True, f"{nome_servidor} adicionado a lista de multijogador"


# ---------------------------------------------------------------------
# Perfil do launcher
# ---------------------------------------------------------------------

def descobrir_versao_forge(game_dir, mc_version, forge_version):
    """Encontra o nome da pasta de versao do Forge dentro de versions/."""
    versoes = Path(game_dir) / "versions"
    if not versoes.exists():
        return None
    try:
        nomes = [d.name for d in versoes.iterdir() if d.is_dir()]
    except Exception:
        return None

    preferidos = [
        f"{mc_version}-forge-{forge_version}",
        f"forge-{mc_version}-{forge_version}",
    ]
    for p in preferidos:
        for n in nomes:
            if n.lower() == p.lower():
                return n
    for n in nomes:
        baixo = n.lower()
        if "forge" in baixo and forge_version in baixo and mc_version in baixo:
            return n
    for n in nomes:
        baixo = n.lower()
        if "forge" in baixo and mc_version in baixo:
            return n
    return None


def _ajustar_arquivo_de_perfis(caminho, versao_id, nome_perfil, log=None):
    """
    Deixa o perfil do Forge selecionado. Serve tanto para o launcher oficial
    (launcher_profiles.json) quanto para o TLauncher (TlauncherProfiles.json),
    porque os dois usam a mesma ideia de 'profiles' e 'selectedProfile'.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return False, None

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        if log:
            log(f"  Nao consegui ler {caminho.name}: {exc}")
        return False, None
    if not isinstance(dados, dict):
        return False, None

    perfis = dados.get("profiles")
    if not isinstance(perfis, dict):
        perfis = {}
        dados["profiles"] = perfis

    # Ja existe um perfil apontando para essa versao?
    chave_escolhida = None
    for chave, perfil in perfis.items():
        if isinstance(perfil, dict) and perfil.get("lastVersionId") == versao_id:
            chave_escolhida = chave
            break

    if chave_escolhida is None:
        chave_escolhida = nome_perfil
        perfis[chave_escolhida] = {
            "name": nome_perfil,
            "type": "custom",
            "lastVersionId": versao_id,
        }
        criou = True
    else:
        criou = False

    dados["selectedProfile"] = chave_escolhida
    if "selectedProfileName" in dados:
        dados["selectedProfileName"] = perfis[chave_escolhida].get("name", nome_perfil)

    try:
        shutil.copy2(caminho, caminho.with_suffix(caminho.suffix + ".bak"))
    except Exception:
        pass

    try:
        temporario = caminho.with_suffix(caminho.suffix + ".novo")
        temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        temporario.replace(caminho)
    except Exception as exc:
        if log:
            log(f"  Nao consegui gravar {caminho.name}: {exc}")
        return False, None

    return True, ("perfil criado" if criou else "perfil existente selecionado")


def preparar_perfil(game_dir, mc_version, forge_version, nome_perfil, log=None):
    """Pre-seleciona o perfil do Forge nos launchers que guardam isso em arquivo."""
    versao_id = descobrir_versao_forge(game_dir, mc_version, forge_version)
    if not versao_id:
        return False, "nao encontrei a versao do Forge instalada para pre-selecionar"

    game_dir = Path(game_dir)
    resultados = []
    for arquivo in ("launcher_profiles.json", "TlauncherProfiles.json"):
        ok, detalhe = _ajustar_arquivo_de_perfis(game_dir / arquivo, versao_id,
                                                 nome_perfil, log=log)
        if ok:
            resultados.append(f"{arquivo}: {detalhe}")

    if not resultados:
        return False, "nenhum arquivo de perfis encontrado para ajustar"
    return True, f"perfil {versao_id} pre-selecionado ({'; '.join(resultados)})"


# ---------------------------------------------------------------------
# Tudo junto
# ---------------------------------------------------------------------

def preparar(game_dir, mc_version, forge_version, nome_servidor, ip_servidor,
             log=None):
    """
    Faz os dois preparos e devolve uma lista de mensagens do que aconteceu.
    Nunca levanta excecao: cada etapa e independente.
    """
    mensagens = []

    try:
        mudou, msg = garantir_servidor(game_dir, nome_servidor, ip_servidor, log=log)
        mensagens.append(msg)
    except Exception as exc:
        mensagens.append(f"lista de servidores: falhou ({exc})")

    try:
        ok, msg = preparar_perfil(game_dir, mc_version, forge_version,
                                  nome_servidor, log=log)
        mensagens.append(msg)
    except Exception as exc:
        mensagens.append(f"perfil do launcher: falhou ({exc})")

    return mensagens
