# BroxasSMP Updater — O que fazer agora

Tudo já está montado neste repositório. **Falta só você subir os mods.**

---

## ⚠️ Antes: dois problemas que eu corrigi no seu manifest

Você tinha gerado o `manifest.json` (139 mods, hashes corretos 👍), mas as URLs
estavam apontando pra `releases/tag/mods`, que é a **página HTML** do release,
não o arquivo. Nenhum download funcionaria.

Corrigi as 139 URLs. E descobri outra coisa: o **navegador do GitHub só aceita
upload de arquivos até 25 MB**, e um mod seu passa disso:

| Mod | Tamanho | Onde vai |
|---|---|---|
| `heralds_luna-2.5-forge-1.20.1.jar` | 30.8 MB | Release `mods-grandes` |
| os outros 138 | até 24 MB | pasta `mods/` |

Já deixei isso configurado. Os hashes que você gerou foram todos aproveitados.

---

## PASSO 1 — Fazer o merge deste Pull Request

Na aba **Pull requests** do repositório, abra o PR que eu criei e clique em
**Merge pull request** → **Confirm merge**.

Isso ativa o robô que compila o `.exe`.

---

## PASSO 2 — Subir os 138 mods na pasta `mods/`

1. Na página inicial do repo, clique na pasta **mods**
2. **Add file → Upload files**
3. Arraste os `.jar` da sua pasta de mods
   - O GitHub aceita **100 arquivos por vez**, então faça em 2 tandas
   - **NÃO** suba o `heralds_luna-2.5-forge-1.20.1.jar` aqui (é o do passo 3)
4. **Commit changes**

> A lista completa está no arquivo `LISTA_DE_MODS.md`, se quiser conferir.

## PASSO 3 — Subir o mod grande num Release

1. Na página inicial do repo → lado direito → **Releases** → **Create a new release**
2. Em **Choose a tag**, digite exatamente:
   ```
   mods-grandes
   ```
   e clique em **Create new tag**
3. Em **Attach binaries**, arraste o **`heralds_luna-2.5-forge-1.20.1.jar`**
4. **Publish release**

## PASSO 4 — Pegar o `.exe`

1. Aba **Actions** → espere o item ficar ✅ verde (2 a 4 minutos)
2. Página inicial → **Releases** → **BroxasSMP Updater**
3. Baixe o **`BroxasSMP-Updater.exe`**

**Pronto!** Manda esse link do Releases no Discord. Ele é fixo: sempre vai
apontar pra versão mais nova.

---

## Depois: como atualizar o pack

### Trocar, adicionar ou remover mod
1. Entre na pasta **mods** do repositório
2. Adicionar: *Add file → Upload files* e arraste
3. Remover: clique no arquivo → ícone de lixeira → *Commit changes*
4. Espere o ✅ na aba **Actions**

Acabou. O botão da galera vira **ATUALIZAR** sozinho.

> Se o mod novo passar de 25 MB, suba no Release `mods-grandes` e adicione uma
> linha no `mods_externos.json` com o `name` e a `url`. O hash é opcional.

### Escrever notícias
Edite o **`noticias.txt`** pelo lápis:
```
# Cerco neste sábado
A janela é das 19h às 22h. Preparem os exércitos.
```

### Mudar IP ou versão do Forge
Edite o **`pack.json`**.

---

## O que cada arquivo faz

| Arquivo | Pra quê |
|---|---|
| `broxas_updater.py` | O aplicativo que a galera usa |
| `detector.py` | Acha as instalações de Minecraft do PC |
| `forge_setup.py` | Instala o Forge automaticamente |
| `gerar_manifest.py` | Monta a lista do pack |
| `pack.json` | Nome do servidor, IP, versões |
| `noticias.txt` | Notícias que aparecem no app |
| `mods_externos.json` | Mods hospedados fora da pasta `mods/` |
| `manifest.json` | A lista do pack (gerada automaticamente) |
| `LISTA_DE_MODS.md` | Conferência dos 139 mods |
| `.github/workflows/publicar.yml` | O robô que compila o `.exe` |

---

## Se der erro

**❌ vermelho na aba Actions**
Clique no item pra ver a mensagem. Causas comuns:
- A pasta `mods` está vazia → suba os `.jar`
- Faltou fazer o merge do PR

**Um mod não baixa no updater**
Confira se o nome do arquivo na pasta `mods` está **idêntico** ao do
`manifest.json`. Renomear arquivo quebra o link.

**Antivírus reclamou do `.exe`**
Falso-positivo comum de programa feito com PyInstaller. Avise a galera.

---

## ⚖️ Aviso sobre licença de mods

Vários mods **não permitem redistribuição**. Hospedar os `.jar` aqui é a forma
mais prática, mas pode contrariar a licença de alguns autores. A alternativa
segura é apontar a `url` de cada mod pro link oficial do CurseForge/Modrinth
no `manifest.json` — o updater aceita qualquer URL. Se quiser seguir esse
caminho, me chame que eu ajusto.
