"""Streamlit 포털: AWS Tutorial Dedup 대시보드"""
import os, sys, json
import streamlit as st
import networkx as nx
from pathlib import Path

try:
    for k, v in st.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))
sys.path.insert(0, str(Path(__file__).parent.parent / "query"))

st.set_page_config(page_title="AWS Tutorial Dedup POC", page_icon="🤖", layout="wide")


@st.cache_data(ttl=300)
def load_data():
    import boto3
    s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION"))
    BUCKET = os.getenv("S3_BUCKET")
    metadata, graph_data = [], {}
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


def render_graph(graph_data: dict) -> str:
    from pyvis.network import Network
    import tempfile
    G = nx.node_link_graph(graph_data, edges="links")
    net = Network(height="450px", width="100%", bgcolor="#1a1a2e", font_color="#eee")
    for node, attrs in G.nodes(data=True):
        color = "#4e8cff" if "bedrock" in node else "#ff6b6b"
        net.add_node(node, label=node, color=color, size=20, title=attrs.get("summary", node))
    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "related")
        color = "#ffd166" if relation == "supersedes" else "#95e1d3"
        net.add_edge(u, v, label=relation, color=color)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        with open(f.name) as fh:
            return fh.read()


PIPELINE_STEPS = [
    "MCP web_fetch",
    "Claude 메타데이터 추출",
    "FAISS 인덱싱",
    "Graph 빌드",
    "S3 저장",
]

def _render_steps(placeholder, current: int, total: int = 5):
    """상단 스텝 진행 바 렌더링 (current=-1: 대기, current=total: 완료)"""
    bars = []
    for i, name in enumerate(PIPELINE_STEPS):
        if i < current:
            icon, color, bg = "✅", "#16a34a", "#f0fdf4"
        elif i == current:
            icon, color, bg = "⏳", "#d97706", "#fffbeb"
        else:
            icon, color, bg = "○", "#94a3b8", "#f8fafc"
        bars.append(
            f"<div style='flex:1;text-align:center;padding:8px 4px;border-radius:8px;"
            f"background:{bg};border:1px solid {color}33;'>"
            f"<div style='font-size:16px'>{icon}</div>"
            f"<div style='font-size:11px;font-weight:600;color:{color};margin-top:2px'>{name}</div>"
            f"</div>"
        )
        if i < len(PIPELINE_STEPS) - 1:
            arrow_col = "#16a34a" if i < current else "#cbd5e1"
            bars.append(
                f"<div style='display:flex;align-items:center;padding:0 2px;"
                f"color:{arrow_col};font-size:18px'>→</div>"
            )
    html = (
        "<div style='display:flex;align-items:stretch;gap:0;"
        "padding:12px 0 16px;'>" + "".join(bars) + "</div>"
    )
    placeholder.markdown(html, unsafe_allow_html=True)


