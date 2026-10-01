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

# ── 완료 화면 네비게이션: query param 처리 ─────────────────────────────────
_nav_q = st.query_params.get("nav", "")
if _nav_q:
    _nav_map = {
        "digest": "📋 문서 다이제스트",
        "graph": "🕸️ 지식 그래프",
        "qa": "💬 Q&A",
    }
    if _nav_q in _nav_map:
        st.session_state.nav_page = _nav_map[_nav_q]
    st.query_params.clear()
    st.rerun()


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

def _render_steps(placeholder, current: int):
    """타임라인 + 로딩바 (current=-1: 대기, 0~4: 진행중, 5: 완료)"""
    COLORS = ["#14b8a6", "#8b5cf6", "#3b82f6", "#10b981", "#f59e0b"]
    total = len(PIPELINE_STEPS)

    # 진행선 / 로딩바 너비 %
    if current < 0:
        fill = 0.0
    elif current >= total:
        fill = 100.0
    else:
        fill = current / (total - 1) * 100.0

    # 그라디언트 색상
    done = COLORS[: max(1, min(current + 1, total))]
    gradient = f"linear-gradient(90deg, {', '.join(done)})"
    glow_color = done[-1]

    # 로딩 텍스트
    if current < 0:
        bar_label = "대기 중..."
    elif current >= total:
        bar_label = "✅&nbsp; COMPLETE"
    else:
        bar_label = f"LOADING...&nbsp;&nbsp;{PIPELINE_STEPS[current]}"

    # 타임라인 노드
    nodes = ""
    for i, name in enumerate(PIPELINE_STEPS):
        c = COLORS[i]
        pos = i / (total - 1) * 100
        if current < 0 or i > current:            # 대기
            dot = (f"width:14px;height:14px;border:2px solid #4b5563;"
                   f"background:#1e2130;border-radius:50%;margin-top:1px;")
            lc, lw = "#4b5563", "400"
        elif i == current:                         # 진행중
            dot = (f"width:18px;height:18px;border:3px solid {c};"
                   f"background:#1e2130;border-radius:50%;margin-top:-1px;"
                   f"box-shadow:0 0 0 4px {c}33;")
            lc, lw = c, "700"
        else:                                      # 완료
            dot = f"width:16px;height:16px;background:{c};border-radius:50%;"
            lc, lw = c, "600"

        nodes += (
            f"<div style='position:absolute;left:{pos:.1f}%;transform:translateX(-50%);"
            f"display:flex;flex-direction:column;align-items:center;'>"
            f"<div style='font-size:10px;font-weight:{lw};color:{lc};white-space:nowrap;"
            f"text-align:center;height:32px;display:flex;align-items:flex-end;"
            f"padding-bottom:6px;line-height:1.2;'>{name}</div>"
            f"<div style='{dot}'></div>"
            f"</div>"
        )

    html = (
        "<div style='padding:4px 3%;margin:10px 0 4px;'>"
        # ── 타임라인 ──
        "<div style='position:relative;height:58px;'>"
        "<div style='position:absolute;top:44px;left:0;right:0;height:2px;"
        "background:#2d3748;border-radius:1px;'></div>"
        f"<div style='position:absolute;top:44px;left:0;width:{fill:.1f}%;height:2px;"
        f"background:{gradient};border-radius:1px;transition:width .4s ease;'></div>"
        + nodes +
        "</div>"
        # ── 로딩 바 ──
        "<div style='margin-top:18px;'>"
        "<div style='position:relative;height:32px;background:#2d3748;"
        "border-radius:8px;overflow:hidden;'>"
        f"<div style='position:absolute;inset:0 auto 0 0;width:{fill:.1f}%;"
        f"background:{gradient};border-radius:8px;"
        f"box-shadow:0 0 18px {glow_color}88;"
        "transition:width .5s ease;'></div>"
        "</div>"
        f"<div style='margin-top:10px;text-align:center;font-size:17px;"
        f"font-weight:800;letter-spacing:3px;color:#cbd5e1;'>{bar_label}</div>"
        "</div>"
        "</div>"
    )
    placeholder.markdown(html, unsafe_allow_html=True)


