# Diretrizes de Engenharia e Eficiência de Tokens

## 1. Princípio Ponytail (Anti-Bloat / Lean Code / YAGNI)
- Seguir a escada de decisão de 7 degraus:
  1. O recurso realmente precisa existir?
  2. Já existe no código?
  3. A biblioteca padrão (stdlib) resolve?
  4. A plataforma nativa resolve?
  5. As dependências já instaladas (`numpy`, `scikit-learn`) resolvem?
  6. Pode ser uma função concisa e direta?
  7. Escreva o mínimo absoluto de código robusto que atenda ao contrato.
- Jamais adicione frameworks pesados, bancos vetoriais externos ou abstrações desnecessárias para resolver contratos simples.

## 2. Princípio Caveman (Comunicação de Alta Densidade / Signal-to-Noise Ratio)
- Elimine preâmbulos, cumprimentos vazios e conclusões óbvias.
- Respostas orientadas a ação, status de execução, diffs objetivos e comandos reproduzíveis.
- Sempre preserve a clareza técnica e precisão em decisões de arquitetura e segurança.

## 3. RTK (Rust Token Killer) & Compressão de Contexto
- Comandos de terminal devem ter escopo estrito e outputs compactos (evitar logs excessivos não filtrados).
- Alinhar com a política de compressão de janela e orçamento de tokens por iteração descrita na especificação de produção.

## 4. OKF Agent Memory (Git-Native Knowledge Base)
- Todo conhecimento persistido no projeto segue a especificação Open Knowledge Format (OKF v0.2):
  - Arquivos Markdown puros com frontmatter YAML (`id`, `title`, `tags`, `progressive_tokens`).
  - Blocos conceituais atômicos (~300 tokens) para progressive disclosure, mitigando context bloat.
  - Auditabilidade total via controle de versão Git (`git diff`, `git log`).

## 5. OmniRoute Gateway Pattern (Resiliência e Roteamento Universal)
- O design de transição para produção deve absorver os princípios do OmniRoute:
  - Padrão de Gateway unificado com fallback resiliente e sensibilidade a quotas.
  - Otimização de custos combinando rotas baratas/locais e fallback inteligente para LLM/Handoff.
