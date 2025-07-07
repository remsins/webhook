async def test_ingest_enqueues_job(client, delivery_queue):
    # Create subscription
    payload = {"target_url": "https://example.com/hook"}
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 201
    sub_id = r.json()["id"]

    # Ingest a webhook
    event = {"yo": "yo"}
    r = await client.post(
        f"/ingest/{sub_id}",
        json=event,
        headers={"X-Event-Type": "test.event"}
    )
    assert r.status_code == 202
    body = r.json()
    assert "webhook_id" in body

    # Exactly one job in the queue
    assert delivery_queue.count == 1
