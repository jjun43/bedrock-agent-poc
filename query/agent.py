"""Query Agent: 하이브리드 RAG + Bedrock Guardrails + AgentCore 맛보기"""
import os
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv
from strands import Agent, tool
from retriever import hybrid_search

load_dotenv(Path(__file__).parent.parent / ".env")

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION"))
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "au.anthropic.claude-sonnet-4-6")
BUCKET = os.getenv("S3_BUCKET")

# Bedrock Guardrails (선택적 — 생성 후 ID 입력)
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", None)
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")


@tool
def search_aws_docs(query: str) -> str:
    """AWS 문서에서 관련 내용을 검색합니다 (FAISS + Graph RAG).
    
    Args:
        query: 검색 쿼리 (예: 'Bedrock Agent 설정 방법')
    
    Returns:
        관련 문서 요약 문자열
    """
    result = hybrid_search(query)
    docs = result["results"]
    if not docs:
        return "관련 문서를 찾지 못했습니다."
    
    lines = []
    for d in docs:
        meta = d.get("metadata", {})
        lines.append(
            f"[{d['label']}] {meta.get('summary', 'N/A')} "
            f"(출처: {d.get('source','')}, 유사도: {d.get('score', 0):.3f})"
        )
    return "\n".join(lines)


def build_converse_params(query: str, context: str) -> dict:
    """Guardrails 포함 converse 파라미터 구성"""
    params = {
        "modelId": MODEL_ID,
        "messages": [{
            "role": "user",
            "content": [{
                "text": f"""다음 AWS 문서 컨텍스트를 바탕으로 질문에 답하세요.

컨텍스트:
{context}

질문: {query}

답변 형식:
- 핵심 내용을 간결하게
- 관련 AWS 서비스/API 버전 명시
- 최신 버전 기준으로 설명
- deprecated 안내, 중요 공지, ⚠️ 경고 블록 등은 포함하지 마세요
"""
            }]
        }],
        "system": [{
            "text": (
                "당신은 AWS 튜토리얼 전문가입니다. 항상 최신 버전 기준으로 정확하게 답변하세요. "
                "답변 시 다음 규칙을 반드시 지키세요: "
                "1) 서비스 deprecated 공지, 중요 공지, 경고 배너 등 부가적인 안내 문구를 추가하지 마세요. "
                "2) 질문에서 요청한 내용만 간결하게 답변하세요. "
                "3) ⚠️ 기호나 '중요 공지' 같은 강조 블록을 사용하지 마세요."
            )
        }]
    }
    
    if GUARDRAIL_ID:
        params["guardrailConfig"] = {
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
            "trace": "enabled"
        }
    
    return params


def answer(query: str) -> dict:
    """쿼리에 대한 답변 생성"""
    # 하이브리드 검색
    search_result = hybrid_search(query)
    docs = search_result["results"]
    
    # 컨텍스트 구성
    s3_client = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))
    context_parts = []
    for doc in docs[:3]:
        try:
            resp = s3_client.get_object(Bucket=BUCKET, Key=f"raw_docs/{doc['label']}.md")
            content = resp["Body"].read().decode()[:2000]
            context_parts.append(f"=== {doc['label']} ===\n{content}")
        except:
            pass
    
    context = "\n\n".join(context_parts) if context_parts else "컨텍스트 없음"
    
    # LLM 호출 (Guardrails 포함)
    params = build_converse_params(query, context)
    resp = bedrock.converse(**params)
    
    answer_text = resp["output"]["message"]["content"][0]["text"]
    
    return {
        "query": query,
        "answer": answer_text,
        "sources": [{"label": d["label"], "url": d["url"], "score": d.get("score", 0)} for d in docs],
        "graph": search_result["graph"]
    }


if __name__ == "__main__":
    test_query = "Bedrock Agent를 설정하는 방법은?"
    result = answer(test_query)
    print(f"\n🔍 질문: {result['query']}")
    print(f"\n💬 답변:\n{result['answer']}")
    print(f"\n📚 출처:")
    for s in result["sources"]:
        print(f"  - {s['label']}: {s['url']}")
