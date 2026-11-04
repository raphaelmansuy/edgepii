# Model catalog

<!-- ste: descriptive -->

As of 4 November 2026. This catalog is a filter list, not a leaderboard. Hard filters come from [AI engineering](03-ai-engineering.md). The checkpoint must emit spans. The license must allow the intended use. V1 must run the weights on the host.

This catalog copies reported F1 values from the named card or paper. They are not `edgepii` results. Where two sources disagree, both numbers appear. The [golden set](09-evaluation.md) is the ranker.

## Defaults to implement first

| Preset | Hub id | Lane | Why this one is first |
| --- | --- | --- | --- |
| `en-closed` | [antoniogr7/pii-identifier-v0.1](https://huggingface.co/antoniogr7/pii-identifier-v0.1) | Closed encoder | ModernBERT, Apache-2.0 on the card, 55 BIO types, context 8192, English |
| `multi-open` | [fastino/gliner2-privacy-filter-PII-multi](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi) | Open schema | 2026-05 PII paper, type list at call time, seven languages on the card |
| `en-bert` | [ab-ai/pii_model](https://huggingface.co/ab-ai/pii_model) | Closed encoder | BERT-base control. Apache-2.0 on the card. About 29 types |
| `rules` | none | Rules | No download. Tests and structured types |

`phi-open` is [nvidia/gliner-PII](https://huggingface.co/nvidia/gliner-PII). Use it when the taxonomy includes health types. The card states an NVIDIA Open Model license. Read that license before a commercial default. Release note on the card: Hugging Face, 28 October 2025.

`zh-schema` is optional. See ModelScope below. It is not a default until a Chinese slice of the golden set exists.

## Closed encoders

| Hub id | Backbone | Languages on the card | Types on the card | License note | Span path |
| --- | --- | --- | --- | --- | --- |
| [antoniogr7/pii-identifier-v0.1](https://huggingface.co/antoniogr7/pii-identifier-v0.1) | ModernBERT-base | English | 55 BIO | Apache-2.0 | HF token-classification pipeline |
| [ab-ai/pii_model](https://huggingface.co/ab-ai/pii_model) | BERT-base-cased | English | About 29 | Apache-2.0 | HF token-classification pipeline |
| [ai4privacy/llama-ai4privacy-english-anonymiser-openpii](https://huggingface.co/ai4privacy/llama-ai4privacy-english-anonymiser-openpii) | ModernBERT-base | English | 20 OpenPII | MIT on the locate note's reading of the card. Re-read before pin | Token classification |
| [ai4privacy/llama-ai4privacy-multilingual-anonymiser-openpii](https://huggingface.co/ai4privacy/llama-ai4privacy-multilingual-anonymiser-openpii) | ModernBERT-base | Multi | 20 | See card | Token classification |
| [DataikuNLP/kiji-pii-model](https://huggingface.co/DataikuNLP/kiji-pii-model) | DeBERTa-v3-small + CRF | EN, DE, FR, ES, NL, DA | 26 BIO | Project blog says Apache-2.0. Confirm the file on the card | Custom head. Not `AutoModel` alone |
| [Wismut/nym-pii-multilingual](https://huggingface.co/Wismut/nym-pii-multilingual) | mmBERT | Many | 40 BIO | See card | Token classification |
| [obi/deid_bert_i2b2](https://huggingface.co/obi/deid_bert_i2b2) | ClinicalBERT | English clinical | PHI, BILOU | See card. Domain is clinical | Token classification |
| [obi/deid_roberta_i2b2](https://huggingface.co/obi/deid_roberta_i2b2) | RoBERTa | English clinical | PHI, BILOU | See card | Token classification |
| [StanfordAIMI/stanford-deidentifier-base](https://huggingface.co/StanfordAIMI/stanford-deidentifier-base) | Transformer de-id | English clinical | PHI | See card and the JAMIA paper | Token spans |
| [Isotonic/deberta-v3-base_finetuned_ai4privacy_v2](https://huggingface.co/Isotonic/deberta-v3-base_finetuned_ai4privacy_v2) | DeBERTa-v3-base | See card | OpenPII-shaped | See card | Token classification |
| [iiiorg/piiranha-v1-detect-personal-information](https://huggingface.co/iiiorg/piiranha-v1-detect-personal-information) | Token classifier | See card | PII | Card carries CC-BY-NC-ND. Not a default | Token classification |

The name `llama-ai4privacy-...-openpii` is a repo name. The backbone on the locate note is ModernBERT, not Llama. Trust the card's `base_model` field when you pin.

## Open-schema span models

| Hub id | Family | Languages | Types | License note | Call shape |
| --- | --- | --- | --- | --- | --- |
| [fastino/gliner2-privacy-filter-PII-multi](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi) | GLiNER2 | EN, FR, ES, DE, IT, PT, NL on the card | 42 | See card | `extract_entities`, with spans |
| [nvidia/gliner-PII](https://huggingface.co/nvidia/gliner-PII) | GLiNER large-v2.1 | Multi on the card | 55+ PII and PHI | NVIDIA Open Model | `{text, label, start, end, score}` |
| [urchade/gliner_multi_pii-v1](https://huggingface.co/urchade/gliner_multi_pii-v1) | GLiNER | Multi | Open PII labels | See card | `predict_entities` |
| [gretelai/gretel-gliner-bi-large-v1.0](https://huggingface.co/gretelai/gretel-gliner-bi-large-v1.0) | GLiNER bi-large | English | Open PII and PHI | See card | `predict_entities` |
| [knowledgator/gliner-pii-edge-v1.0](https://huggingface.co/knowledgator/gliner-pii-edge-v1.0) | GLiNER edge | See card | Open list at call time | See card | `predict_entities` |
| [knowledgator/gliner-pii-base-v1.0](https://huggingface.co/knowledgator/gliner-pii-base-v1.0) | GLiNER | See card | Open list | See card | Same. Named in the GLiNER2-PII paper table |

GLiNER label strings are not taxonomy types. The [label map](10-taxonomy.md) is mandatory. A label with no map becomes a dropped span and a counter, not a new public type.

## ModelScope

| Preset | Id | Task | Caution |
| --- | --- | --- | --- |
| `zh-schema` | [iic/nlp_structbert_siamese-uie_chinese-base](https://www.modelscope.cn/models/iic/nlp_structbert_siamese-uie_chinese-base) | Schema extraction | General IE, not a PII fine-tune. Prove offsets |
| none, pin only one | [damo/nlp_structbert_siamese-uie_chinese-base](https://www.modelscope.cn/models/damo/nlp_structbert_siamese-uie_chinese-base) | Same family | Do not load both |
| `eu-token-ms` | [onnx-community/multilang-pii-ner-ONNX](https://www.modelscope.cn/models/onnx-community/multilang-pii-ner-ONNX) | Token classification | EN, DE, IT, FR on the HF twin. Not Chinese |

Do not list `damo/nlp_raner_named-entity-recognition_chinese-base-generic` as a PII model. The output shape is a span, and the types are generic NER ([issue 274](https://github.com/modelscope/modelscope/issues/274)).

The adapter accepts a UIE hit only when the surface equals `source[start:end]`. If the live card uses an inclusive end, the adapter can try `end+1` one time. If neither slice matches, the adapter drops the hit. The adapter does not search the string for the surface.

## Reported numbers to keep out of gates

| Source | What it reports | Use |
| --- | --- | --- |
| [arXiv:2605.09973](https://arxiv.org/html/2605.09973) HTML table | SPY average F1 0.471 for GLiNER2-PII, above nvidia 0.391 and urchade 0.384 | Paper-reported. Protocol is theirs |
| fastino card | Average F1 0.477 on the card's SPY table | Disagrees with the paper table. Do not merge |
| antoniogr7 card | F1 0.9628, F2 0.9699 on Nemotron-PII test | In-domain. Not SPY |
| ab-ai card | F1 about 0.96 on "generator" | Train-like. Not a public shared task |
| [arXiv:2608.02616](https://arxiv.org/abs/2608.02616) | Cross-benchmark study of a privacy filter | Different protocol. Read it for the fine-tune crossover, not for our floor |
| knowledgator edge card | F1 on `synthetic-multi-pii-ner-v1` | Their set. Not our freeze |

## Selection rule

<!-- ste: procedural -->

1. Reject a checkpoint that does not return character offsets or BIO tags with offsets.
2. Reject a checkpoint whose license blocks the product.
3. Reject a remote API in v1.
4. Run the survivors on the dev freeze with the scorer.
5. Read the misses.
6. Promote a preset only after the sealed freeze meets the floors in the [evaluation spec](09-evaluation.md).

## Pinning

Each preset records `hub`, `repo_id`, `revision`, and `sha256` of the weight file. A floating `main` branch is not a preset. The locator prints the revision in debug output. It does not print the source string.

## Install extras

The core package has no torch dependency. Extras group the hubs so a rule-only test stays small.

| Extra | Installs | Presets |
| --- | --- | --- |
| `hf` | `transformers` | `en-closed`, `en-bert` |
| `gliner2` | `gliner2` | `multi-open` |
| `gliner` | `gliner` | `phi-open` and the GLiNER v1 cards |
| `ms` | `modelscope` | `zh-schema` |

The [implementation plan](08-implementation-plan.md) builds `rules` and the scorer before any extra.
