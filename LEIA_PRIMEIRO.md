# BroxasSMP Updater — O que fazer agora

## ✅ Boa notícia: o upload ficou 10x menor

O erro que você teve (`Commit failed — The file is too large`) é o limite de
**25 MB por arquivo** do upload pelo navegador do GitHub.

Resolvi isso de um jeito melhor: usei os hashes SHA-1 que você já tinha gerado
para consultar a **API do Modrinth** e descobrir o link oficial de cada mod.
Resultado:

| | Antes | Agora |
|---|---|---|
| Mods que você precisa enviar | 139 | **37** |
| Tamanho do upload | 282,8 MB | **28,6 MB** |
| Maior arquivo | 30,8 MB ❌ | **4,69 MB** ✅ |
| Precisa criar Release? | Sim | **Não** |

Os outros **102 mods são baixados direto do CDN oficial do Modrinth**. Isso
também deixa o download mais rápido pra galera e resolve a questão de licença
(não estamos re-hospedando esses mods).

Testei 5 links do Modrinth por HTTP: todos responderam **200** com o tamanho
exato conferindo com o hash.

---

## PASSO 1 — Subir os 37 mods

1. Na página inicial do repositório, clique na pasta **mods**
2. **Add file → Upload files**
3. Arraste **apenas os 37 arquivos** listados no `LISTA_DE_MODS.md`
   (seção *"VOCE PRECISA ENVIAR ESTES"*)
4. **Commit changes**

Agora cabe tudo de uma vez: 37 arquivos, 28,6 MB no total, nenhum acima de 25 MB.

> **Dica pra achar os arquivos rápido:** abra a sua pasta de mods, ordene por
> nome e vá selecionando com Ctrl+clique os 37 da lista. Ou copie os 37 pra uma
> pasta separada primeiro e arraste tudo de lá.

## PASSO 2 — Pegar o `.exe`

1. Aba **Actions** → espere ficar ✅ verde (2 a 4 minutos)
2. Página inicial → **Releases** → **BroxasSMP Updater**
3. Baixe o **`BroxasSMP-Updater.exe`**

**Pronto!** Manda o link do Releases no Discord. Ele é fixo: sempre aponta pra
versão mais nova.

---

## Os 37 arquivos que faltam

Estão todos no `LISTA_DE_MODS.md`. Os maiores:

```
4.69 MB  voicechat-forge-1.20.1-2.6.21.jar
3.63 MB  naturalist-5.0pre5+forge-1.20.1.jar
2.94 MB  Neruina-2.1.2-forge+1.20.1.jar
2.49 MB  cfm-forge-1.20.1-7.0.0-pre36.jar
2.49 MB  bettervillage-forge-1.20.1-3.3.1-all.jar
```
...e mais 32 arquivos, todos abaixo de 1,3 MB.

---

## Depois: como atualizar o pack

### Adicionar ou remover mod
1. Entre na pasta **mods** do repositório
2. Adicionar: *Add file → Upload files* e arraste
3. Remover: clique no arquivo → ícone de lixeira → *Commit changes*
4. Espere o ✅ na aba **Actions**

Acabou. O botão da galera vira **ATUALIZAR** sozinho.

> Se o mod novo passar de 25 MB, me chame: eu procuro o link oficial dele no
> Modrinth e adiciono no `mods_externos.json`, aí você não precisa enviar o arquivo.

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
| `mods_externos.json` | Os 102 mods com link oficial do Modrinth |
| `manifest.json` | A lista completa dos 139 mods |
| `pack.json` | Nome do servidor, IP, versões |
| `noticias.txt` | Notícias que aparecem no app |
| `LISTA_DE_MODS.md` | Quais mods enviar e quais são automáticos |
| `.github/workflows/publicar.yml` | O robô que compila o `.exe` |

---

## Se der erro

**❌ vermelho na aba Actions**
Clique no item pra ver a mensagem. Causa mais comum: a pasta `mods` está vazia.

**`Commit failed — file is too large`**
Algum arquivo acima de 25 MB entrou no upload. Confira a lista do
`LISTA_DE_MODS.md` — os 37 corretos são todos pequenos.

**Um mod não baixa no updater**
O nome do arquivo na pasta `mods` tem que ser **idêntico** ao do `manifest.json`.

**Antivírus reclamou do `.exe`**
Falso-positivo comum de programa feito com PyInstaller. Avise a galera.
