# Perguntas douradas — régua do retrieval
Status: **implementado** — ver `scripts/golden.json` (pares canônicos) e `scripts/eval_retrieval.py`.

Data: 2026-09-23. Critério de acerto: chunk esperado no **top-5** (testar query PT e EN).
Localizações verificadas contra `storage/bm25.jsonl` (não chutadas).

## Q1 — Loss da VAE (caso difícil / honestidade)
- EN: `What is the loss function of a VAE?` · PT: `Como é a função de perda (loss) da VAE?`
- Esperado: `ch03_p108-110_0010` (Cap 3, "The Loss Function", livro pp. 80-82).
- Por que é ouro: os termos **ELBO / lower bound / evidence não existem em nenhum dos 196 chunks**
  (só "KL divergence" em 6 chunks do Cap 3). Ou a extração do PyMuPDF manglou a equação, ou o livro
  não usa o termo. Testa se o modelo é honesto ("não encontrei ELBO") em vez de alucinar.

## Q2 — Reparameterization trick (definição pontual)
- EN: `How does the reparameterization trick work in VAEs?` · PT: `Como funciona o truque de reparametrização?`
- Esperado: `ch03_p106-108_0009` (Cap 3, "The Encoder", livro pp. 78-80).

## Q3 — Discriminador GAN (conceito + código)
- EN: `How does the GAN discriminator work in the DCGAN example?` · PT: `Como funciona o discriminador da GAN no exemplo DCGAN?`
- Esperado: `ch04_p126-129_0002` (Cap 4, "The Discriminator", livro pp. 98-101, chunk `code`).

## Q4 — GANs vs Diffusion (cross-capítulo)
- EN: `How do GANs and diffusion models differ?` · PT: `Qual a diferença entre GANs e diffusion models?`
- Esperado: ≥1 chunk do Cap 4 **e** ≥1 do Cap 8 no top-5. Testa cobertura multi-capítulo.

## Q5 — Cosine diffusion schedule (seção específica)
- EN: `What is the cosine diffusion schedule?` · PT: `O que é o cosine diffusion schedule?`
- Esperado: `ch08_p238-240_0003` ou `ch08_p240-242_0004` (Cap 8, "Diffusion Schedules", livro pp. 210-214).

## Como medir (implementado)
`scripts/eval_retrieval.py` roda as 5 perguntas por idioma e mede hit (1/0) + posição do 1º acerto
por estágio (denso / híbrido+RRF / final). Rodar antes/depois de qualquer mudança (query EN, rechunk,
vectorless).

```bash
python scripts/eval_retrieval.py --lang all             # PT+EN
python scripts/eval_retrieval.py --lang en --no-rerank  # baseline sem cross-encoder
```

Baseline (2026-09-23): 5/10 no placar final; híbrido acha 9/10 no top-20; re-rank derrubava 4 →
default OFF. `scripts/demo_seed.py` (kit S5) segue pendente e é outro artefato.
