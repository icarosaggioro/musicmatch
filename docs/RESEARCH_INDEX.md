# Índice de Tópicos e Itens Pesquisados

Este documento serve como mapa de referência rápida para todos os tópicos conceituais, padrões, tecnologias e componentes investigados durante a concepção do projeto.

---

## 1. Engenharia de Áudio & Padrão MP3
* **MPEG-1/2 Audio Layer III (ISO/IEC 11172-3 / 13818-3)**:
  * Modelagem Psicoacústica (Limiar absoluto de audição, mascaramento em frequência, mascaramento temporal: *pre-masking* e *post-masking*).
  * Banco de Filtros Híbrido (32 sub-bandas polifásicas + MDCT de janelas longas/curtas para transientes e mitigação de *pre-echo*).
  * Modos de Canal (Stereo, Joint Stereo: Mid/Side e Intensity Stereo).
  * Estrutura do Frame (Syncword de 11/12 bits, Bitrate, Sample Rate, Padding, cálculo de tamanho do frame).
  * *Bit Reservoir* (Reservatório de bits, campo `main_data_begin` e impacto em cortes/seeking).
  * Metadados e Tags (ID3v1 nos últimos 128 bytes, ID3v2.3/v2.4 com frames flexíveis e imagens APIC).
  * Modos de Taxa de Bits (CBR, VBR com headers Xing/LAME/VBRI, ABR).
  * Artefatos Acústicos (*pre-echo*, *swishing/birdies*, cortes abruptos de frequência em low-bitrates).

---

## 2. Arquitetura para Grandes Bibliotecas de Áudio (10k a 100k+ Faixas)
* **Técnicas de I/O em Disco e Escala**:
  * *Selective / Range-based Parsing* (leitura dos primeiros KBs para ID3v2 e últimos bytes para ID3v1 sem carregar o arquivo completo).
  * Suporte a múltiplos formatos (MP3, FLAC com `VORBIS_COMMENT`, AAC/M4A com átomos `moov/udta`).
* **Banco de Dados & Indexação Local**:
  * SQLite com extensão **FTS5** (*Full-Text Search*) para buscas textuais instantâneas.
  * Busca vetorial embarcada via **`sqlite-vec` / `sqlite-vss`**.
  * Virtualização de Lista / Interface (*Virtual Scrolling / Windowing*) para renderizar apenas itens visíveis no viewport.
* **Métricas e Processamento de Áudio em Lote**:
  * *Audio Fingerprinting* para deduplicação acústica (Chromaprint / AcoustID).
  * Normalização de Loudness (EBU R128 / LUFS / ReplayGain 2.0).
  * Cache ultraleve de *Waveforms* (vetores de picos/RMS condensados em poucos bytes por faixa).
  * Análise Harmônica e Rítmica (Detecção de BPM, Grid de Batidas, *Camelot Wheel* / Tonalidade Musical).
  * Detecção de *Fake Lossless / Upscaled Transcodes* (auditoria espectral de cortes em 16kHz).

---

## 3. Orquestração de Agentes & Frameworks de IA
* **Frameworks de Agentes Comparados**:
  * **LangGraph**: Grafos de estado dirigidos (*State Graphs*), persistência/checkpoints (*time-travel*), controle determinístico e *human-in-the-loop*.
  * **CrewAI**: Abordagem baseada em papéis humanos (*Crews, Agents, Tasks, Manager*).
  * **Microsoft AutoGen (v0.4 / Magentic-One)**: Modelo de atores conversacionais para debates e tarefas abertas.
  * **LlamaIndex Workflows**: Fluxos dirigidos por eventos (*Event-Driven*) focados em dados e RAG.
* **Orquestradores de Filas Assíncronas de Alto Volume**:
  * BullMQ, Inngest, Celery/Arq e Filas Nativas em SQLite com Worker Threads.
* **Framework Selecionado**: **Google Antigravity SDK** com arquitetura de subagentes e suporte híbrido cloud/on-device.

---