def run_live_ingestion(prog_placeholder, log_area):
    """실시간 ingestion 파이프라인 실행 (로그 스트리밍)"""
    import yaml, httpx, html2text, boto3, numpy as np, faiss, tempfile

    logs = []

    def log(msg):
        import re as _re
        logs.append(msg)
        _lines = [l for l in logs if l != "```"]
        _html = "<br>".join([_re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', l) for l in _lines])
        log_area.markdown(
            f"<div style='background:#0d1117;border:1px solid #30363d;border-radius:8px;"
            f"padding:16px 20px;font-family:ui-monospace,monospace;"
            f"font-size:13px;color:#c9d1d9;line-height:1.9;max-height:450px;"
            f"overflow-y:auto;'>{_html}</div>",
            unsafe_allow_html=True
        )

    task_path = Path(__file__).parent.parent / "ingestion" / "task.yaml"
    with open(task_path) as f:
        task = yaml.safe_load(f)

    urls = task["steps"][0]["inputs"]["urls"]
    bucket = os.getenv("S3_BUCKET")
    region = os.getenv("AWS_DEFAULT_REGION")
    model_id = os.getenv("BEDROCK_MODEL_ID", "au.anthropic.claude-sonnet-4-6")
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
    threshold = 0.45  # 코사인 유사도 임계값 (0.85 → 0.45)
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


# ── Grafana CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] > .main { background:#111217; }
[data-testid="stSidebar"] { background:#181b1f !important; border-right:1px solid #2c3235; }
[data-testid="stSidebar"] > div:first-child { padding-top:0; }

.gf-logo { padding:20px 16px 12px; border-bottom:1px solid #2c3235; margin-bottom:8px; }
.gf-logo-title { font-size:15px;font-weight:700;color:#f46800;letter-spacing:0.02em; }
.gf-logo-sub { font-size:11px;color:#6c7a8a;margin-top:2px; }

[data-testid="stSidebar"] [role="radiogroup"] { gap:2px !important; }
[data-testid="stSidebar"] label[data-baseweb="radio"] {
    background:transparent;border-radius:4px;padding:8px 16px;
    cursor:pointer;transition:background .15s;width:100%;font-size:14px;
}
[data-testid="stSidebar"] label[data-baseweb="radio"],
[data-testid="stSidebar"] label[data-baseweb="radio"] *,
[data-testid="stSidebar"] [role="radiogroup"] p,
[data-testid="stSidebar"] [role="radiogroup"] span,
[data-testid="stSidebar"] [role="radiogroup"] div {
    color:#ffffff !important;
}
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover { background:#2c3235; }
[data-testid="stSidebar"] label[data-baseweb="radio"][aria-checked="true"],
[data-testid="stSidebar"] label[data-baseweb="radio"][aria-checked="true"] * {
    background:rgba(244,104,0,0.15);border-left:3px solid #f46800;
    color:#f46800 !important;font-weight:700;
}

.gf-page-header { border-bottom:1px solid #2c3235; padding:16px 0 14px; margin-bottom:20px; }
.gf-page-title { font-size:22px;font-weight:700;color:#d8dee9; }
.gf-page-sub { font-size:13px;color:#6c7a8a;margin-top:3px; }
.gf-page-sub2 { font-size:12px;color:#4a5568;margin-top:3px; }

[data-testid="stMetricValue"] { color:#f46800 !important; }
.stButton > button[kind="primary"] { background:#f46800 !important;border:none;color:#fff !important; }
.stButton > button[kind="primary"]:hover { background:#d45a00 !important; }

.gf-sidebar-footer {
    margin-top:32px;padding-top:12px;border-top:1px solid #2c3235;
    font-size:11px;color:#4a5568;line-height:1.6;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div class="gf-logo">
  <div class="gf-logo-title">🤖 AWS Dedup POC</div>
  <div class="gf-logo-sub">Bedrock · FAISS · Graph RAG</div>
</div>
""", unsafe_allow_html=True)

    page = st.radio(
        "navigation",
        ["⚡ 실시간 수집", "📋 문서 다이제스트", "🕸️ 지식 그래프", "💬 Q&A"],
        key="nav_page",
        label_visibility="collapsed",
    )

    st.markdown("""
<div class="gf-sidebar-footer">
  Amazon Bedrock<br>Strands Agents · FAISS · NetworkX
</div>
""", unsafe_allow_html=True)

# ── Page header ───────────────────────────────────────────────────────────
st.markdown("""
<div class="gf-page-header">
  <div class="gf-page-title">🤖 AWS Tutorial Dedup POC</div>
  <div class="gf-page-sub">Bedrock + FAISS + Graph RAG</div>
  <div class="gf-page-sub2">Claude Sonnet 4.6 · Titan Embed v2 · Strands Agents SDK · NetworkX · FAISS</div>
</div>
""", unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────────────
if page == "⚡ 실시간 수집":
    prog_placeholder = st.empty()
    log_placeholder = st.empty()

    if not st.session_state.get("t4_started"):
        _render_steps(prog_placeholder, -1)
        with log_placeholder.container():
            if st.button("🚀 실시간 수집 시작", type="primary", use_container_width=True):
                st.session_state.t4_started = True
                st.session_state.t4_error = None
                log_placeholder.empty()
                try:
                    run_live_ingestion(prog_placeholder, log_placeholder)
                    st.session_state.t4_done = True
                except Exception as e:
                    st.session_state.t4_error = str(e)
                finally:
                    st.rerun()
            st.markdown("")
            st.markdown("## ⚡ 실시간 Ingestion 파이프라인")
            st.markdown("버튼을 누르면 위 파이프라인이 단계별로 진행되며 실시간 상태가 표시됩니다.")
            import yaml as _yaml
            _task_path = Path(__file__).parent.parent / "ingestion" / "task.yaml"
            try:
                with open(_task_path) as _f:
                    _task = _yaml.safe_load(_f)
                _urls = _task["steps"][0]["inputs"]["urls"]
                _rows = "".join(
                    f"<div style='display:flex;align-items:baseline;gap:10px;padding:6px 0;"
                    f"border-bottom:1px solid #2c3235;'>"
                    f"<code style='background:#1e2130;color:#7dd3fc;padding:2px 7px;"
                    f"border-radius:4px;font-size:12px;white-space:nowrap;'>{_item['label']}</code>"
                    f"<a href='{_item['url']}' target='_blank' style='color:#6c7a8a;"
                    f"font-size:12px;word-break:break-all;text-decoration:none;'"
                    f"onmouseover=\"this.style.color='#94a3b8'\" onmouseout=\"this.style.color='#6c7a8a'\">"
                    f"{_item['url']}</a></div>"
                    for _item in _urls
                )
                st.markdown(
                    f"<div style='border:1px solid #2c3235;border-radius:8px;overflow:hidden;"
                    f"margin-top:16px;'>"
                    f"<div style='background:#1a1d23;padding:8px 14px;border-bottom:1px solid #2c3235;"
                    f"display:flex;align-items:center;gap:8px;'>"
                    f"<span style='color:#f46800;font-size:13px;'>📄</span>"
                    f"<span style='color:#d8dee9;font-size:13px;font-weight:600;'>수집 대상 문서</span>"
                    f"<span style='margin-left:auto;background:#2c3235;color:#94a3b8;"
                    f"font-size:11px;padding:1px 8px;border-radius:10px;'>{len(_urls)}개</span>"
                    f"</div>"
                    f"<div style='padding:4px 14px 4px;background:#111217;'>{_rows}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            except Exception:
                pass
    else:
        _render_steps(prog_placeholder, 5)
        with log_placeholder.container():
            err = st.session_state.get("t4_error")
            if err:
                st.error(f"❌ 오류 발생: {err}")
            else:
                st.success("✅ Ingestion 완료! 다른 탭에서 결과를 확인하세요.")
            st.markdown("""
<style>
.nav-link {
  background:#1a1d23;border:1px solid #2c3235;border-radius:8px;
  padding:14px 18px;display:flex;align-items:flex-start;gap:14px;
  text-decoration:none;margin-bottom:8px;transition:border-color .15s;
}
.nav-link:hover { border-color:#f46800; }
</style>
<div style='margin-top:8px;'>

  <a href="?nav=digest" class='nav-link'>
    <span style='font-size:20px;'>📋</span>
    <div>
      <div style='color:#d8dee9;font-size:14px;font-weight:600;margin-bottom:3px;'>문서 다이제스트</div>
      <div style='color:#6c7a8a;font-size:12px;line-height:1.6;'>수집된 AWS 문서의 요약·키워드·버전 정보를 카드 형태로 확인합니다.</div>
    </div>
    <span style='margin-left:auto;color:#f46800;font-size:16px;align-self:center;'>→</span>
  </a>

  <a href="?nav=graph" class='nav-link'>
    <span style='font-size:20px;'>🕸️</span>
    <div>
      <div style='color:#d8dee9;font-size:14px;font-weight:600;margin-bottom:3px;'>지식 그래프</div>
      <div style='color:#6c7a8a;font-size:12px;line-height:1.6;'>문서 간 유사도·버전 계승 관계를 NetworkX 그래프로 시각화합니다.</div>
    </div>
    <span style='margin-left:auto;color:#f46800;font-size:16px;align-self:center;'>→</span>
  </a>

  <a href="?nav=qa" class='nav-link'>
    <span style='font-size:20px;'>💬</span>
    <div>
      <div style='color:#d8dee9;font-size:14px;font-weight:600;margin-bottom:3px;'>Q&amp;A</div>
      <div style='color:#6c7a8a;font-size:12px;line-height:1.6;'>FAISS + Graph RAG 기반 하이브리드 검색으로 AWS 문서에 질문합니다.</div>
    </div>
    <span style='margin-left:auto;color:#f46800;font-size:16px;align-self:center;'>→</span>
  </a>

</div>
""", unsafe_allow_html=True)
            st.markdown("")
            if st.button("🔄 다시 실행", type="secondary", use_container_width=True):
                st.session_state.t4_started = False
                st.session_state.t4_done = False
                st.session_state.t4_error = None
                st.rerun()

elif page == "📋 문서 다이제스트":
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

elif page == "🕸️ 지식 그래프":
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

elif page == "💬 Q&A":
    st.subheader("AWS 문서 Q&A (하이브리드 RAG)")
    query = st.text_input("질문 입력", value="Bedrock Agent를 설정하는 방법은?")
    if st.button("🔍 검색", type="primary") and query:
        with st.spinner("검색 중..."):
            try:
                from agent import answer
                result = answer(query)
                st.markdown("### 💬 답변")
                st.markdown("""
<style>
[data-testid="stVerticalBlockBorderWrapper"] {
    background:#1a1d23 !important;
    border-color:#2c3235 !important;
    border-radius:8px !important;
    padding:4px 8px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] p,
[data-testid="stVerticalBlockBorderWrapper"] li,
[data-testid="stVerticalBlockBorderWrapper"] span {
    color:#d8dee9 !important;
    font-size:14px !important;
    line-height:1.85 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] h1,
[data-testid="stVerticalBlockBorderWrapper"] h2,
[data-testid="stVerticalBlockBorderWrapper"] h3 {
    color:#f0f4f8 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] code {
    background:#2c3235 !important;
    color:#7dd3fc !important;
}
</style>
""", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(result["answer"])
                if result.get("sources"):
                    st.markdown("### 📚 참고 문서")
                    for src in result["sources"]:
                        score = src.get('score', 0)
                        st.markdown(f"- [{src['label']}]({src['url']})  `{score:.3f}`")
            except Exception as e:
                st.error(f"오류: {e}")
