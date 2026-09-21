from daystrom.loki import LokiClient


client = LokiClient()

result = client.query_range(
    '{app=~"sable|vesper"}',
    limit=20,
)


for stream in result["data"]["result"]:
    labels = stream["stream"]

    for timestamp, message in stream["values"]:
        print(
            timestamp,
            labels.get("host"),
            labels.get("app"),
            labels.get("log_type"),
            message,
        )
