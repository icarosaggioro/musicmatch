# 0010. Estratégia de Integração do yt-dlp, Gestão de Dependências e Empacotamento de CI/CD

## Contexto
Para implementar a **Frente 1 do Roadmap** (Ingestão Web e Download de Mídia a partir de plataformas como YouTube, SoundCloud e Bandcamp), o MusicMatch necessita do motor do **`yt-dlp`**.

Foi realizada uma análise aprofundada de arquitetura, segurança e engenharia de software ([`docs/YT-DLP_RELATORIO_TECNICO_E_SEGURANCA.md`](file:///c:/WebApps/musicmatch/docs/YT-DLP_RELATORIO_TECNICO_E_SEGURANCA.md)) e uma investigação empírica sobre como os maiores projetos abertos de mídia no GitHub estruturam essa integração (referências: **spotDL**, **MeTube** e **yt-dlg**).

Avaliaram-se os seguintes fatores críticos:
1. **O Fenômeno do *Bitrot* Acelerado**: Plataformas de vídeo alteram algoritmos de assinatura (`n-sig`), desafios JavaScript e tokens de atestação (WebPO / Botguard) semanalmente. Congelar código do `yt-dlp` dentro do repositório gera obsolescência e quebras funcionais constantes.
2. **Impacto no Repositório e Ferramental**: O `yt-dlp` possui mais de 1.700 extratores especializados e mais de 50 MB de código. Importar esse código manualmente para dentro da pasta [`src/`](file:///c:/WebApps/musicmatch/src) polui o histórico Git, degrada linters (`ruff`, `flake8`), contamina relatórios de cobertura de testes (`pytest-cov`) e quebra verificações estáticas no CI/CD.
3. **Fluxos de Integração Contínua (GitHub Actions) e Compilação para Produção**: Investigou-se como executáveis desktop (.exe) e pacotes de produção são gerados. Ficou comprovado que empacotadores como **PyInstaller**, **Nuitka** e imagens **Docker** inspecionam o ambiente virtual (`site-packages`), embutindo o `yt-dlp` compilado de forma transparente dentro do binário final, sem exigir que o código-fonte resida na pasta do projeto.
4. **Disponibilidade de Clone Local**: O desenvolvedor já mantém uma cópia ativa do repositório em `C:\WebApps\yt-dlp`.

---

## Decisão

1. **Isolamento Estrito do Código-Fonte (Zero Vendoring em `src/`)**:
   - O código-fonte do `yt-dlp` **não** será copiado para dentro de [`src/`](file:///c:/WebApps/musicmatch/src) nem mantido como pasta solta no repositório do MusicMatch.
   - O repositório Git do MusicMatch permanece 100% autoral, leve e focado no domínio de música, DSP e agentes.

2. **Dependência Declarativa Oficial em `pyproject.toml`**:
   - Adotar o `yt-dlp` como dependência declarada em [`pyproject.toml`](file:///c:/WebApps/musicmatch/pyproject.toml) (`yt-dlp>=2025.01.01`).
   - Essa abordagem garante compatibilidade nativa com ambientes virtuais, contêineres Docker e runners limpos do GitHub Actions.

3. **Ambiente Local de Desenvolvimento com Instalação Editável (`-e`)**:
   - Para o ciclo de desenvolvimento local, o ambiente virtual ([`.ve`](file:///c:/WebApps/musicmatch/.ve)) do MusicMatch é conectado diretamente ao repositório local existente em `C:\WebApps\yt-dlp`:
     ```powershell
     .ve\Scripts\pip install -e C:\WebApps\yt-dlp
     ```
   - Isso elimina duplicidade de espaço em disco e permite depuração com breakpoints e atualização contínua via `git pull` dentro da pasta `C:\WebApps\yt-dlp`.

4. **Camada de Adaptação e Segurança Arquitetural (Padrão Adapter)**:
   - A aplicação não consumirá o `yt-dlp` diretamente nos comandos de interface ou agentes.
   - Todo acesso será mediado pelo serviço [`AudioDownloaderService`](file:///c:/WebApps/musicmatch/src/musicmatch/services/downloader.py), aplicando as travas de segurança documentadas:
     - Bloqueio de protocolo local (`enable_file_urls: False`).
     - Prevenção de DoS com limite de duração (`match_filter` contra transmissões ao vivo 24/7).
     - Mitigação de SSRF (validação e sanitização de URLs externas).
     - Prevenção de Path Traversal via `prepare_filename` e IDs canônicos.
     - Execução assíncrona desacoplada da thread principal do REPL.

5. **Estratégia de CI/CD e Empacotamento**:
   - **GitHub Actions (CI)**: Runners configuram Python, instalam dependências via `pip install -e .` (com cache ativo de pacotes) e executam testes com mocks da camada de download.
   - **Produção / Executável Desktop**: Ao gerar o executável final via PyInstaller (`pyinstaller -F`), o empacotador coleta os binários e módulos do `yt-dlp` a partir do virtualenv, entregando um executável único `.exe` autocontido ao usuário final.

6. **Localização Física dos Arquivos Baixados**:
   - Mídias de áudio baixadas residirão na pasta dedicada `data/downloads/` (já protegida no `.gitignore`) ou em caminho configurado via `.env` (`MUSICMATCH_DOWNLOAD_DIR`).
   - Ao término do download, o arquivo é automaticamente catalogado pelo `AudioScanner` no banco de dados SQLite (`tracks` e `tracks_fts`).

---

## Consequências

- **Manutenibilidade Máxima**: Atualizações corretivas do YouTube são incorporadas via `pip install -U yt-dlp` ou `git pull` em `C:\WebApps\yt-dlp`, sem tocar no código do MusicMatch.
- **Repositório Enxuto**: Zero inchaço no Git e tempos de clone e commit ultrarrápidos.
- **Qualidade de Código Assegurada**: Linters, formatadores e cobertura de testes continuam analisando estritamente os módulos do MusicMatch.
- **Conformidade de CI/CD**: O pipeline do GitHub funciona de forma determinística e reproduzível em qualquer máquina sem acoplamento a caminhos locais fixos.

