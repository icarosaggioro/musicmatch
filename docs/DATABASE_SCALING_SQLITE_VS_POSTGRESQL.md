# Estudo Técnico de Engenharia: SQLite vs PostgreSQL em Larga Escala (1.000.000 de Faixas)

**Projeto**: MusicMatch  
**Data**: 2026-09-05  
**Autor**: Engenharia de Software & DSP / AI Architect  
**Status**: Referência Técnica & Roadmap de Migração Futura  

---

## 1. Contexto e Premissas do Cenário

O MusicMatch tem como visão gerenciar coleções volumosas de áudio com alta performance, integrando orquestração de agentes de Inteligência Artificial (**Google Antigravity SDK**), processamento de sinais de áudio / DSP em **Rust** e consultas expressivas em linguagem natural ou determinísticas.

Este estudo analisa formalmente a sustentabilidade do motor de persistência atual (**SQLite com FTS5**) em comparação com uma migração para **PostgreSQL (com `pgvector` e `pg_trgm`)**, considerando as seguintes condições de contorno:

1. **Volume de Catálogo**: 1.000.000 de faixas musicais indexadas.
2. **Consultas Multicritério Determinísticas / Procedimentais**:
   * **BPM**: Filtros por faixa, tolerância percentual ($\pm 5\%$) e relações harmônicas ($0.5\times$ *half-time*, $2.0\times$ *double-time*).
   * **Ano de Lançamento**: Janelas de proximidade temporal com decaimento gaussiano (ex: anos 80, anos 90, $\pm 3$ anos).
   * **Gênero Musical**: Similaridade categórica e hierárquica (ex: *House* $\approx$ *Tech-House*).
   * **Artista**: Correspondência aproximada e grafos de similaridade de estilo.
   * **Título**: Prioridade deliberadamente menor em buscas de recomendação/vibe.
   * **Métricas Musicais Estendidas**: Tipo de composição, andamento (*meter* / fórmula de compasso 4/4, 3/4), tonalidade (*Camelot Wheel* / Key), *Loudness* (LUFS EBU R128).
3. **Consultas Semânticas Comandadas por LLMs**:
   * Necessidade de componente vetorial (*embeddings* de áudio, humor, letras e descrições semânticas).
   * Consultas híbridas: mescla de restrições rígidas relacionais (*hard filters*) com ordenação por similaridade de cosseno de vetores densos.
4. **Ferramental Tradicional de Manutenção**:
   * Disponibilidade, ergonomia e profundidade de ferramentas clássicas de administração (DBeaver, DataGrip, pgAdmin, visualização de planos de execução `EXPLAIN ANALYZE`).
5. **Complexidade de Manutenção**:
   * Ponderada com peso moderado (a qualidade técnica da solução e a escalabilidade prevalecem sobre a complexidade de setup).

---

## 2. Dimensionamento e Volumetria para 1.000.000 de Faixas

### A. Tabela Relacional e Metadados Estruturados
* **Linha típica**: ID (UUID ou string curta), Título, Artista, Álbum, Gênero, Ano, Duração, Bitrate, BPM, Tonalidade, Compasso, Tipo de Composição, Caminho do Arquivo, Mood, LUFS, Timestamps.
* **Tamanho médio por tupla**: ~600 bytes.
* **Armazenamento bruto (1M registros)**: **~600 MB**.
* **Índices Relacionais B-Tree**:
  * `(bpm)`, `(year)`, `(genre)`, `(artist)`, `(file_path)`: **~350 MB a 500 MB**.

### B. Componente Textual / Trigramas
* Busca fonética e difusa (*fuzzy*) por artista, álbum e gênero (para absorver erros de digitação):
  * **Índices GIN com `pg_trgm` ou FTS5**: **~500 MB a 800 MB**.

