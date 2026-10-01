"""Ingestion 파이프라인 1회 실행 스크립트"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from agent import run_ingestion

if __name__ == "__main__":
    print("=" * 50)
    print("AWS Tutorial Dedup - Ingestion Pipeline")
    print("=" * 50)
    enriched_docs, index, G = run_ingestion()
    print("\n📊 결과 요약:")
    for doc in enriched_docs:
        meta = doc.get("metadata", {})
        print(f"  [{doc['label']}] {meta.get('summary', 'N/A')}")
