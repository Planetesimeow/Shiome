"""CSV 导入：表头模糊匹配、宽容的数字解析、重复导入不产生重复行。"""
import pytest

from app.ingestion import parse_creator_center_csv, _parse_number


@pytest.mark.parametrize("raw,expected", [
    ("1,234", 1234), ("1.2万", 12000), ("3.5w", 35000), ("2.1亿", 210000000),
    ("21秒", 21), ("0:21", 21), ("1:00:00", 3600), ("512次", 512),
])
def test_parse_number_tolerates_creator_center_formats(raw, expected):
    assert _parse_number(raw) == expected


def test_parse_number_rejects_garbage():
    with pytest.raises(ValueError):
        _parse_number("这不是数字")


def test_csv_import_inserts_then_updates(client, account_id, csv_bytes):
    files = {"file": ("sample_import.csv", csv_bytes, "text/csv")}
    first = client.post("/api/posts/import", files=files).json()
    assert first["inserted"] == 3 and first["updated"] == 0

    second = client.post("/api/posts/import", files=files).json()
    assert second["inserted"] == 0 and second["updated"] == 3, "重复导入不该产生重复行"
    assert len(client.get("/api/posts").json()) == 3


def test_csv_percentages_and_durations_land_correctly(client, account_id, csv_bytes):
    client.post("/api/posts/import",
                files={"file": ("s.csv", csv_bytes, "text/csv")})
    post = next(p for p in client.get("/api/posts").json()
                if p["title"].startswith("CSV导入·体态反差科普A"))
    assert post["completion_rate"] == pytest.approx(0.46)
    assert post["avg_watch_time"] == pytest.approx(21.0)
    assert post["plays"] == 35000


def test_csv_import_applies_anomaly_flag(client, account_id, csv_bytes, test_data):
    for period in test_data["anomaly_periods"]:
        client.post("/api/anomaly-periods", json=period)
    client.post("/api/posts/import", files={"file": ("s.csv", csv_bytes, "text/csv")})
    flagged = [p for p in client.get("/api/posts").json() if p["is_anomaly_period"]]
    assert len(flagged) == 1 and "异常期样本C" in flagged[0]["title"]


def test_missing_required_headers_is_a_400(client, account_id):
    bad = "播放量,点赞数\n100,5\n".encode("utf-8")
    r = client.post("/api/posts/import", files={"file": ("bad.csv", bad, "text/csv")})
    assert r.status_code == 400


def test_bad_row_is_reported_not_fatal():
    csv = ("视频标题,发布时间,播放量\n"
           "好的一行,2026-04-01,1000\n"
           "坏的一行,2026-04-02,这不是数字\n").encode("utf-8")
    records, errors = parse_creator_center_csv(csv)
    assert len(records) == 2, "个别字段坏掉不该整行丢弃"
    assert len(errors) == 1 and errors[0]["line"] == 3
    assert records[1].get("plays") is None