### C. Componente Vetorial (Embeddings de Vibe / Áudio / LLM)
* **Dimensão do Vetor**: 768 dimensões (padrão de embeddings de texto do Gemini ou embeddings de áudio como CLAP/MuLan).
* **Armazenamento Bruto dos Vetores**:
  * Em `Float32` (4 bytes/dim): $768 \times 4 = 3.072\text{ bytes/faixa} \times 10^6 \approx \mathbf{3,07\text{ GB}}$.
  * Em `Halfvec` / Float16 (2 bytes/dim): $768 \times 2 = 1.536\text{ bytes/faixa} \times 10^6 \approx \mathbf{1,54\text{ GB}}$.
* **Índice Vetorial HNSW (Hierarchical Navigable Small World)**:
  * Sobrecarga de grafos de vizinhança: $1,3\times$ a $1,8\times$ o tamanho dos vetores brutos: **~2,5 GB a 5,0 GB**.

> **Resumo de Armazenamento Consolidado**:
> * **Total em Disco (Relacional + FTS + Vetores HNSW)**: **~6 GB a 9 GB**.
> * **Consumo de Memória Operacional Recomendado (RAM)**: Mínimo de **4 GB a 8 GB** dedicados ao banco de dados para manter páginas de índice HNSW em cache e evitar leituras aleatórias em SSD/NVMe.

---

## 3. Análise Comparativa dos Motores

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   MUSICMATCH ENGINE                    │
                    │               1.000.000 Faixas Musicais                │
                    └──────────────────────────┬─────────────────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