def run_live_ingestion(prog_placeholder, log_area):
    """실시간 ingestion 파이프라인 실행 (로그 스트리밍)"""
    import yaml, httpx, html2text, boto3, numpy as np, faiss, tempfile

    logs = []

    def log(msg):
        logs.append(msg)
        log_area.markdown("\n".join(logs))

    task_path = Path(__file__).parent.parent / "ingestion" / "task.yaml"
    with open(task_path) as f:
        task = yaml.safe_load(f)

    urls = task["steps"][0]["inputs"]["urls"]
    bucket = os.getenv("S3_BUCKET")
    region = os.getenv("AWS_DEFAULT_REGION")
    model_id = os.getenv("BEDROCK_MODEL_ID")
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    log("```")
    log(f"🚀 태스크 시작: {task['task']['name']}")

    # Step 1: MCP web_fetch
    _render_steps(prog_placeholder, 0)
    log("\n**[Step 1] MCP web_fetch** — AWS 공식 문서 수집 중...")
    docs = []
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    for item in urls:
        label, url = item["label"], item["url"]
        try:
            log(f"  📥 fetching: {label}  ({url[:60]}...)")
            r = httpx.get(url, timeout=30, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; BedrockPOC/1.0)"})
            content = h.handle(r.text)
            docs.append({"label": label, "url": url, "content": content})
            log(f"  ✅ {label} — {len(content):,} chars")
        except Exception as e:
            log(f"  ❌ {label} 실패: {e}")
    log(f"\n  → {len(docs)}개 문서 수집 완료")

    # Step 2: Claude 메타데이터 추출
    _render_steps(prog_placeholder, 1)
    log("\n**[Step 2] Claude Sonnet** — 메타데이터 추출 중...")
    enriched = []
    for doc in docs:
        snippet = doc["content"][:3000]
        prompt = f"""다음 AWS 문서에서 메타데이터를 추출하세요.
반드시 아래 JSON 형식으로만 응답하세요:
{{"title":"...","version":"...","summary":"...","keywords":["..."],"supersedes":[]}}
문서:
{snippet}"""
        try:
            resp = bedrock.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}])
            raw = resp["output"]["message"]["content"][0]["text"]
            start = raw.find("{"); end = raw.rfind("}") + 1
            meta = json.loads(raw[start:end])
            doc["metadata"] = meta
            enriched.append(doc)
            log(f"  ✅ {doc['label']} — {meta.get('summary','')[:60]}...")
        except Exception as e:
            log(f"  ❌ {doc['label']} 메타데이터 실패: {e}")
            doc["metadata"] = {"summary": "", "keywords": [], "version": "unknown"}
            enriched.append(doc)

    # Step 3: FAISS 임베딩
    _render_steps(prog_placeholder, 2)
    log("\n**[Step 3] Titan Embed V2** — 벡터 임베딩 & FAISS 인덱싱...")
    DIM = 1024
    index = faiss.IndexFlatIP(DIM)
    vectors = []
    for doc in enriched:
        text = doc["content"][:8000]
        try:
            resp = bedrock.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({"inputText": text, "dimensions": DIM, "normalize": True}),
                contentType="application/json")
            vec = np.array(json.loads(resp["body"].read())["embedding"], dtype="float32")
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
            index.add(vec.reshape(1, -1))
            log(f"  ✅ {doc['label']} 벡터화 완료")
        except Exception as e:
            log(f"  ❌ {doc['label']} 임베딩 실패: {e}")
            vectors.append(np.zeros(DIM, dtype="float32"))

    # Step 4: NetworkX 그래프
    _render_steps(prog_placeholder, 3)
    log("\n**[Step 4] NetworkX** — 지식 그래프 빌드...")
    G = nx.DiGraph()
    threshold = task.get("config", {}).get("dedup_threshold", 0.85)
    for doc in enriched:
        G.add_node(doc["label"], url=doc["url"], summary=doc["metadata"].get("summary", ""))
    edge_count = 0
    n = len(vectors)
    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(vectors[i]) > 0 and np.linalg.norm(vectors[j]) > 0:
                sim = float(np.dot(vectors[i], vectors[j]))
                if sim >= threshold:
                    G.add_edge(enriched[i]["label"], enriched[j]["label"],
                               relation="similar_to", score=sim)
                    edge_count += 1
                    log(f"  🔗 {enriched[i]['label']} → {enriched[j]['label']} (sim={sim:.3f})")
    log(f"  → 노드: {G.number_of_nodes()}, 엣지: {edge_count}")

    # Step 5: S3 저장
    _render_steps(prog_placeholder, 4)
    log("\n**[Step 5] S3** — 아티팩트 저장 중...")
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            faiss.write_index(index, tmp.name)
            s3.upload_file(tmp.name, bucket, "faiss_index.bin")
        log(f"  ✅ faiss_index.bin → s3://{bucket}/")
        graph_json = nx.node_link_data(G, edges="links")
        s3.put_object(Bucket=bucket, Key="graph.json",
                      Body=json.dumps(graph_json, ensure_ascii=False))
        log(f"  ✅ graph.json → s3://{bucket}/")
        meta_list = [{"label": d["label"], "url": d["url"], "metadata": d["metadata"]}
                     for d in enriched]
        s3.put_object(Bucket=bucket, Key="metadata.json",
                      Body=json.dumps(meta_list, ensure_ascii=False))
        log(f"  ✅ metadata.json → s3://{bucket}/")
        for doc in enriched:
            s3.put_object(Bucket=bucket, Key=f"raw_docs/{doc['label']}.md",
                          Body=doc["content"].encode())
        log(f"  ✅ raw_docs/ → {len(enriched)}개 문서")
    except Exception as e:
        log(f"  ❌ S3 저장 실패: {e}")

    _render_steps(prog_placeholder, 5)
    log(f"\n✅ **Ingestion 완료!** 문서 {len(enriched)}개 처리")
    log("```")
    return True


# ── UI ───────────────────────────────────────────────────────────────
st.title("🤖 AWS Tutorial Dedup POC")
st.caption("Bedrock + FAISS + Graph RAG  ·  AWS ProServe Senior AI Application Architect L6")

tab1, tab2, tab3, tab4 = st.tabs(["📋 문서 다이제스트", "🕸️ 지식 그래프", "💬 Q&A", "⚡ 실시간 수집"])

