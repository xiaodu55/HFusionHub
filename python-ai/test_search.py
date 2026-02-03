"""
Search Tool API 测试脚本
"""
import sys
import os

# 设置 UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

def test_search():
    print("=" * 60)
    print("Search Tool API Test")
    print("=" * 60)

    # 1. Test Milvus connection
    print("\n[1] Testing Milvus connection...")
    try:
        from app.core.vectorstore.milvus_store import get_milvus_client, create_collection
        client = get_milvus_client()
        if client:
            print("  [OK] Milvus connected")
            create_collection()
            print("  [OK] Collection created/verified")
        else:
            print("  [FAIL] Milvus connection failed")
            return
    except Exception as e:
        print(f"  [FAIL] Milvus error: {e}")
        return

    # 2. Test Embedding service
    print("\n[2] Testing Embedding service...")
    embedding = None
    try:
        from app.core.embedding import get_embedding_service
        es = get_embedding_service()
        embedding = es.get_embedding("test text")
        if embedding and len(embedding) > 0:
            print(f"  [OK] Embedding generated, dim={len(embedding)}")
        else:
            print("  [FAIL] Embedding generation failed")
    except Exception as e:
        print(f"  [FAIL] Embedding error: {e}")

    # 3. Test SearchTool
    print("\n[3] Testing SearchTool...")
    try:
        from app.core.tools.search_tool import SearchTool
        import asyncio

        tool = SearchTool(knowledge_base_id=1)

        async def run_search():
            return await tool.execute(query="test search", top_k=5)

        results = asyncio.run(run_search())

        if results:
            print(f"  [OK] Search executed, {len(results)} results")
            for i, r in enumerate(results[:3]):
                if "error" in r:
                    print(f"    [{i+1}] Error: {r['error']}")
                else:
                    print(f"    [{i+1}] score={r.get('score', 0):.4f}, content={r.get('content', '')[:50]}...")
        else:
            print("  [WARN] Empty results (knowledge base may be empty)")
    except Exception as e:
        print(f"  [FAIL] SearchTool error: {e}")
        import traceback
        traceback.print_exc()

    # 4. Test search_similar directly
    print("\n[4] Testing search_similar function...")
    try:
        from app.core.vectorstore.milvus_store import search_similar

        # Text search
        results = search_similar(query_text="test", top_k=5, knowledge_base_id=1)
        print(f"  [OK] Text search: {len(results)} results")

        # Embedding search
        if embedding:
            results = search_similar(query_embedding=embedding, top_k=5)
            print(f"  [OK] Embedding search: {len(results)} results")
    except Exception as e:
        print(f"  [FAIL] search_similar error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)


if __name__ == "__main__":
    test_search()