┌──────────────────────────────┐                              ┌──────────────────────────────┐
│       SQLite 3 + FTS5        │                              │   PostgreSQL 16 + pgvector   │
│   (Embarcado / In-Process)   │                              │     (Cliente / Servidor)     │
├──────────────────────────────┤                              ├──────────────────────────────┤
│ • Latência: ~10-30 µs        │                              │ • Latência: ~300-800 µs      │
│ • Arquivo único (.db local)  │                              │ • Daemon/Serviço (Porta 5432)│
│ • Single-Core por Query      │                              │ • Multi-Core Paralelo        │
│ • Single-Writer Lock (WAL)   │                              │ • MVCC Completo (Multi-write)│
│ • `sqlite-vec` experimental  │                              │ • `pgvector` industrial      │
│ • Ferramentas: Básicas       │                              │ • Ferramentas: Enterprise    │
└──────────────────────────────┘                              └──────────────────────────────┘
```

### 3.1. SQLite: Pontos Fortes e Gargalos Críticos

#### Vantagens
1. **Latência de Leitura Zero-IPC**:
   * O SQLite roda diretamente no espaço de memória da aplicação (Python ou Rust via FFI C-ABI). Não há serialização TCP, context-switch de SO ou loopback networking. Leituras unitárias ocorrem em microssegundos.
2. **Arquitetura Zero-Dependência**:
   * Todo o catálogo reside em um arquivo único (`musicmatch.db`).
   * Backup atômico simples (cópia direta do arquivo ou comando `VACUUM INTO`).
   * Distribuição para o usuário final sem necessidade de gerenciar serviços de segundo plano do Windows.
3. **Escrita em Lote Simples no Rust**:
   * A crate `rusqlite` permite que threads em Rust abram transações diretas com baixo consumo de memória.

#### Gargalos em 1.000.000 de Faixas
1. **Ausência de Paralelismo de Query (Gargalo Single-Core)**:
   * Uma consulta que calcula fórmulas matemáticas ponderadas de similaridade (BPM harmônico + proximidade de ano com decadência exponencial + distâncias de gênero) sobre dezenas de milhares de candidatos é executada em **uma única thread de CPU**. Em CPUs modernas de 8 a 16 núcleos, o SQLite deixa 85-95% do hardware ocioso, resultando em latências de 300ms a 1.200ms.
2. **Concorrência de Escrita (Single-Writer no WAL)**:
   * O modo WAL (*Write-Ahead Logging*) permite múltiplos leitores simultâneos, mas **apenas um único escritor por vez**.
   * Se o Scanner em Rust estiver executando a indexação inicial ou atualização de LUFS/BPM em segundo plano, tentativas do Agente Antigravity ou da UI de persistir preferências ou tags resultarão em contenção de locks (`SQLITE_BUSY`).
3. **Limitações do Ecossistema Vetorial (`sqlite-vec`)**:
   * Embora o `sqlite-vec` seja promissor, ele ainda carece de quantização de vetores madura, algoritmos HNSW em disco altamente particionados e suporte a *Iterative Index Scanning* com filtragem relacional combinada para 1M de registros. Manter 1M de vetores em RAM no SQLite compromete a leveza do app desktop.

---

### 3.2. PostgreSQL: Pontos Fortes e Trade-Offs

#### Vantagens
1. **Paralelismo Real de Consultas (`Parallel Query Execution`)**:
   * O planejador de consultas do Postgres divide varreduras e cálculos de similaridade em múltiplos *parallel worker threads*. Cálculos intensivos de distâncias numéricas e funções analíticas sobre 1M de linhas são executados em 30ms a 80ms.
2. **Maturidade Vetorial com `pgvector`**:
   * Suporte nativo a índices **HNSW** e **IVFFlat**.
   * Suporte a tipos **`halfvec`** (16 bits) e quantização binária, cortando o uso de RAM pela metade.
   * Suporte a **Iterative Index Search**: permite que filtros rígidos (`WHERE bpm BETWEEN 120 AND 130 AND year >= 1990`) sejam avaliados de forma coordenada com a travessia do grafo HNSW, evitando o problema clássico de nós vetoriais esgotados.
3. **MVCC Completo e Locks em Nível de Linha**:
   * Leituras e escritas não se bloqueiam mutuamente. O Scanner em Rust pode ingerir faixas continuamente enquanto o Agente consulta metadados e calcula recomendações sem contenção.
4. **Busca Textual Difusa Avançada (`pg_trgm`)**:
   * Correspondência de artistas e títulos por similaridade de trigramas com índices GIN, lidando com erros de digitação de forma superior ao FTS tradicional.
5. **Ferramental Tradicional de Nível Industrial**:
   * DBeaver, DataGrip e pgAdmin fornecem visualização gráfica completa de planos de execução (`EXPLAIN (ANALYZE, BUFFERS)`), identificando com precisão consumo de I/O em disco vs cache de memória.
   * Extensões como `pg_stat_statements` permitem identificar gargalos de queries geradas pelo LLM em tempo real.

#### Desvantagens / Trade-Offs
1. **Requisito de Serviço / Daemon**:
   * Exige a execução de um processo servidor PostgreSQL (serviço do Windows ou container Docker).
   * Para um app desktop, adiciona complexidade de empacotamento, alocação de portas de rede (5432) e permissões no firewall.
2. **Latência de IPC / Loopback TCP**:
   * Adiciona um piso mínimo de latência de ~300µs a 800µs por requisição devido ao protocolo de rede cliente-servidor (desprezível para queries complexas, mas perceptível em loops com milhares de queries unitárias).
3. **Consumo de Memória Basal**:
   * O PostgreSQL com pool de buffers configurado para 1M de linhas aloca de 1 GB a 2 GB de RAM de forma persistente.

---

## 4. Tabela de Comparação Direta

| Requisito do Projeto | SQLite (com FTS5 + `sqlite-vec`) | PostgreSQL (com `pgvector` + `pg_trgm`) |
| :--- | :--- | :--- |
| **Escala Relacional (1M faixas)** | Atende bem em consultas simples indexadas (B-Tree). | Atende com folga, excelente otimizador de custos. |
| **Similaridade Ponderada Multicritério** | Lenta em cálculos complexos (Single-Core CPU). | **Ultrarrápida** com paralelismo multi-thread. |
| **Componente Vetorial (1M de embeddings)** | Experimental, alto risco de saturação de RAM. | **Produção industrial** (HNSW + `halfvec` + Iterative Scan). |
| **Concorrência Ingestão vs Agente IA** | Risco de lock contention (`database is locked`). | **Concorrência total** via MVCC e lock por linha. |
| **Fuzzy Matching (Artista/Álbum)** | Limitado a prefixos/tokens FTS5. | **Excelente** via `pg_trgm` (trigramas GIN). |
| **Latência de Leitura Unitária** | **~10 a 30 µs** (C-ABI in-memory). | ~300 a 800 µs (Protocolo TCP loopback). |
| **Manutenção / Ferramentas Tradicionais** | Ferramentas simples (DB Browser, SQLiteStudio). | **Líder absoluto** (DBeaver, DataGrip, EXPLAIN detalhado). |
| **Instalação e Portabilidade Desktop** | **Perfeita**: Arquivo único local, zero-config. | Média/Alta: Exige daemon rodando ou Docker. |

---

## 5. Modelagem Proposta no PostgreSQL para 1M de Faixas

### DDL: Esquema com Suporte Relacional, Fuzzy Text e Vetores

```sql
-- Habilita extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Tabela principal de faixas
CREATE TABLE tracks (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    album VARCHAR(255) NOT NULL,
    genre VARCHAR(100) NOT NULL,
    year SMALLINT,
    bpm REAL NOT NULL CHECK(bpm > 0),
    composition_type VARCHAR(50), -- Ex: 'Instrumental', 'Vocal', 'Remix', 'Acoustic'
    meter VARCHAR(10) DEFAULT '4/4', -- Ex: '4/4', '3/4', '6/8'
    musical_key VARCHAR(10),        -- Ex: '8A', '11B' (Camelot Wheel)
    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0),
    bitrate_kbps INTEGER NOT NULL,
    file_path TEXT UNIQUE NOT NULL,
    mood VARCHAR(100),
    lufs REAL,
    -- Vetor denso de 768 dimensões em meia precisão (Float16) para economizar RAM
    embedding halfvec(768),
    created_at TIMESTAMPTZ DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ DEFAULT clock_timestamp()
);

