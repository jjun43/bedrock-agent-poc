# bedrock-agent-poc

> **PoC:** AWS 튜토리얼 문서 수집 → 중복 제거 + 최신 버전 정리 → Streamlit 포털 출력  
> Amazon Bedrock · Strands Agents · Graph RAG · Harness Engineering 실습

## 🎯 시나리오

AWS 튜토리얼은 서비스·SDK 버전별로 문서가 중복 존재한다.  
MCP web_fetch로 다양한 버전의 튜토리얼을 수집하고,  
FAISS + Graph RAG로 중복을 제거하여 **최신 버전 다이제스트만** 출력한다.

```
[AWS Docs / Blog / GitHub aws-samples / Local .md (구버전)]
      │  MCP web_fetch
      ▼
[Ingestion Agent] ── Nova Pro 메타 추출 ──► [S3]
      │                                      raw_docs / faiss_index.bin / graph.json
      └── Titan Embed V2 + FAISS ───────────►[S3]
      └── NetworkX Graph ──────────────────►[S3]
                                              │ load
                                              ▼
                          [Query Agent] ── FAISS + Graph BFS ── Nova Pro + Guardrails
                                              │
                                              ▼
                                    [Streamlit Cloud 포털]
                                    ├── 중복 제거 다이제스트
                                    ├── 기술 관계 그래프 (Pyvis)
                                    ├── Knowledge Bases 비교 탭
                                    └── 직접 질의 Q&A
```

## 🏗️ 파이프라인 구조

### ① INGESTION — 사전 1회 실행

| 단계 | 구현 |
|------|------|
| Task 정의 (Harness) | `task.yaml` → S3 업로드 → Agent가 문서로 실행 |
| 문서 수집 | MCP web_fetch (`httpx` + `html2text`) |
| 메타데이터 추출 | Nova Pro (서비스명·날짜·API 버전·키워드) |
| 벡터 인덱싱 | Titan Embed V2 + FAISS (`faiss-cpu`) |
| 그래프 빌드 | NetworkX (`supersedes`, `similar_to`, `uses` 엣지) |
| 결과 저장 | S3 (raw_docs / faiss_index.bin / graph.json) |

### ② QUERY / DEMO — 실시간

| 단계 | 구현 |
|------|------|
| 배포 | GitHub → Streamlit Community Cloud (자동 배포) |
| 하이브리드 검색 | FAISS 유사도 검색 + Graph BFS 탐색 |
| 응답 생성 | Nova Pro + Bedrock Guardrails (안전 필터) |
| 관리형 RAG 비교 | Bedrock Knowledge Bases (커스텀 RAG vs 관리형 비교) |
| Agent 엔드포인트 | Bedrock AgentCore (HTTP 배포, 맛보기) |

## 📦 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| LLM | Amazon Bedrock Nova Pro 1.0 |
| 임베딩 | Amazon Titan Text Embeddings V2 |
| 에이전트 프레임워크 | Strands Agents (`@tool` 데코레이터) |
| 문서 기반 태스크 (Harness) | YAML → S3 → Agent 실행 |
| 벡터 검색 | FAISS (`faiss-cpu`) |
| 그래프 RAG | NetworkX |
| 안전 필터 | Amazon Bedrock Guardrails |
| 관리형 RAG | Amazon Bedrock Knowledge Bases |
| Agent 배포 | Amazon Bedrock AgentCore |
| 스토리지 | Amazon S3 |
| 평가 | RAGAS + Amazon Bedrock Evaluation |
| 그래프 시각화 | Pyvis |
| 웹 배포 | Streamlit Community Cloud |

## 📋 진행 상태

### Phase 0 — AWS 셋업
- [ ] S3 버킷 생성 (`us-east-1`)
- [ ] IAM 사용자 생성 + Access Key 발급
- [ ] Bedrock 모델 접근 확인 (Nova Pro, Titan Embed V2)
- [ ] 예산 알림 설정

### Phase 1 — Ingestion Pipeline
- [ ] task.yaml Harness 구현 (문서 기반 태스크 정의)
- [ ] MCP web_fetch 도구 구현
- [ ] Nova Pro 메타데이터 추출
- [ ] Titan Embed V2 + FAISS 인덱싱
- [ ] NetworkX 그래프 빌드
- [ ] S3 저장 파이프라인 완성

### Phase 2 — Query Agent
- [ ] FAISS + Graph 하이브리드 검색
- [ ] Nova Pro + Guardrails 응답 생성
- [ ] Bedrock Knowledge Bases 비교 탭
- [ ] Bedrock AgentCore 배포 (맛보기)

### Phase 3 — Streamlit 포털
- [ ] 중복 제거 다이제스트 카드
- [ ] Pyvis 그래프 시각화
- [ ] 직접 질의 Q&A 탭
- [ ] Streamlit Community Cloud 배포

### Phase 4 — 평가 · 문서화
- [ ] RAGAS 평가 (Faithfulness, Context Recall)
- [ ] Bedrock Evaluation 연동
- [ ] README 최종 정리

## 🗂️ 디렉토리 구조

```
bedrock-agent-poc/
├── ingestion/
│   ├── task.yaml          # Harness: 태스크 문서 정의
│   ├── agent.py           # Ingestion Agent (Strands)
│   ├── web_fetch.py       # MCP web_fetch 도구
│   └── run_ingestion.py   # 실행 스크립트 (1회)
├── query/
│   ├── agent.py           # Query Agent (Strands + AgentCore)
│   └── retriever.py       # FAISS + Graph 하이브리드 검색
├── portal/
│   └── app.py             # Streamlit 포털
├── evals/
│   └── eval.py            # RAGAS + Bedrock Evaluation
├── .env.example           # 환경변수 템플릿 (키 미포함)
├── requirements.txt
└── README.md
```

## 💰 예상 비용

| 서비스 | 예상 비용 |
|--------|-----------|
| S3 | ~$0.01 |
| Nova Pro (Ingestion + 데모 쿼리) | ~$0.15 |
| Titan Embed V2 | ~$0.01 |
| Guardrails | ~$0.02 |
| Knowledge Bases (OpenSearch, 사용 후 즉시 삭제) | ~$1~3 |
| Bedrock Evaluation | ~$0.10 |
| **합계** | **~$1.5~3.5** |

> Ready Set Build 크레딧 $100 기준으로 충분한 여유  
> ⚠️ Knowledge Bases 사용 후 OpenSearch Serverless 컬렉션 즉시 삭제 필요

## 🔗 참고 자료

- [Strands Agents Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/33f099a6-45a2-47d7-9e3c-a23a6568821e/en-US)
- [Amazon Bedrock AgentCore 문서](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [RAGAS 평가 프레임워크](https://docs.ragas.io/)

## ✍️ 작성자

이준성 · SK플래닛 AI/Backend 개발자  
개인 PoC 프로젝트 (2026.10 ~)
