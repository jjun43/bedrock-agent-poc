"""Streamlit 포털: AWS Tutorial Dedup 대시보드"""
import os
import sys
import json
import streamlit as st
import networkx as nx
from pyvis.network import Network
import tempfile
from pathlib import Path

# 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "query"))

st.set_page_config(
    page_title="AWS Tutorial Dedup POC",
    page_icon="🤖",
    layout="wide"
)

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


def load_data():
    """S3에서 데이터 로드 (캐시)"""
    import boto3
    s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))
    BUCKET = os.getenv("S3_BUCKET")
    
    metadata = []
    graph_data = {}
    
    try:
        resp = s3.get_object(Bucket=BUCKET, Key="metadata.json")
        metadata = json.loads(resp["Body"].read())
    except Exception as e:
        st.warning(f"메타데이터 로드 실패: {e}")
    
    try:
        resp = s3.get_object(Bucket=BUCKET, Key="graph.json")
        graph_data = json.loads(resp["Body"].read())
    except Exception as e:
        st.warning(f"그래프 로드 실패: {e}")
    
    return metadata, graph_data


def render_graph(graph_data: dict):
    """Pyvis로 인터랙티브 그래프 렌더링"""
    G = nx.node_link_graph(graph_data)
    net = Network(height="450px", width="100%", bgcolor="#1a1a2e", font_color="#eee")
    
    for node in G.nodes(data=True):
        label = node[0]
        color = "#4e8cff" if "bedrock" in label else "#ff6b6b"
        net.add_node(label, label=label, color=color, size=20)
    
    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "related")
        color = "#ffd166" if relation == "supersedes" else "#95e1d3"
        net.add_edge(u, v, label=relation, color=color)
    
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        with open(f.name) as fh:
            return fh.read()


# ── UI 시작 ──────────────────────────────────────────────────────────
st.title("🤖 AWS Tutorial Dedup POC")
st.caption("Bedrock + FAISS + Graph RAG | AWS ProServe Senior AI Application Architect L6")

tab1, tab2, tab3 = st.tabs(["📋 문서 다이제스트", "🕸️ 지식 그래프", "💬 Q&A"])

with tab1:
    st.subheader("최신 버전 AWS 튜토리얼 다이제스트")
    
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
    
    metadata, graph_data = load_data()
    
    if metadata:
        cols = st.columns(2)
        for i, doc in enumerate(metadata):
            with cols[i % 2]:
                meta = doc.get("metadata", {})
                with st.container(border=True):
                    st.markdown(f"**{doc['label']}**")
                    st.caption(doc.get("url", ""))
                    st.write(meta.get("summary", "요약 없음"))
                    if meta.get("keywords"):
                        st.markdown(" ".join(f"`{k}`" for k in meta["keywords"]))
    else:
        st.info("아직 데이터가 없습니다. Ingestion을 먼저 실행하세요.")
        st.code("cd ingestion && /opt/anaconda3/bin/python run_ingestion.py")

with tab2:
    st.subheader("문서 관계 그래프")
    
    _, graph_data = load_data()
    
    if graph_data and graph_data.get("nodes"):
        html = render_graph(graph_data)
        st.components.v1.html(html, height=480)
        
        G = nx.node_link_graph(graph_data)
        col1, col2, col3 = st.columns(3)
        col1.metric("노드 수", G.number_of_nodes())
        col2.metric("엣지 수", G.number_of_edges())
        col3.metric("연결 요소", nx.number_weakly_connected_components(G))
    else:
        st.info("그래프 데이터가 없습니다. Ingestion 실행 후 확인하세요.")

with tab3:
    st.subheader("AWS 문서 Q&A (하이브리드 RAG)")
    
    query = st.text_input(
        "질문 입력",
        placeholder="예: Bedrock Agent를 설정하는 방법은?",
        key="query_input"
    )
    
    col1, col2 = st.columns([3, 1])
    with col2:
        use_kb = st.toggle("Knowledge Base 사용", value=False)
    
    if st.button("🔍 검색", type="primary") and query:
        with st.spinner("검색 중..."):
            try:
                from agent import answer
                result = answer(query)
                
                st.markdown("### 답변")
                st.write(result["answer"])
                
                if result.get("sources"):
                    st.markdown("### 📚 참고 문서")
                    for src in result["sources"]:
                        st.markdown(f"- [{src['label']}]({src['url']}) (유사도: {src['score']:.3f})")
            except Exception as e:
                st.error(f"오류: {e}")
                st.info("Ingestion을 먼저 실행하세요.")

st.divider()
st.caption("Built with Amazon Bedrock · Strands Agents · FAISS · NetworkX · Streamlit")