-- Índices B-Tree para filtros numéricos e de janela
CREATE INDEX idx_tracks_bpm ON tracks(bpm);
CREATE INDEX idx_tracks_year ON tracks(year);
CREATE INDEX idx_tracks_key ON tracks(musical_key);
CREATE INDEX idx_tracks_comp_type ON tracks(composition_type);

-- Índices GIN de Trigramas para busca difusa em Artista e Gênero
CREATE INDEX idx_tracks_artist_trgm ON tracks USING gin (artist gin_trgm_ops);
CREATE INDEX idx_tracks_genre_trgm ON tracks USING gin (genre gin_trgm_ops);

-- Índice Vetorial HNSW (similaridade por Cosseno)
CREATE INDEX idx_tracks_embedding_hnsw 
ON tracks USING hnsw (embedding halfvec_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

### Exemplo de Query Híbrida de Recomendação / Similaridade

A consulta abaixo demonstra como o PostgreSQL resolve em uma única passagem:
1. **Pré-filtragem B-Tree**: Reduz o espaço amostral para faixas viáveis.
2. **Score de BPM Harmônico**: Bonifica tempo real ou variações de meio tempo (*half-time*) e dobro (*double-time*).
3. **Decaimento de Ano**: Função de Gauss para proximidade temporal.
4. **Similaridade de Gênero / Artista**: Trigramas difusos.
5. **Similaridade Vetorial Semântica**: Distância de cosseno gerada pelo LLM.
6. **Peso Mínimo para o Título**: Conforme requisito, o título não distorce o ranking musical.

```sql
WITH candidates AS (
    SELECT 
        id, title, artist, album, genre, year, bpm, musical_key,
        -- Similaridade harmônica de BPM
        CASE 
            WHEN abs(bpm - :target_bpm) <= 4 THEN 1.0
            WHEN abs(bpm - (:target_bpm * 0.5)) <= 3 THEN 0.8
            WHEN abs(bpm - (:target_bpm * 2.0)) <= 6 THEN 0.8
            ELSE 0.2
        END AS bpm_score,
        -- Decaimento Gaussiano de Ano (tolerância centrada no ano-alvo)
        exp(-power(coalesce(year, :target_year) - :target_year, 2) / 20.0) AS year_score,
        -- Similaridade de Gênero via Trigramas
        similarity(genre, :target_genre) AS genre_score,
        -- Similaridade Vetorial de Vibe/Semântica acionada pelo LLM
        (1 - (embedding <=> :target_vector::halfvec)) AS semantic_score
    FROM tracks
    WHERE 
        -- Filtros rápidos via índices tradicionais
        bpm BETWEEN (:target_bpm * 0.45) AND (:target_bpm * 2.1)
        AND year BETWEEN (:target_year - 15) AND (:target_year + 15)
)
SELECT 
    id, title, artist, album, genre, year, bpm, musical_key,
    -- Ranking Ponderado Final (Título ignorado no score)
    (
        0.35 * semantic_score +
        0.25 * bpm_score +
        0.25 * genre_score +
        0.15 * year_score
    ) AS similarity_score
FROM candidates
ORDER BY similarity_score DESC
LIMIT 50;
```

---

## 6. Conclusão e Recomendação Estratégica

### Decisão Técnica: **Migrar para PostgreSQL com `pgvector` na Fase de Alta Escala**

1. **Adequação ao Patamar de 1 Milhão de Faixas**:
   * O SQLite atende com perfeição até 100.000 faixas. Porém, ao atingir **1.000.000 de faixas com vetores densos de 768 dimensões e consultas multicritério ponderadas**, a falta de paralelismo de CPU e a imaturidade de índices vetoriais em larga escala no SQLite degradam a experiência do usuário.
2. **Suporte Vetorial de Primeira Linha**:
   * O `pgvector` com `halfvec` e HNSW permite manter 1M de vetores indexados em ~1,5 GB a 2 GB de RAM com respostas sub-40ms.
3. **Isolamento de Concorrência**:
   * O scanner multi-thread em Rust (`Rayon`) e o agente de IA (`Google Antigravity SDK`) podem ler e escrever simultaneamente sem locks de arquivo.
4. **Ferramental de Nível Enterprise**:
   * Facilidade total de inspeção e tuning de planos de execução via DBeaver / DataGrip.

---

## 7. Roteiro Prático de Migração (Migration Roadmap)

Para garantir que a transição ocorra de forma fluida e sem retrabalho quando o projeto atingir o estágio avançado:

### Fase 1: Preservar a Camada de Abstração Atual (Hoje)
* O MusicMatch já utiliza o padrão **Repository Pattern** (`SQLiteTrackRepository`) e modelos validados por **Pydantic V2** (`Track`).
* **Ação**: Manter o desenvolvimento das ferramentas do agente (`tools/search.py`, `tools/scanner.py`) e serviços (`LibraryService`) desacoplados de SQL bruto.

### Fase 2: Implementação do `PostgresTrackRepository` (Fase Futura)
* Criar a classe `PostgresTrackRepository` implementando a mesma interface pública de métodos (`insert_track`, `insert_batch`, `search_combined`, `get_stats`).
* No Python, utilizar drivers assíncronos de alta performance (`asyncpg` ou `psycopg3`).
* No Rust (`musicmatch_core`), utilizar a crate `tokio-postgres` com operações binárias `COPY` para garantir ingestão superior a 30.000 faixas/segundo.

### Fase 3: Ambiente e Execução
* Configurar um manifesto `docker-compose.yml` local com imagem oficial `pgvector/pgvector:pg16`.
* Adicionar flag de configuração no `.env` (`DATABASE_BACKEND=sqlite` ou `DATABASE_BACKEND=postgres`), permitindo alternar de forma transparente entre o SQLite local e o cluster PostgreSQL.
