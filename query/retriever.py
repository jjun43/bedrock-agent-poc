"""FAISS + Graph 하이브리드 검색기"""
import os
import json
import boto3
import faiss
import numpy as np
import networkx as nx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION"))
s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))

BUCKET = os.getenv("S3_BUCKET")
EMBED_MODEL_ID = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
SIMILARITY_THRESHOLD = 0.75


def load_artifacts() -> tuple:
    """S3에서 FAISS 인덱스, 그래프, 메타데이터 로드"""
    # FAISS 인덱스
    resp = s3.get_object(Bucket=BUCKET, Key="faiss_index.bin")
    with open("/tmp/faiss_index.bin", "wb") as f:
        f.write(resp["Body"].read())
    index = faiss.read_index("/tmp/faiss_index.bin")
    
    # 그래프
    resp = s3.get_object(Bucket=BUCKET, Key="graph.json")
    graph_data = json.loads(resp["Body"].read())
    G = nx.node_link_graph(graph_data)
    
    # 메타데이터
    resp = s3.get_object(Bucket=BUCKET, Key="metadata.json")
    metadata = json.loads(resp["Body"].read())
    
    return index, G, metadata


def get_query_embedding(text: str) -> np.ndarray:
    """쿼리 텍스트를 임베딩 벡터로 변환"""
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps({"inputText": text[:8000]}),
        contentType="application/json"
    )
    vec = np.array([json.loads(resp["body"].read())["embedding"]], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def faiss_search(index: faiss.Index, metadata: list, query_vec: np.ndarray, k: int = 3) -> list:
    """FAISS 유사도 검색 → 상위 k개 문서"""
    D, I = index.search(query_vec, k)
    results = []
    for dist, idx in zip(D[0], I[0]):
        if dist >= SIMILARITY_THRESHOLD and idx < len(metadata):
            results.append({
                **metadata[idx],
                "score": float(dist),
                "source": "faiss"
            })
    return results


def graph_expand(G: nx.DiGraph, seed_labels: list, hops: int = 2) -> list:
    """그래프 BFS 확장: seed 노드에서 N홉 이내 연결 노드 반환"""
    related = set()
    for label in seed_labels:
        if label not in G:
            continue
        # BFS
        for node in nx.single_source_shortest_path_length(G, label, cutoff=hops):
            if node != label:
                related.add(node)
    return list(related)


def hybrid_search(query: str, k: int = 3) -> dict:
    """FAISS + Graph 하이브리드 검색"""
    index, G, metadata = load_artifacts()
    
    # 1단계: FAISS 벡터 검색
    query_vec = get_query_embedding(query)
    faiss_results = faiss_search(index, metadata, query_vec, k)
    
    # 2단계: 그래프 확장
    seed_labels = [r["label"] for r in faiss_results]
    related_labels = graph_expand(G, seed_labels)
    
    # 관련 노드 메타데이터 추가
    graph_results = []
    for label in related_labels:
        match = next((m for m in metadata if m["label"] == label), None)
        if match:
            graph_results.append({**match, "source": "graph"})
    
    # 중복 제거 (FAISS 결과 우선)
    seen = {r["label"] for r in faiss_results}
    for gr in graph_results:
        if gr["label"] not in seen:
            faiss_results.append(gr)
            seen.add(gr["label"])
    
    return {
        "query": query,
        "results": faiss_results,
        "graph": nx.node_link_data(G)
    }
