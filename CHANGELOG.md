# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [0.2.0] - Em Desenvolvimento
### Adicionado
- Integração das bibliotecas `mediafile` e `pyacoustid` para leitura real de tags de áudio e fingerprint acústico.
- Motor de varredura real (`Scanner`) com suporte a múltiplos formatos (.mp3, .flac, .m4a, .aac, .ogg, .wav, .wma, .aiff, .opus).
- Implementação de idempotência estrita e **Stat-Cache** via `file_mtime` e `file_size` conforme **ADR 0009** ($O(1)$ para re-scans inalterados).
- Hash determinístico de caminho canônico SHA-256 para `Track.id`.
- Política de ciclo de vida não-destrutivo com soft-delete (`status = 'AVAILABLE' | 'MISSING'`).
- Novo comando `/scan` com métricas detalhadas de varredura e persistência.

---

## [0.1.0] - 2026-09-06
### Adicionado
- **Arquitetura Base (Walking Skeleton)**:
  - Sistema de orquestração em Python 3.14 com separação de responsabilidades (Clean Architecture / DDD).
  - Padrão **Command** no Harness interativo desacoplado da interface gráfica (`ConsoleUI`).
  - Despachante de comandos (`CommandRegistry`) com suporte a slash commands: `/help`, `/status`, `/scan`, `/search`, `/list`, `/clear`, `/exit`.
  - Persistência em **SQLite com FTS5** (*Full-Text Search*) e tabela de conteúdo externo sincronizada por gatilhos nativos (`AFTER INSERT`, `AFTER UPDATE`, `AFTER DELETE`).
  - Busca híbrida ranqueada por relevância Okapi BM25 combinada a filtros relacionais (BPM, gênero).
  - Contratos de domínio fortemente tipados com **Pydantic V2** (`Track`, `ScanResult`).
  - Camada de serviços de negócio (`LibraryService`) desacoplando o banco de dados das interfaces.
  - Orquestração de agentes com o **Google Antigravity SDK** e integração com modelos **Gemini 3.6 Flash** via `google-genai`.
  - Suíte de testes automatizados com `pytest` (73 testes unitários e de integração, 98% de cobertura).
- **Documentação Arquitetural**:
  - ADRs 0001 a 0009 documentando todas as decisões fundamentais do sistema.