## 4. Ecossistema Google AI & Antigravity
* **Google Antigravity SDK (`google-antigravity`)**:
  * Pilares conceituais: `Agent`, `Conversation`, `Connection`.
  * Configuração Híbrida:
    * `LocalAgentConfig`: Conexão com modelos em nuvem (Gemini).
    * `LiteRTAgentConfig`: Execução **100% on-device/local via GPU (CUDA/DirectX) ou NPU** com a família **Gemma 4** (sem API Key).
    * `LocalOpenAIAgentConfig`: Conexão a servidores locais (Ollama, LM Studio).
  * Delegação e orquestração de sub-agentes autônomos (`enable_subagents=True`, `SubagentConfig`).
  * Integração nativa com MCP (*Model Context Protocol*).
  * Triggers periódicos, eventos em background, hooks de ciclo de vida e políticas de segurança.
* **API Google Gemini (Interactions API / GenAI SDK)**:
  * Modelos de referência: `gemini-3.6-flash`, `gemini-3.1-pro-preview`.
  * **Entrada Nativa de Áudio Multimodal**: O modelo processa arquivos de áudio brutos (.mp3, .wav) para identificar instrumentos, arranjos, timbres, transcrições e emoção na voz.
  * Janela de contexto massiva (1M+ tokens) para análise cruzada de discografias e catálogos.
  * Saídas estruturadas garantidas (*Structured Outputs / JSON Schema*).
  * **Gemini Live API**: Streaming bidirecional de áudio via WebSockets para assistentes e DJs conversacionais por voz em tempo real.

---

## 5. Tecnologias de Interface & Execução (Desktop & Web)
* **Conceitos de Plataforma Analisados**:
  * **Electron**: Chromium + Node.js embutidos (muito maduro, alto uso de RAM).
  * **Tauri (v2)**: WebView nativa do SO + Backend em Rust (ultraleve, alta performance de I/O).
  * **WebUI / pywebview**: Abordagem minimalista usando backend local abrindo janela web nativa ou navegador.
  * **WASM (WebAssembly)**: Código binário no navegador (`minimp3.wasm`, DSPs em *AudioWorklets*, SQLite WASM/OPFS).
* **Status**: *Opções mapeadas; escolha final da interface gráfica a ser definida em breve.*

---

## 6. Stack e Linguagens Confirmadas (Python 3.14.6 + Rust)
* **Python 3.14.6**:
  * Orquestrador de Agentes (Google Antigravity SDK).
  * Integração com APIs Gemini e modelos On-Device (LiteRT).
  * Servidor de APIs e WebSockets (FastAPI).
* **Rust**:
  * Extensão nativa compilada (`musicmatch_core`) para algoritmos de alta velocidade.
  * Varredura multi-thread de disco com `Rayon`.
  * Leitura e manipulação de metadados e bitstreams (`lofty`, `symphonia`).
  * Motor numérico de DSP (BPM, LUFS, Waveform picos com SIMD).
* **Ponte de Interoperabilidade**:
  * **`PyO3` + `Maturin`**: Geração de binários C-ABI nativos (`.pyd`) consumidos diretamente em Python sem overhead de IPC.

---

## 7. Resultados do Grill-Me (Adoção do Rust & Padrões FFI)
* **Eliminação do Gargalo do GIL/FFI**: O Rust grava os resultados da indexação diretamente no SQLite local em lote (*batch insert*). Nenhum array volumoso de objetos trafega pela ponte Python/Rust.
* **Comunicação por Eventos Assíncronos**: O Rust dispara eventos assíncronos (notificações/callbacks de progresso) para o Python, mantendo a thread principal e a UI 100% responsivas.
* **Resiliência e Auditoria**: Rust isola erros de decodificação e arquivos corrompidos sem usar `panic!`, gravando relatórios de integridade para o Agente Auditor do Antigravity processar.
* **Build & Distribuição**: Uso do `Maturin` para desenvolvimento simplificado (`maturin develop`) e geração de binários pré-compilados (.pyd) transparentes para o usuário final.
