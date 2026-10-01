"""RAGAS + Bedrock Evaluation: 파이프라인 품질 측정"""
import os
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION"))
MODEL_ID = os.getenv("BEDROCK_MODEL_ID")

# 평가 데이터셋 (골든셋)
EVAL_QUESTIONS = [
    {
        "question": "Amazon Bedrock Knowledge Base란 무엇인가?",
        "ground_truth": "Amazon Bedrock Knowledge Base는 RAG(Retrieval-Augmented Generation)를 위한 관리형 서비스로, S3의 데이터를 자동으로 임베딩하여 LLM 응답의 정확도를 높입니다."
    },
    {
        "question": "Strands Agents의 @tool 데코레이터 사용법은?",
        "ground_truth": "@tool 데코레이터를 함수에 붙이면 Strands Agent가 해당 함수를 도구로 사용할 수 있습니다. 함수의 docstring이 도구 설명으로 사용됩니다."
    },
    {
        "question": "FAISS cosine similarity 임계값 설정은?",
        "ground_truth": "faiss.IndexFlatIP와 L2 정규화를 사용하면 내적이 코사인 유사도와 동일합니다. 0.85 이상이면 중복으로 판단하는 것이 일반적입니다."
    }
]


def bedrock_evaluate(question: str, answer: str, context: str, ground_truth: str) -> dict:
    """Bedrock LLM-as-Judge로 평가"""
    prompt = f"""다음 RAG 시스템의 응답을 평가하세요.

질문: {question}
정답: {ground_truth}
제공된 컨텍스트: {context[:500]}
생성된 답변: {answer}

다음 기준으로 0~1 사이 점수를 JSON으로 출력하세요:
- faithfulness: 답변이 컨텍스트에 근거한 정도
- answer_relevancy: 답변이 질문에 관련된 정도
- context_recall: 컨텍스트가 정답을 포함하는 정도

JSON만 출력:"""

    resp = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}]
    )
    
    text = resp["output"]["message"]["content"][0]["text"]
    import re
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return {"faithfulness": 0, "answer_relevancy": 0, "context_recall": 0}


def run_evaluation():
    """전체 평가 실행"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "query"))
    from agent import answer as query_answer
    
    results = []
    print("🔬 Bedrock Evaluation 시작...")
    
    for item in EVAL_QUESTIONS:
        print(f"\n  📝 질문: {item['question'][:50]}...")
        
        try:
            result = query_answer(item["question"])
            scores = bedrock_evaluate(
                item["question"],
                result["answer"],
                "\n".join(s["label"] for s in result["sources"]),
                item["ground_truth"]
            )
            results.append({
                "question": item["question"],
                "scores": scores,
                "sources": [s["label"] for s in result["sources"]]
            })
            print(f"  ✅ Faithfulness: {scores.get('faithfulness', 0):.2f} | "
                  f"Relevancy: {scores.get('answer_relevancy', 0):.2f} | "
                  f"Recall: {scores.get('context_recall', 0):.2f}")
        except Exception as e:
            print(f"  ❌ 오류: {e}")
    
    # 평균 점수
    if results:
        avg_faith = sum(r["scores"].get("faithfulness", 0) for r in results) / len(results)
        avg_rel = sum(r["scores"].get("answer_relevancy", 0) for r in results) / len(results)
        avg_rec = sum(r["scores"].get("context_recall", 0) for r in results) / len(results)
        
        print(f"\n📊 평균 점수:")
        print(f"  Faithfulness:     {avg_faith:.3f}")
        print(f"  Answer Relevancy: {avg_rel:.3f}")
        print(f"  Context Recall:   {avg_rec:.3f}")
        
        # S3에 결과 저장
        s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))
        s3.put_object(
            Bucket=os.getenv("S3_BUCKET"),
            Key="eval_results.json",
            Body=json.dumps({
                "results": results,
                "averages": {
                    "faithfulness": avg_faith,
                    "answer_relevancy": avg_rel,
                    "context_recall": avg_rec
                }
            }, ensure_ascii=False).encode()
        )
        print("\n✅ 결과를 S3에 저장했습니다 (eval_results.json)")
    
    return results


if __name__ == "__main__":
    run_evaluation()
