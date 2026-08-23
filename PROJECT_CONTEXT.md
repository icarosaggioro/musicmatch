# MusicMatch - Contexto e Diretrizes do Projeto

## 1. Persona de Atuação
O projeto é concebido e conduzido sob a ótica combinada de duas disciplinas de engenharia:
* **Engenheiro de Software**: Arquitetura de sistemas, estruturas de dados, concorrência, otimização de I/O em disco, bancos de dados locais, APIs assíncronas, filas de processamento, interoperabilidade Python-Rust e orquestração de agentes.
* **Engenheiro de Som / Especialista em DSP & Music AI**: Processamento de sinais de áudio, psicoacústica, análise espectral (FFT), medição de loudness (LUFS/EBU R128), detecção de BPM e harmonia, transcrição musical, modelos neurais de áudio e curadoria acústica.

---

## 2. Diretrizes e Requisitos Definidos

### A. Domínio e Escopo
* **Manipulação e Reprodução de Áudio**: Foco inicial no formato MP3, com arquitetura expansível para outros formatos (FLAC, WAV, AAC, OGG, etc.).
* **Grandes Bibliotecas Locais**: Projetado para gerenciar e indexar coleções volumosas (10.000 a 100.000+ arquivos) com alta performance, baixo uso de memória e buscas instantâneas.
* **Plataforma / Ambiente**: Aplicação projetada para rodar **localmente no PC do usuário (Windows)**, garantindo privacidade, velocidade máxima de acesso ao disco e operação independente.

### B. Envolvimento Massivo de Inteligência Artificial (IA-Native)
* **Orquestração de Agentes**: Uso do **Google Antigravity SDK** para orquestrar agentes e subagentes autônomos para automação de tarefas, curadoria e auditoria.
* **Processamento Assíncrono em Lote**: Filas de tarefas em segundo plano para indexação, geração de mini-waveforms, extração acústica e análise de letras sem congelar a UI ou interromper a reprodução.
* **Compreensão Semântica & Multimodal**:
  * Análise de letras, identificação de humor (*mood*), geração de metadados enriquecidos e busca em linguagem natural por afinidade musical ("vibe").
  * Capacidades de escuta direta de áudio (multimodal via Gemini) para entender arranjos, timbres e características musicais.
  * Execução híbrida: Modelos em nuvem (Gemini 3.6 Flash / 3.1 Pro) e modelos locais on-device (família Gemma 4 via LiteRT/GPU).

### C. Stack Tecnológica Confirmada
* **Linguagem de Orquestração & Backend**: **Python 3.14.6**
  * Responsável pela orquestração de agentes com o **Google Antigravity SDK**, integrações de IA com `google-genai` e camada de serviço local (FastAPI / WebSockets).
* **Linguagem de Alta Performance & DSP**: **Rust**
  * Responsável por operações críticas de I/O em disco (varredura multi-thread de 100k arquivos com Rayon), leitura de tags/headers (`lofty`/`symphonia`), algoritmos numéricos de DSP (BPM, LUFS, Mini-Waveforms com SIMD) e manipulação ultrarrápida do SQLite.
  * **Padrão de FFI / Zero GIL Overhead**: O Rust processa os arquivos e grava em lote diretamente no SQLite local, notificando o Python por eventos assíncronos (sem converter centenas de milhares de objetos na memória).
  * **Tratamento Resiliente de Erros**: Arquivos corrompidos ou anômalos são catalogados em tabela de auditoria para inspeção pelo Agente Auditor do Antigravity.
  * **Ponte de Interoperabilidade**: **PyO3 + Maturin** (compilação de extensões nativas C-ABI em Rust consumíveis diretamente como módulos Python sem overhead de IPC).
* **Banco de Dados Local**: **SQLite** embarcado com **FTS5** (busca textual instantânea) e extensão vetorial (`sqlite-vec`).
* **Interface Gráfica**: *(Em definição / a ser escolhida em breve)*.

---

## 3. Direcionamento Arquitetural

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             ARQUITETURA MUSICMATCH                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  [ Interface Gráfica ] (A definir em breve)                                  │
│                             │ (WebSockets / REST IPC)                        │
│                             ▼                                                │
│  [ Camada de Orquestração & IA - Python 3.14.6 ]                             │
│    ├── Google Antigravity SDK (Agente Principal e Subagentes Autônomos)     │
│    ├── Google GenAI SDK (Gemini 3.6 Flash / 3.1 Pro Multimodal)              │
│    ├── Servidor Local de APIs (FastAPI / WebSockets)                         │
│    │                                                                         │
│    │  import musicmatch_core (Ponte PyO3 / Maturin - Dispara Tarefas)        │
│    ▼                                                                         │
│  [ Camada de Alta Performance & DSP - Rust ]                                 │
│    ├── Multi-threaded File Scanner (Rayon para 100k+ faixas)                 │
│    ├── Tag & Bitstream Parser (lofty / symphonia)                            │
│    ├── DSP Engine (BPM, LUFS EBU R128, Mini-Waveforms com SIMD)              │
│    ├── Tratamento de Erros & Log de Integridade (sem panics)                 │
│    └── Gravação Direta em Lote (SQLite + FTS5 + sqlite-vec)                  │
│                                                                              │
│  ◄── Evento Assíncrono de Conclusão / Progresso para o Python ───────────────┘
└──────────────────────────────────────────────────────────────────────────────┘
```
