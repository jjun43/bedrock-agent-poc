"""Ingestion Agent: Harness task.yaml 기반 파이프라인 실행"""
import os
import json
import yaml
import boto3
import pickle
import numpy as np
import faiss
import networkx as nx
from pathlib import Path
from dotenv import load_dotenv
from strands import Agent
from web_fetch import fetch_aws_doc

load_dotenv(Path(__file__).parent.parent / ".env")

# AWS 클라이언트
bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION"))
s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))

BUCKET = os.getenv("S3_BUCKET")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID")
EMBED_MODEL_ID = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")


def get_embedding(text: str) -> list[float]:
    """Titan Embed V2로 텍스트 임베딩"""
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps({"inputText": text[:8000]}),
        contentType="application/json"
    )
    return json.loads(resp["body"].read())["embedding"]


def extract_metadata(doc: dict) -> dict:
    """Nova Pro / Claude로 메타데이터 추출"""
    prompt = f"""다음 AWS 문서에서 메타데이터를 JSON으로 추출하세요.

문서 레이블: {doc['label']}
URL: {doc['url']}
내용 (처음 2000자):
{doc['content'][:2000]}

추출할 필드:
- service_name: AWS 서비스명
- api_version: API/SDK 버전 (없으면 null)
- publish_date: 문서 날짜 (없으면 null)  
- keywords: 핵심 키워드 리스트 (최대 5개)
- summary: 한 줄 요약

JSON만 출력하세요."""

    resp = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}]
    )
    
    text = resp["output"]["message"]["content"][0]["text"]
    # JSON 파싱
    import re
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return {**doc, "metadata": json.loads(json_match.group())}
    return {**doc, "metadata": {}}


def run_ingestion():
    """task.yaml 읽어서 파이프라인 실행"""
    task_path = Path(__file__).parent / "task.yaml"
    with open(task_path) as f:
        task = yaml.safe_load(f)
    
    print(f"🚀 태스크 시작: {task['task']['name']}")
    
    # Step 1: 문서 수집
    fetch_step = next(s for s in task["steps"] if s["id"] == "fetch_docs")
    docs = []
    for url_cfg in fetch_step["inputs"]["urls"]:
        print(f"  📥 수집: {url_cfg['label']}")
        doc = fetch_aws_doc(url_cfg["url"], url_cfg["label"])
        if doc["status"] == "success":
            docs.append(doc)
            # S3에 원본 저장
            s3.put_object(
                Bucket=BUCKET,
                Key=f"raw_docs/{doc['label']}.md",
                Body=doc["content"].encode()
            )
    print(f"  ✅ {len(docs)}개 문서 수집 완료")
    
    # Step 2: 메타데이터 추출
    print("  🔍 메타데이터 추출 중...")
    enriched_docs = [extract_metadata(d) for d in docs]
    
    # Step 3: 벡터 인덱스 빌드
    print("  🔢 FAISS 인덱스 빌드 중...")
    embeddings = []
    for doc in enriched_docs:
        emb = get_embedding(doc["content"][:8000])
        doc["embedding_idx"] = len(embeddings)
        embeddings.append(emb)
    
    emb_array = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(emb_array)
    index = faiss.IndexFlatIP(emb_array.shape[1])  # cosine similarity
    index.add(emb_array)
    
    # 유사도 검색으로 중복 후보 탐지
    D, I = index.search(emb_array, k=len(embeddings))
    
    # Step 4: 그래프 빌드
    print("  🕸️ 지식 그래프 빌드 중...")
    G = nx.DiGraph()
    for doc in enriched_docs:
        G.add_node(doc["label"], **doc.get("metadata", {}), url=doc["url"])
    
    for i, (distances, indices) in enumerate(zip(D, I)):
        for dist, j in zip(distances, indices):
            if i != j and dist >= 0.50:
                G.add_edge(
                    enriched_docs[i]["label"],
                    enriched_docs[j]["label"],
                    relation="similar_to",
                    score=float(dist)
                )
    
    # Step 5: S3 저장
    print("  💾 S3 저장 중...")
    
    # FAISS 인덱스
    faiss.write_index(index, "/tmp/faiss_index.bin")
    with open("/tmp/faiss_index.bin", "rb") as f:
        s3.put_object(Bucket=BUCKET, Key="faiss_index.bin", Body=f.read())
    
    # 그래프
    graph_data = nx.node_link_data(G)
    s3.put_object(
        Bucket=BUCKET, Key="graph.json",
        Body=json.dumps(graph_data, ensure_ascii=False).encode()
    )
    
    # 메타데이터
    metadata = [{
        "label": d["label"], "url": d["url"],
        "metadata": d.get("metadata", {}),
        "embedding_idx": d["embedding_idx"]
    } for d in enriched_docs]
    s3.put_object(
        Bucket=BUCKET, Key="metadata.json",
        Body=json.dumps(metadata, ensure_ascii=False).encode()
    )
    
    print(f"\n✅ Ingestion 완료! S3 버킷: {BUCKET}")
    print(f"   - 문서: {len(docs)}개")
    print(f"   - 그래프 노드: {G.number_of_nodes()}, 엣지: {G.number_of_edges()}")
    return enriched_docs, index, G


if __name__ == "__main__":
    run_ingestion()
