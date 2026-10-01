"""MCP web_fetch 도구: AWS 문서 URL → 마크다운 변환"""
import httpx
import html2text
from strands import tool


@tool
def fetch_aws_doc(url: str, label: str) -> dict:
    """AWS 문서 URL을 마크다운으로 변환해서 반환합니다.
    
    Args:
        url: 수집할 AWS 문서 URL
        label: 문서 식별 레이블 (예: 'bedrock-intro-v2')
    
    Returns:
        label, url, content(markdown) 포함한 딕셔너리
    """
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; BedrockPOC/1.0)"})
        r.raise_for_status()
        
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # 줄바꿈 없음
        
        content = h.handle(r.text)
        return {
            "label": label,
            "url": url,
            "content": content,
            "status": "success",
            "length": len(content)
        }
    except Exception as e:
        return {
            "label": label,
            "url": url,
            "content": "",
            "status": "error",
            "error": str(e)
        }
