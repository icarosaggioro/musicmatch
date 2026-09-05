# 🎵 MusicMatch

> **AI-Native Local Music Management, Curation & DSP Playback System**  
> Um laboratório prático e didático de Engenharia de Software, Agentes Inteligentes de IA e Processamento Digital de Sinais (DSP).

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-99%25-success.svg)]()
[![Architecture](https://img.shields.io/badge/architecture-Harness%20%7C%20Pydantic%20V2-orange.svg)]()
[![License](https://img.shields.io/badge/license-MIT-informational.svg)]()

---

## 🎯 Propósito do Projeto

O **MusicMatch** foi concebido sob a perspectiva combinada de duas disciplinas de engenharia:
1. **Engenharia de Software Moderna**: Padrões de projeto consolidados (*Command Pattern*, *Event Loop Boundaries*, *Clean Architecture*, *Single Responsibility Principle*), orquestração de Agentes de IA, integridade estrita de dados em tempo de execução via **Pydantic V2** e interoperabilidade de alta performance com **Rust (PyO3/Maturin)**.
2. **Engenharia de Som & DSP / Music AI**: Processamento de sinais de áudio, psicoacústica e peculiaridades do formato MP3 (taxas CBR/VBR, bancos de filtros MDCT, *bit reservoir*, tags ID3), medição de *Loudness* percebido (**LUFS / EBU R128**), detecção de BPM/harmonia e escuta direta multimodal com modelos **Gemini**.

O objetivo final é criar uma aplicação que rode **100% local no Windows**, capaz de gerenciar, auditar e indexar grandes acervos musicais (10.000 a mais de 100.000 faixas) com busca instantânea em linguagem natural e total privacidade.

---

## 🏛️ Arquitetura do Sistema

O projeto adota a estratégia de evolução didática e incremental (**Walking Skeleton**), partindo da orquestração de alto nível em Python com stubs tipados e harness interativo, preparando as interfaces para a futura conexão com o motor nativo em Rust e persistência SQLite.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             ARQUITETURA MUSICMATCH                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  [ Interface / Harness ]                                                     │
│    ├── ConsoleUI (Apresentação, Banners, Observabilidade ReAct desacoplada)  │
│    ├── Command Registry (Slash Commands: /help, /status, /scan, /clear, /exit)│
│    └── Event Loop (Roteamento de Comandos vs Linguagem Natural)              │
│                             │ (Chamada Direta ou WebSockets / REST IPC)      │
│                             ▼                                                │
│  [ Camada de Orquestração & IA - Python 3.14.6 ]                             │
│    ├── Google Antigravity SDK & Google GenAI SDK (Gemini 3.6 Flash)         │
│    ├── Pydantic V2 (Modelos de Domínio, Validação e JSON Schemas)            │
│    ├── SingleTurnAgent (Ciclo ReAct com observabilidade em tempo real)       │
│    │                                                                         │
│    │  import musicmatch_core (Ponte PyO3 / Maturin - Roadmap)               │
│    ▼                                                                         │
│  [ Camada de Alta Performance & DSP - Rust ] (Roadmap)                       │
│    ├── Multi-threaded File Scanner (Rayon para 100k+ faixas)                 │
│    ├── Tag & Bitstream Parser (lofty / symphonia)                            │
│    ├── DSP Engine (BPM, LUFS EBU R128, Mini-Waveforms com SIMD)              │
│    └── Gravação Direta em Lote (SQLite + FTS5 + sqlite-vec)                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Stack Tecnológica

- **Linguagem & Runtime**: Python 3.14.6 (compatível com 3.11+)
- **SDK de Inteligência Artificial**: `google-genai` (Gemini 3.6 Flash com Function Calling e saídas estruturadas)
- **Modelagem de Domínio & Validação**: `pydantic` V2 (validação estrita em tempo de execução)
- **Harness & Interface**: Event Loop desacoplado com padrão *Command* e renderizador `ConsoleUI`
- **Testes & Cobertura**: `pytest`, `pytest-asyncio`, `pytest-cov`, `coverage` (**99% de cobertura**)
- **Ponte Nativa & DSP (Roadmap)**: Rust compilado via `PyO3` e `Maturin`

---

## 🚀 Como Começar

### Pré-requisitos
- **Python 3.11 ou superior** instalado.
- Chave de API do **Google AI Studio** (Gemini API) — obtenha gratuitamente em [aistudio.google.com](https://aistudio.google.com/).

### 1. Clonar o Repositório
```bash
git clone https://github.com/icarosaggioro/musicmatch.git
cd musicmatch
```

### 2. Criar e Ativar o Ambiente Virtual
No Windows (PowerShell):
```powershell
python -m venv .ve
.\.ve\Scripts\Activate.ps1
```

### 3. Instalar as Dependências
Instala o projeto em modo editável (`-e`) com as dependências de desenvolvimento e testes:
```powershell
pip install -e ".[dev]"
```

### 4. Configurar as Variáveis de Ambiente
Copie o arquivo de exemplo e insira sua chave da API do Gemini:
```powershell
cp .env.example .env
```
Edite o arquivo `.env`:
```env
GEMINI_API_KEY=sua_chave_gemini_aqui
GEMINI_MODEL=gemini-3.6-flash
LOG_LEVEL=INFO
```

---

## 🎮 Como Usar (Harness Interativo)

Para iniciar o MusicMatch, execute diretamente pelo terminal:
```powershell
musicmatch
```
*(Ou alternativamente: `python -m musicmatch.cli`)*

### A. Comandos Administrativos do Harness (Slash Commands)
O sistema conta com comandos rápidos iniciados com barra `/` que executam operações diretamente sem gastar tokens da LLM:

| Comando | Descrição |
| :--- | :--- |
| `/help` | Exibe a lista completa de comandos e instruções de uso. |
| `/status` | Exibe o modelo Gemini conectado, total de faixas indexadas e status do banco. |
| `/scan <caminho>` | Dispara a ferramenta de varredura diretamente (ex: `/scan C:/Musicas`). |
| `/clear` | Limpa a tela do terminal. |
| `/exit` | Encerra a aplicação (*aliases*: `sair`, `exit`, `quit`, `q`). |

### B. Interagindo com o Agente Inteligente ReAct
Qualquer entrada que não comece com `/` é automaticamente encaminhada ao Agente de IA, que utiliza raciocínio ReAct com logs de observabilidade em tempo real:

- **Acionamento de Ferramentas (Function Calling)**:
  ```text
  MusicMatch > Por favor, indexe as faixas do diretório C:/Musicas
  ```
  *O agente identificará a intenção, despachará a ferramenta `scan_library`, validará os dados via Pydantic, populará o banco e sintetizará um resumo.*

- **Dúvidas Conceituais sobre Áudio e DSP**:
  ```text
  MusicMatch > O que significa LUFS e como a norma EBU R128 é aplicada na normalização?
  MusicMatch > Qual é o impacto do Bit Reservoir no formato MP3 ao realizar cortes de áudio?
  ```
  *O agente responderá tecnicamente de forma direta, sem acionar ferramentas desnecessárias.*

---

## 🧪 Testes Automatizados e Cobertura

O projeto possui **37 testes unitários** automatizados, cobrindo o agente de IA com mocks determinísticos (sem consumo de tokens de API), validações do Pydantic, roteamento do harness e a interface visual:

```powershell
# Executa todos os testes
pytest

# Executa os testes com relatório detalhado de cobertura por linha
pytest --cov=musicmatch --cov-report=term-missing
```

### Relatório de Cobertura Atual: **99%**
```text
Name                                  Stmts   Miss  Cover
---------------------------------------------------------
src\musicmatch\__init__.py                1      0   100%
src\musicmatch\agent\core.py             44      0   100%
src\musicmatch\cli.py                    10      1    90%
src\musicmatch\commands\__init__.py       3      0   100%
src\musicmatch\commands\base.py          13      1    92%
src\musicmatch\commands\registry.py      84      0   100%
src\musicmatch\config.py                 10      0   100%
src\musicmatch\domain\models.py          24      0   100%
src\musicmatch\harness\__init__.py        2      0   100%
src\musicmatch\harness\loop.py           37      0   100%
src\musicmatch\storage\mock_db.py        20      0   100%
src\musicmatch\tools\scanner.py          11      0   100%
src\musicmatch\ui\__init__.py             2      0   100%
src\musicmatch\ui\renderer.py            53      0   100%
---------------------------------------------------------
TOTAL                                   314      2    99%
```

---

## 📚 Documentação & Decisões Arquiteturais (ADRs)

Todas as decisões arquiteturais e notas de pesquisa estão registradas e versionadas:
- [CONTEXT.md](CONTEXT.md): Dicionário de linguagem ubíqua (*Ubiquitous Language*) para evitar ambiguidades conceituais.
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): Diretrizes gerais, personas de atuação e direcionamento técnico.
- [docs/RESEARCH_INDEX.md](docs/RESEARCH_INDEX.md): Mapa de pesquisa cobrindo especificações MPEG-1/2 Layer III, técnicas de I/O em disco, SQLite FTS5/vetorial e comparativo de frameworks de agentes.
- **Registros de Decisão Arquitetural (ADRs)**:
  - [ADR 0001](docs/adr/0001-top-down-walking-skeleton-with-stubs.md): Top-Down Development via Walking Skeleton and Typed Tool Contracts.
  - [ADR 0002](docs/adr/0002-orchestrator-cli-repl.md): Orchestrator Architecture and CLI Observability REPL.
  - [ADR 0003](docs/adr/0003-didactic-incremental-evolution.md): Didactic Incremental Evolution Strategy.
  - [ADR 0004](docs/adr/0004-data-lifecycle-and-first-tool-selection.md): Data Lifecycle and First Tool Selection (`scan_library`).
  - [ADR 0005](docs/adr/0005-structured-cli-harness-and-commands.md): Structured CLI Harness with Command Registry and View Separation.
  - [ADR 0006](docs/adr/0006-domain-modeling-and-runtime-validation-with-pydantic.md): Domain Modeling and Runtime Validation with Pydantic.

---

## 📄 Licença

Este projeto é desenvolvido para fins didáticos e laboratoriais sob a licença MIT.
