# ADR-009: Arquitetura Multi-Linguagem para Inferência de Alta Performance (Desacoplamento Cold/Hot Path)

- **Conformidade ISM:** M2 (Arquitetar — Modelos Lineares Calibrados e Álgebra Vetorial) & M3 (Orquestrar — OmniRoute Gateway, Zero GC e SLAs de Produção)
- **Relacionada a:** [ADR-005](0005-alinhamento-apm-e-omniroute-gateway.md), [ADR-006](0006-taxonomia-de-capacidades-e-colapso-de-duplicatas.md), [ADR-007](0007-calibracao-de-probabilidade-e-guarda-de-margem.md), [ADR-008](0008-guarda-de-direcao-leitura-escrita.md)
- **Documento de Referência:** [Proposta de Arquitetura Multi-Linguagem](../architecture/proposta-arquitetura-multi-linguagem.md)

---

## 1. Contexto

O pipeline desenvolvido e validado no MVP em Python (`candidate_starter`) alcançou 100% de acurácia no roteador e 100% de Hit Rate@2 no catálogo de 285 ferramentas bancárias com 0 execuções incorretas.

Entretanto, transpor esse pipeline diretamente para produção de escala bancária (milhares de RPS com p99 sub-10ms) esbarra em limitações estruturais intrínsecas ao ecossistema Python no *hot path* de requisições síncronas:
1. **O Global Interpreter Lock (GIL)**: Impede concorrência real multi-core em um mesmo processo, exigindo múltiplos processos pesados (Gunicorn/Uvicorn) e desperdiçando gigabytes de memória RAM.
2. **Jitter de Garbage Collection (GC)**: Mesmo em Python e Go, pausas imprevisíveis de GC sob alto volume de criação/destruição de strings e vetores degradam o percentil p99 de latência.
3. **Overhead de Runtimes Interpretados**: Operações puramente lineares de TF-IDF e multiplicação vetorial contra 285 documentos consomem tempo desnecessário de dispatch dinâmico.

## 2. Decisão

Adotar uma **Arquitetura Multi-Linguagem Estrita**, segregando rigidamente o ciclo de vida do sistema em dois caminhos independentes:

1. **Cold Path (Pesquisa, Treinamento e MLOps em Python 3.12)**:
   - Python permanece como linguagem exclusiva para treinamento com `scikit-learn`, calibração com `CalibratedClassifierCV` (Platt Scaling), testes adversariais, cálculo de SHAP e geração de artefatos.
   - O pipeline de CI/CD exporta artefatos determinísticos imutáveis e versionados: `model.onnx` (ou pesos lineares nativos), vocabulário TF-IDF com pesos `idf`, matriz CSR pré-computada dos documentos do catálogo (`doc_matrix.csr`) e regras de normalização.
   - O runtime de produção **nunca importa Python, numpy ou scikit-learn**.

2. **Hot Path (Gateway de Inferência em Rust como Primário ou Go como Secundário)**:
   - O OmniRoute Gateway é compilado em **Rust** (binário estático, container `distroless`), eliminando qualquer pausa de Garbage Collector e operando sob o paradigma *zero-allocation* no caminho crítico de processamento.
   - Alternativa secundária em **Go** permitida caso a equipe priorize agilidade de adoção, com disciplina estrita de buffers em `sync.Pool`.
   - **Motor Core Embutido (*In-Process*)**: Executa normalização de texto canônica (Unicode NFKD), projeção TF-IDF esparsa, inferência do classificador linear e produto escalar contra as matrizes pré-carregadas em memória.
   - **4 Camadas de Guard Rails Nativas**: Verificação de corte de probabilidade ($\ge 0.75$), score mínimo ($\ge 0.10$), margem relativa ($\ge 0.25$) e guarda de direção (leitura vs escrita) avaliadas em < 10 microsegundos.
   - Latência total do hot path (estágios 3 a 8 do pipeline) estabelecida em **< 1–3 ms p99**.

3. **Estratégia de Portabilidade**:
   - Fase 1: Inferência via ONNX Runtime (`ort` crate) para garantia imediata de paridade matemática sem risco de divergência.
   - Fase 2: Transição opcional para projeção e produto escalar nativos em Rust puro (tabela Hash de vocabulário + dot product esparso), reduzindo dependências externas a zero.

## 3. Consequências

### Positivas:
- **Latência Determinística**: Eliminação total de oscilações no p99; respostas servidas entre 0.5 ms e 1.5 ms.
- **Eficiência de Recursos e Custo**: Um único nó com 2 vCPUs suporta mais de 20.000 RPS, reduzindo a pegada de infraestrutura em mais de 80% comparado a pods Python.
- **Segurança Bancária**: Imutabilidade e segurança de memória garantidas pelo compilador Rust, sem vulnerabilidades de injeção dinâmica de código.
- **Governança e Testes de Paridade**: O pipeline de CI valida paridade matemática estrita ($\epsilon < 10^{-5}$) entre o modelo Python e a execução Rust antes de qualquer publicação de release.

### Negativas / Mitigações:
- **Duplicidade de Implementação da Lógica de NLP**: Regras de tokenização e remoção de acentos devem ser replicadas rigorosamente em Rust.  
  *Mitigação*: Criação de testes de regressão automatizados de paridade com *golden files* no CI/CD.
- **Curva de Aprendizado de Rust**: Maior complexidade de desenvolvimento inicial.  
  *Mitigação*: Alternativa em Go documentada e homologada caso a velocidade de manutenção sobreponha a necessidade de latência sub-milissegundo.
