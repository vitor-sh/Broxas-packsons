"""
Gera o manifest de cada pack e o indice packs.json
==================================================

Percorre a pasta packs/, gera um manifest.json para cada pack e monta o
packs.json, que e o arquivo que o launcher le para saber quais modpacks
existem.

Uso (o robo do GitHub chama assim):
    python gerar_packs.py --repo vitor-sh/Broxas-packsons --versao 1.0.42
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
RAIZ_PACKS = Path("packs")


def sha1_de(caminho: Path) -> str:
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(1024 * 256), b""):
            h.update(pedaco)
    return h.hexdigest()


def ler_noticias(caminho: Path):
    if not caminho.exists():
        return []
    noticias, atual = [], None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        s = linha.strip()
        if s.startswith("#"):
            if atual:
                noticias.append(atual)
            atual = {"titulo": s.lstrip("#").strip(), "texto": ""}
        elif s:
            if atual is None:
                atual = {"titulo": "", "texto": ""}
            atual["texto"] = (atual["texto"] + " " + s).strip()
    if atual:
        noticias.append(atual)
    return noticias


def gerar_manifest(pasta_pack: Path, repo: str, versao: str):
    """Monta o manifest de um pack. Devolve (dados_do_pack, manifest)."""
    pid = pasta_pack.name
    cfg = json.loads((pasta_pack / "pack.json").read_text(encoding="utf-8"))
    mods_dir = pasta_pack / "mods"
    base_url = f"https://raw.githubusercontent.com/{repo}/main/packs/{pid}/mods"

    mods = []
    for jar in sorted(mods_dir.glob("*.jar")):
        mods.append({
            "name": jar.name,
            "url": f"{base_url}/{quote(jar.name)}",
            "sha1": sha1_de(jar),
            "size": jar.stat().st_size,
        })
    da_pasta = len(mods)

    externos_path = pasta_pack / "mods_externos.json"
    de_link = 0
    if externos_path.exists():
        extras = json.loads(externos_path.read_text(encoding="utf-8"))
        ja = {m["name"].lower() for m in mods}
        for item in extras.get("mods", []):
            nome, url = item.get("name"), item.get("url")
            if not nome or not url or nome.lower() in ja:
                continue
            mods.append({"name": nome, "url": url,
                         "sha1": item.get("sha1", ""), "size": item.get("size", 0)})
            ja.add(nome.lower())
            de_link += 1

    forge = cfg.get("forge", "47.4.20")
    mc = cfg.get("minecraft", "1.20.1")
    completo = f"{mc}-{forge}"

    manifest = {
        "pack_id": pid,
        "pack_nome": cfg.get("nome", pid),
        "pack_version": versao,
        "servidor": cfg.get("ip", ""),
        "minecraft": mc,
        "loader": f"Forge {forge}",
        "forge": {"version": forge,
                  "installer_url": f"{FORGE_MAVEN}/{completo}/forge-{completo}-installer.jar"},
        "noticias": ler_noticias(pasta_pack / "noticias.txt"),
        "mods": mods,
    }
    (pasta_pack / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    info = {
        "id": pid,
        "nome": cfg.get("nome", pid),
        "descricao": cfg.get("descricao", ""),
        "ip": cfg.get("ip", ""),
        "minecraft": mc,
        "loader": f"Forge {forge}",
        "mods": len(mods),
        "manifest": f"https://raw.githubusercontent.com/{repo}/main/packs/{pid}/manifest.json",
    }
    return info, manifest, da_pasta, de_link


def main():
    ap = argparse.ArgumentParser(description="Gera os manifests e o packs.json")
    ap.add_argument("--repo", required=True, help="usuario/repositorio no GitHub")
    ap.add_argument("--versao", required=True, help="versao dos packs (ex: 1.0.42)")
    args = ap.parse_args()

    if not RAIZ_PACKS.is_dir():
        raise SystemExit("ERRO: a pasta packs/ nao existe")

    pastas = sorted(p for p in RAIZ_PACKS.iterdir()
                    if p.is_dir() and (p / "pack.json").exists())
    if not pastas:
        raise SystemExit("ERRO: nenhum pack encontrado em packs/")

    indice = []
    print(f"Gerando {len(pastas)} pack(s), versao {args.versao}")
    print()
    for pasta in pastas:
        info, manifest, da_pasta, de_link = gerar_manifest(pasta, args.repo, args.versao)
        indice.append(info)
        tam = sum(m["size"] for m in manifest["mods"]) / 1024 / 1024
        print(f"  {info['nome']}  (packs/{pasta.name})")
        print(f"    {info['mods']} mods: {da_pasta} da pasta + {de_link} de link")
        print(f"    {tam:.0f} MB | {info['loader']} | {len(manifest['noticias'])} noticia(s)")
        sem_hash = [m["name"] for m in manifest["mods"] if not m["sha1"]]
        if sem_hash:
            print(f"    AVISO: {len(sem_hash)} mod(s) sem hash: {sem_hash[:3]}")
        print()

    Path("packs.json").write_text(
        json.dumps({"servidor": "BroxasSMP", "versao": args.versao, "packs": indice},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"packs.json gerado com {len(indice)} pack(s)")

    escrever_lista(pastas, args.versao)
    print("LISTA_DE_MODS.md gerado")


def escrever_lista(pastas, versao):
    """
    Escreve o LISTA_DE_MODS.md a partir dos manifests. Fica sempre em dia,
    porque e refeito a cada publicacao.
    """
    linhas = ["# Lista de mods dos packs", "",
              f"Gerado automaticamente na versao {versao}. Nao edite na mao.", ""]

    for pasta in pastas:
        manifest = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
        mods = manifest["mods"]
        nomes_pasta = {j.name for j in (pasta / "mods").glob("*.jar")}
        na_pasta = sorted((m for m in mods if m["name"] in nomes_pasta),
                          key=lambda m: m["name"].lower())
        por_link = sorted((m for m in mods if m["name"] not in nomes_pasta),
                          key=lambda m: m["name"].lower())
        total_mb = sum(m["size"] for m in mods) / 1024 / 1024

        linhas += [f"## {manifest['pack_nome']}  (`packs/{pasta.name}/`)", "",
                   f"{len(mods)} mods | {total_mb:.0f} MB | {manifest['loader']}", "",
                   f"### Guardados aqui no repositorio ({len(na_pasta)})", "",
                   f"Ficam em `packs/{pasta.name}/mods/`. Da para adicionar e remover "
                   "pelo site do GitHub.", ""]
        for m in na_pasta:
            linhas.append(f"- {m['name']}  ({m['size']/1024/1024:.2f} MB)")

        linhas += ["", f"### Baixados por link oficial ({len(por_link)})", "",
                   f"Ficam em `packs/{pasta.name}/mods_externos.json`. Nao ocupam "
                   "espaco no repositorio.", ""]
        for m in por_link:
            linhas.append(f"- {m['name']}  ({m['size']/1024/1024:.2f} MB)")
        linhas.append("")

    Path("LISTA_DE_MODS.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
