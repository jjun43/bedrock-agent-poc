# bedrock-agent-poc

> **PoC:** On-premise RAG 시스템(LLM Wiki)을 Amazon Bedrock · AgentCore · Strands Agents 기반으로 재설계

## 🎯 목표

사내 온프레미스 LLM Wiki RAG 시스템을 AWS로 이전하는 과정을 직접 경험하며,  
Bedrock 기반 멀티 에이전트 아키텍처와 Evals 체계를 구축한다.

## 🏗️ 목표 아키텍처

```
[사용자 질의]
      │
      ▼
[Strands Agents - Orchestrator]
      │
      ├──► [Amazon Bedrock Knowledge Base]
      │         └── S3 (LLM Wiki 문서) + Titan Embeddings
      │
      ├──► [AgentCore - Tool 실행]
      │         └── 검색 / 요약 / 외부 API 호출
      │
      └──► [Evals]
                ├── 정답률 (Correctness)
                └── 근거 정확도 (Groundedness)
```

## 📦 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| LLM | Amazon Bedrock (Nova Pro / Claude) |
| 에이전트 프레임워크 | Strands Agents |
| 에이전트 런타임 | Amazon Bedrock AgentCore |
| Knowledge Base | Amazon Bedrock KB + S3 |
| 임베딩 | Amazon Titan Text Embeddings V2 |
| 벡터 스토어 | Amazon Bedrock 인라인 (S3 Vectors) |
| Evals | RAGAS (정답률 · 근거 정확도) |
| IaC | AWS CDK (예정) |

## 📋 진행 상태

- [x] AWS 계정 생성 및 Bedrock API 확인
- [x] GitHub 저장소 생성
- [ ] Strands Agents Hands-On Workshop 완료
- [ ] Bedrock Knowledge Base RAG 구성
- [ ] AgentCore 에이전트 배포
- [ ] Evals 파이프라인 구축 (RAGAS)
- [ ] 결과 문서화

## 🗂️ 디렉토리 구조 (예정)

```
bedrock-agent-poc/
├── agents/          # Strands Agents 정의
├── knowledge_base/  # KB 설정 및 문서 업로드 스크립트
├── evals/           # RAGAS 기반 평가 코드
├── infra/           # AWS CDK (인프라 코드)
└── docs/            # 설계 문서 및 결과 정리
```

## 🔗 참고 자료

- [Strands Agents Hands-On Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/strands-agents)
- [Amazon Bedrock AgentCore 문서](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [RAGAS 평가 프레임워크](https://docs.ragas.io/)

## ✍️ 작성자

이준성 · SK플래닛 AI/Backend 개발자  
개인 PoC 프로젝트 (2026.10 ~)
