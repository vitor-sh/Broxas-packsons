"""
Verificacao do manifest antes de publicar
=========================================

Testa se TODOS os mods do manifest realmente podem ser baixados. Serve para
o robo do GitHub falhar quando algo quebrou, em vez de a galera descobrir na
hora de jogar.

Confere, para cada mod:
  - o endereco responde (HTTP 200)
  - o tamanho do arquivo confere com o registrado no manifest

Uso:
    python verificar_manifest.py manifest.json
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

AGENTE = "BroxasUpdater/1.0 (verificacao)"

# Da para aumentar pelas variaveis de ambiente. O robo do GitHub usa valores
# maiores, porque arquivo recem-enviado leva alguns minutos para aparecer no
# raw.githubusercontent.com e um 404 nesse caso e falso alarme.
TENTATIVAS = int(os.getenv("VERIFICAR_TENTATIVAS", "3"))
ESPERA = int(os.getenv("VERIFICAR_ESPERA", "6"))       # segundos entre tentativas
LINHAS_DE_TRABALHO = int(os.getenv("VERIFICAR_LINHAS", "8"))


def _contexto():
    try:
        import certifi
        import ssl
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _consultar(url, metodo="HEAD"):
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=40, context=_contexto()) as resp:
        tamanho = resp.headers.get("Content-Length")
        return resp.status, int(tamanho) if tamanho else None


def verificar_um(entrada):
    """Devolve (nome, ok, mensagem)."""
    nome = entrada.get("name", "(sem nome)")
    url = entrada.get("url", "")
    esperado = entrada.get("size") or 0

    if not url:
        return nome, False, "sem endereco no manifest"
    if not url.startswith("https://"):
        return nome, False, f"endereco nao usa https: {url}"

    ultimo_erro = "erro desconhecido"
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            status, tamanho = _consultar(url)
            if status != 200:
                ultimo_erro = f"respondeu HTTP {status}"
            elif esperado and tamanho and tamanho != esperado:
                # tamanho diferente indica arquivo trocado sem atualizar o hash
                return nome, False, (f"tamanho diferente: manifest diz {esperado} "
                                     f"bytes, servidor devolveu {tamanho}")
            else:
                return nome, True, "ok"
        except urllib.error.HTTPError as exc:
            ultimo_erro = f"HTTP {exc.code}"
            if exc.code == 405:      # servidor nao aceita HEAD
                try:
                    status, tamanho = _consultar(url, metodo="GET")
                    if status == 200:
                        return nome, True, "ok (via GET)"
                    ultimo_erro = f"HTTP {status}"
                except Exception as exc2:
                    ultimo_erro = str(exc2)
            elif exc.code not in (404, 429, 500, 502, 503):
                break                # erro que nao melhora com nova tentativa
        except Exception as exc:
            ultimo_erro = str(exc)

        if tentativa < TENTATIVAS:
            time.sleep(ESPERA)

    return nome, False, ultimo_erro


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else "manifest.json"
    with open(caminho, encoding="utf-8") as f:
        manifest = json.load(f)

    mods = manifest.get("mods", [])
    if not mods:
        print("::error::O manifest nao tem nenhum mod.")
        return 1

    print(f"Conferindo {len(mods)} mods do pack v{manifest.get('pack_version','?')}")
    print()

    # avisa sobre nomes repetidos, que fariam um mod sobrescrever o outro
    vistos, repetidos = set(), set()
    for m in mods:
        n = (m.get("name") or "").lower()
        if n in vistos:
            repetidos.add(m.get("name"))
        vistos.add(n)

    falhas = []
    with ThreadPoolExecutor(max_workers=LINHAS_DE_TRABALHO) as executor:
        for nome, ok, msg in executor.map(verificar_um, mods):
            if ok:
                print(f"  ok      {nome}")
            else:
                print(f"  FALHOU  {nome}  ->  {msg}")
                falhas.append((nome, msg))

    print()
    print("=" * 62)
    print(f"  Conferidos : {len(mods)}")
    print(f"  Com falha  : {len(falhas)}")
    print(f"  Repetidos  : {len(repetidos)}")
    print("=" * 62)

    for nome in sorted(repetidos):
        print(f"::warning::Mod repetido no manifest: {nome}")

    if falhas:
        print()
        for nome, msg in falhas:
            print(f"::error::{nome}: {msg}")
        print()
        print("::error::O manifest NAO foi publicado. Corrija os itens acima "
              "e envie de novo. A galera continua com a versao anterior, "
              "que funciona.")
        return 1

    print()
    print("Todos os mods podem ser baixados. Manifest liberado para publicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
