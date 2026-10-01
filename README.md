# AWS Tutorial Dedup POC

**AWS ProServe Senior AI Application Architect L6 지원용 Bedrock PoC**

> MCP web_fetch로 AWS 튜토리얼 다중 버전 수집 → FAISS + Graph RAG로 중복 제거 → 최신 버전 다이제스트를 Streamlit으로 서빙

---

## 🎯 시나리오

AWS 공식 문서에는 동일한 기능(예: Bedrock Agent 설정)에 대해 여러 버전의 튜토리얼이 혼재합니다.  
이 PoC는 중복 문서를 자동으로 탐지·제거하고, **최신 버전 정보만 담은 깔끔한 다이제스트**를 제공합니다.

---

## 🏗️ 파이프라인 구조

### INGESTION (1회 실행)
```
AWS Docs URLs
    ↓ MCP web_fetch (httpx + html2text)
Raw Markdown
    ↓ Claude Sonnet 4.6 (메타데이터 추출)
Enriched Docs
    ↓ Titan Embed V2 → FAISS IndexFlatIP (cosine)
Vector Index  ←→  NetworkX DiGraph (supersedes / similar_to / uses)
    ↓
S3 (faiss_index.bin + graph.json + metadata.json + raw_docs/)
```

### QUERY (Streamlit 요청마다)
```
User Query
    ↓ Titan Embed V2
Query Vector
    ↓ FAISS top-k (cosine ≥ 0.75)
Seed Docs → Graph BFS (2홉 확장)
    ↓ Hybrid Context
Claude Sonnet 4.6 (Bedrock Guardrails 적용)
    ↓
Answer + Sources + Pyvis Graph
```

---

## 🛠️ 기술 스택

| 레이어 | 기술 |
|--------|------|
| **LLM** | Claude Sonnet 4.6 (`anthropic.claude-sonnet-4-6-20250514-v1:0`) |
| **Embedding** | Amazon Titan Embed Text V2 |
| **Vector DB** | FAISS (faiss-cpu, cosine similarity) |
| **Graph RAG** | NetworkX DiGraph (BFS 2홉 확장) |
| **Agent Framework** | Strands Agents (`@tool` 데코레이터) |
| **Web Scraping** | httpx + html2text (MCP web_fetch 패턴) |
| **Harness Engineering** | task.yaml 기반 문서 주도 파이프라인 |
| **Safety** | Amazon Bedrock Guardrails |
| **Storage** | Amazon S3 (ap-southeast-2) |
| **Frontend** | Streamlit Community Cloud + Pyvis |
| **Evaluation** | Bedrock LLM-as-Judge (Faithfulness / Relevancy / Recall) |

---

## 📁 디렉토리 구조

```
bedrock-agent-poc/
├── ingestion/
│   ├── task.yaml          # Harness: 태스크 문서 정의 (Agent가 S3에서 읽어 실행)
│   ├── web_fetch.py       # MCP web_fetch 도구 (@tool 데코레이터)
│   ├── agent.py           # Ingestion Agent (Strands + FAISS + NetworkX)
│   └── run_ingestion.py   # 1회 실행 스크립트
├── query/
│   ├── retriever.py       # FAISS + Graph BFS 하이브리드 검색
│   └── agent.py           # Query Agent (Bedrock Guardrails 포함)
├── portal/
│   └── app.py             # Streamlit 포털 (다이제스트 + 그래프 + Q&A)
├── evals/
│   └── eval.py            # Bedrock LLM-as-Judge 평가
├── .env                   # 환경변수 (git 제외)
├── .env.example           # 환경변수 템플릿
├── requirements.txt       # 의존성
└── README.md
```

---

## 🚀 실행 방법

### 1. 환경 설정
```bash
cp .env.example .env
# .env에 AWS 자격증명 입력
```

### 2. 패키지 설치
```bash
/opt/anaconda3/bin/python -m pip install -r requirements.txt
```

### 3. Ingestion (1회)
```bash
cd ingestion
/opt/anaconda3/bin/python run_ingestion.py
```

### 4. Streamlit 포털 실행
```bash
cd portal
/opt/anaconda3/bin/python -m streamlit run app.py
```

---

## ✅ Phase 체크리스트

### Phase 0 — AWS 인프라 설정 ✅
- [x] AWS 계정 로그인 (Ready Set Build, $140 크레딧)
- [x] S3 버킷 생성 (`bedrock-agent-poc-jjun43`, ap-southeast-2)
- [x] IAM 사용자 (`js43.lee`) + S3/Bedrock 권한
- [x] Bedrock 모델 확인 (Claude Sonnet 4.6 서버리스)

### Phase 1 — Ingestion Pipeline ✅
- [x] `task.yaml` Harness 문서
- [x] `web_fetch.py` MCP 도구
- [x] `agent.py` Strands 기반 인제스천 에이전트
- [x] FAISS 인덱스 + NetworkX 그래프 → S3

### Phase 2 — Query Agent ✅
- [x] FAISS 벡터 검색
- [x] Graph BFS 확장 (하이브리드 RAG)
- [x] Bedrock Guardrails 연동

### Phase 3 — Streamlit 포털 ✅
- [x] 최신 버전 다이제스트 카드
- [x] Pyvis 인터랙티브 그래프
- [x] Q&A 탭 (하이브리드 RAG)

### Phase 4 — 평가 & 마무리 ✅
- [x] Bedrock LLM-as-Judge (Faithfulness / Relevancy / Recall)
- [ ] Streamlit Community Cloud 배포
- [ ] Bedrock Evaluation 결과 README 추가

---

## 💰 비용 추산

| 서비스 | 예상 비용 |
|--------|-----------|
| Claude Sonnet 4.6 (인제스천 + 쿼리 테스트) | ~$0.50 |
| Titan Embed V2 | ~$0.10 |
| S3 (< 1MB) | ~$0.00 |
| **합계** | **~$0.60** |

Ready Set Build $140 크레딧으로 충분히 커버됩니다.

---

## 📍 AWS 설정

- **리전**: ap-southeast-2 (시드니) — Ready Set Build 무료 플랜 지원 리전
- **모델**: `anthropic.claude-sonnet-4-6-20250514-v1:0` (AU 추론 프로파일)
- **버킷**: `bedrock-agent-poc-jjun43`
