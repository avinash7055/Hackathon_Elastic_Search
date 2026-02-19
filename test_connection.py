from elasticsearch import Elasticsearch

es = Elasticsearch(
    "https://my-elasticsearch-project-a4024e.es.asia-south1.gcp.elastic.cloud:443",
    api_key="OERua1U1d0JDTElhRW8zSk94VUI6NTdEY3BRbHRTMjlOWVRBWktaMG02dw=="
)

try:
    info = es.info()
    print("✅ Connected to Elasticsearch!")
    print(f"   Cluster: {info['cluster_name']}")
    print(f"   Version: {info['version']['number']}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
