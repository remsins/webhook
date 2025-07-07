async def test_subscription_crud_flow(client):
    # Create
    payload = {
        "target_url": "https://example.com/hook",
        "secret": "s3cr3t",
        "events": ["order.created"]
    }
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 201
    sub = r.json()
    sub_id = sub["id"]
    assert sub["target_url"] == payload["target_url"]
    assert sub["secret"] == payload["secret"]
    assert sub["events"] == payload["events"]

    # Read
    r = await client.get(f"/subscriptions/{sub_id}")
    assert r.status_code == 200
    assert r.json() == sub

    # Update
    upd = {"target_url": "https://example.org/updated"}
    r = await client.patch(f"/subscriptions/{sub_id}", json=upd)
    assert r.status_code == 200
    updated = r.json()
    assert updated["target_url"] == upd["target_url"]
    assert updated["secret"] == payload["secret"]
    assert updated["events"] == payload["events"]

    # List
    r = await client.get("/subscriptions/")
    assert r.status_code == 200
    arr = r.json()
    assert any(item["id"] == sub_id for item in arr)

    # Delete
    r = await client.delete(f"/subscriptions/{sub_id}")
    assert r.status_code == 204

    # Confirm gone
    r = await client.get(f"/subscriptions/{sub_id}")
    assert r.status_code == 404