# ── Tab 1: 다이제스트 ─────────────────────────────────────────────────
with tab1:
    st.subheader("최신 버전 AWS 튜토리얼 다이제스트")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
    metadata, _ = load_data()
    if metadata:
        cols = st.columns(2)
        for i, doc in enumerate(metadata):
            meta = doc.get("metadata", {})
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"**{doc['label']}**")
                    st.caption(doc.get("url", ""))
                    st.write(meta.get("summary", "요약 없음"))
                    kws = meta.get("keywords", [])
                    if kws:
                        st.markdown(" ".join(f"`{k}`" for k in kws))
    else:
        st.info("아직 데이터가 없습니다.")

# ── Tab 2: 그래프 ────────────────────────────────────────────────────
with tab2:
    st.subheader("문서 관계 그래프")
    _, graph_data = load_data()
    if graph_data and graph_data.get("nodes"):
        html = render_graph(graph_data)
        st.components.v1.html(html, height=480)
        G = nx.node_link_graph(graph_data, edges="links")
        c1, c2, c3 = st.columns(3)
        c1.metric("노드", G.number_of_nodes())
        c2.metric("엣지", G.number_of_edges())
        c3.metric("연결 요소", nx.number_weakly_connected_components(G))
    else:
        st.info("그래프 데이터가 없습니다.")

# ── Tab 3: Q&A ───────────────────────────────────────────────────────
with tab3:
    st.subheader("AWS 문서 Q&A (하이브리드 RAG)")
    query = st.text_input("질문 입력", placeholder="예: Bedrock Agent를 설정하는 방법은?")
    if st.button("🔍 검색", type="primary") and query:
        with st.spinner("검색 중..."):
            try:
                from agent import answer
                result = answer(query)
                st.markdown("### 💬 답변")
                st.write(result["answer"])
                if result.get("sources"):
                    st.markdown("### 📚 참고 문서")
                    for src in result["sources"]:
                        score = src.get('score', 0)
                        st.markdown(f"- [{src['label']}]({src['url']})  `{score:.3f}`")
            except Exception as e:
                st.error(f"오류: {e}")

# ── Tab 4: 실시간 수집 ────────────────────────────────────────────────
with tab4:
    prog_placeholder = st.empty()
    log_placeholder = st.empty()

    if not st.session_state.get("t4_started"):
        with log_placeholder.container():
            st.markdown("## ⚡ 실시간 Ingestion 파이프라인")
            # Pipeline flow badges
            st.markdown(
                "<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;"
                "margin:12px 0 20px;font-size:13px;'>"
                "<span style='background:#dbeafe;color:#1e40af;padding:4px 12px;"
                "border-radius:20px;font-weight:600'>MCP web_fetch</span>"
                "<span style='color:#94a3b8;font-size:18px'>→</span>"
                "<span style='background:#fef3c7;color:#92400e;padding:4px 12px;"
                "border-radius:20px;font-weight:600'>Claude 메타데이터 추출</span>"
                "<span style='color:#94a3b8;font-size:18px'>→</span>"
                "<span style='background:#dcfce7;color:#166534;padding:4px 12px;"
                "border-radius:20px;font-weight:600'>FAISS 인덱싱</span>"
                "<span style='color:#94a3b8;font-size:18px'>→</span>"
                "<span style='background:#f3e8ff;color:#6b21a8;padding:4px 12px;"
                "border-radius:20px;font-weight:600'>Graph 빌드</span>"
                "<span style='color:#94a3b8;font-size:18px'>→</span>"
                "<span style='background:#fef9c3;color:#713f12;padding:4px 12px;"
                "border-radius:20px;font-weight:600'>S3 저장</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown("**수집 대상 문서**")
            import yaml as _yaml
            _task_path = Path(__file__).parent.parent / "ingestion" / "task.yaml"
            try:
                with open(_task_path) as _f:
                    _task = _yaml.safe_load(_f)
                for _item in _task["steps"][0]["inputs"]["urls"]:
                    st.markdown(f"- `{_item['label']}` — {_item['url']}")
            except Exception:
                pass
            st.markdown("")
            if st.button("🚀 실시간 수집 시작", type="primary", use_container_width=True):
                st.session_state.t4_started = True
                log_placeholder.empty()
                try:
                    run_live_ingestion(prog_placeholder, log_placeholder)
                    st.success("✅ 완료! '문서 다이제스트' 탭에서 결과를 확인하세요.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"오류: {e}")
    else:
        st.info("이미 수집이 완료되었습니다.")
        if st.button("🔄 다시 실행", type="secondary"):
            st.session_state.t4_started = False
            st.rerun()

st.divider()
st.caption("Built with Amazon Bedrock · Strands Agents · FAISS · NetworkX · Streamlit")
