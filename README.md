# Webhook Delivery Service

## Overview

This project implements a robust backend system designed as a reliable webhook delivery service. It ingests incoming webhooks via an API endpoint, queues them for asynchronous processing, and attempts delivery to subscribed target URLs. The service handles delivery failures with an exponential backoff retry mechanism and provides visibility into the delivery status through logging and dedicated API endpoints. A minimal Streamlit UI is included for basic interaction.

This service was built as a solution to the Backend Assignment.

## Features

*   **Subscription Management:** Full CRUD API endpoints (`/subscriptions`) to manage webhook subscriptions (target URL, optional secret, optional event filtering).
*   **Webhook Ingestion:** An API endpoint (`/ingest/{subscription_id}`) to accept webhook payloads (JSON) via HTTP POST, quickly acknowledge (202 Accepted), and queue for delivery.
*   **Asynchronous Delivery:** Background workers (using RQ and Redis) process queued delivery jobs independently from the ingestion API.
*   **Retry Mechanism:** Automatic retries with exponential backoff (10s, 30s, 1m, 5m, 15m) for failed delivery attempts (non-2xx responses, timeouts, network errors), up to 5 attempts.
*   **Delivery Logging:** Detailed logging of each delivery attempt (success, failure, status code, error details) stored in PostgreSQL.
*   **Log Retention:** Automatic purging of delivery logs older than 72 hours.
*   **Status & Analytics API:** Endpoints to retrieve delivery status and history for a specific webhook (`/status/{webhook_id}`) or list recent attempts for a subscription (`/subscriptions/{subscription_id}/attempts`).
*   **Caching:** Redis caching for subscription details to optimize worker performance and reduce database load.
*   **Containerization:** Fully containerized using Docker and orchestrated locally with Docker Compose.
*   **Minimal UI:** A Streamlit application for creating/deleting subscriptions and viewing delivery attempt history.

## Architecture & Technology Choices

*   **Language:** Python 3.10
*   **Web Framework (API):** FastAPI
    *   *Rationale:* High performance due to its asynchronous nature (ASGI). Automatic data validation via Pydantic. Automatic interactive API documentation (Swagger UI/OpenAPI). Well-suited for building robust APIs quickly.
*   **Database:** PostgreSQL (v15 Alpine)
    *   *Rationale:* Robust, ACID-compliant relational database. Excellent for structured data like subscriptions and logs. Supports efficient indexing (used for `webhook_id`, `subscription_id`, `timestamp`) and reliable data storage. Handles potentially large log volumes well.
*   **Cache:** Redis (v6 Alpine)
    *   *Rationale:* Fast in-memory key-value store, ideal for caching frequently accessed subscription data to reduce database lookups in workers. Also used by RQ as the queue backend.
*   **Asynchronous Task Queue:** Redis + RQ (Redis Queue)
    *   *Rationale:* Simple yet robust Python library for handling background jobs. Decouples webhook ingestion from delivery, improving API responsiveness and reliability. Handles job persistence, retries, and scheduling naturally using Redis.
*   **UI Framework:** Streamlit
    *   *Rationale:* Allows for rapid development of simple data-oriented web applications directly in Python. Sufficient for the minimal UI requirement to demonstrate backend functionality without extensive frontend development.
*   **Containerization:** Docker & Docker Compose
    *   *Rationale:* Standard for packaging applications and their dependencies. Ensures consistent environments across development, testing, and deployment. Docker Compose simplifies local orchestration of multiple services (API, worker, DB, Redis).

## Database Schema & Indexing

Two main tables are used:

1.  **`subscriptions` Table:** Stores webhook subscription configurations.
    *   `id` (UUID, Primary Key): Unique identifier for the subscription.
    *   `target_url` (Text, Not Null): The URL where webhooks should be sent.
    *   `secret` (Text, Nullable): Optional secret key for signature verification (Bonus).
    *   `events` (Array of Text, Nullable): Optional list of event types to filter on (Bonus).

2.  **`delivery_logs` Table:** Stores the status of each delivery attempt.
    *   `id` (UUID, Primary Key): Unique identifier for the log entry.
    *   `webhook_id` (UUID, Not Null, Indexed): Identifier linking attempts for the same original incoming webhook.
    *   `subscription_id` (UUID, Not Null, Indexed): Identifier linking logs to the relevant subscription.
    *   `target_url` (Text, Not Null): The target URL for this attempt.
    *   `timestamp` (DateTime, Not Null, Indexed): When the attempt occurred (UTC).
    *   `attempt_number` (Integer, Not Null): 1 for initial attempt, 2+ for retries.
    *   `outcome` (Text, Not Null): Result of the attempt ("Success", "Failed Attempt", "Failure").
    *   `status_code` (Integer, Nullable): HTTP status code received from the target URL.
    *   `error` (Text, Nullable): Error details if the attempt failed.

**Indexing Strategy:**

*   Indexes are placed on `delivery_logs.webhook_id` and `delivery_logs.subscription_id` to allow fast lookups for the Status/Analytics API endpoints.
*   An index on `delivery_logs.timestamp` is beneficial for the log retention cleanup query.
*   Primary keys are automatically indexed.

## Prerequisites

*   Git
*   Docker Engine
*   Docker Compose (usually included with Docker Desktop)
*   Python 3.10+ (if running Streamlit UI locally outside Docker)
*   `curl` (or similar tool for testing API endpoints)

## Local Development Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/remsins/webhook.git
    cd webhook
    ```

2.  **Configure Environment:**
    Create a `.env` file in the project root. This file defines connection URLs for services *within the Docker network*.
    ```dotenv
    # .env
    DATABASE_URL=postgresql://postgres:postgres@db:5432/webhook_svc
    REDIS_URL=redis://redis:6379/0
    API_BASE_URL=http://api:8000 # Used by UI container if run via compose
    ```
    *Note: `db` and `redis` are the service names defined in `docker-compose.yml`.*

3.  **(Optional) Python Virtual Environment:** If you plan to run the Streamlit UI locally *without* Docker Compose managing it:
    ```bash
    conda create -n venv python=3.10
    pip install -r requirements.txt
    conda activate venv
    ```

## Running Locally (Docker Compose)

This is the recommended way to run the entire application stack locally. It uses the main `docker-compose.yml` and merges `docker-compose.override.yml` (if present) for development-specific settings like port mapping and volume mounts.

1.  **Start Services:** From the project root directory, run:
    ```bash
    docker-compose up --build
    ```
    *   `--build` is only needed the first time or if you change `Dockerfile` or `requirements.txt`. Subsequent starts can use `docker-compose up`.
    *   This will build the Docker image, start containers for the API, Worker, PostgreSQL, and Redis.

2.  **Access Services:**
    *   **API:** The API server will be running inside its container. If using the `docker-compose.override.yml` provided during development, it's accessible from your host machine at `http://localhost:8000`.
    *   **API Docs (Swagger UI):** `http://localhost:8000/docs`
    *   **Worker:** The worker container starts automatically and listens for jobs on the `deliveries` queue. You will see its logs in the `docker-compose up` output.
    *   **Database:** Accessible internally to other containers at `db:5432`. Exposed locally at `localhost:5432` if using the override file.
    *   **Redis:** Accessible internally at `redis:6379`. Exposed locally at `localhost:6379` if using the override file.

3.  **Access Streamlit UI (If running locally outside Docker):**
    If you set up the virtual environment and installed requirements:
    ```bash
    streamlit run ui/app.py
    ```
    Access the UI at `http://localhost:8501`. Ensure the `API_BASE_URL` in `ui/app.py` points to `http://localhost:8000` for this setup.

4.  **Stop Services:**
    Press `Ctrl+C` in the terminal where `docker-compose up` is running, or run `docker-compose down` from another terminal in the project root. To remove data volumes as well, use `docker-compose down -v`.

## API Endpoints & Examples (`curl`)

*(Base URL for local testing: `http://localhost:8000`)*

### Subscriptions

*   **Create Subscription:**
    *   `POST /subscriptions/`
    *   Creates a new webhook subscription.
    *   *Request Body:* `{"target_url": "string", "secret": "string" (optional), "events": ["list", "of", "strings"] (optional)}`
    *   *Example:*
        ```bash
        curl -X POST http://localhost:8000/subscriptions/ \
        -H "Content-Type: application/json" \
        -d '{"target_url": "https://webhook.site/your-unique-id"}'
        ```
    *   *Success Response:* `201 Created` with subscription details (including ID).

*   **List Subscriptions:**
    *   `GET /subscriptions/`
    *   Returns a list of all subscriptions.
    *   *Example:*
        ```bash
        curl http://localhost:8000/subscriptions/
        ```
    *   *Success Response:* `200 OK` with a JSON array of subscriptions.

*   **Read Subscription:**
    *   `GET /subscriptions/{subscription_id}`
    *   Returns details for a specific subscription.
    *   *Example:*
        ```bash
        curl http://localhost:8000/subscriptions/<subscription_id>
        ```
    *   *Success Response:* `200 OK` with subscription details. `404 Not Found` if ID doesn't exist.

*   **Update Subscription:**
    *   `PATCH /subscriptions/{subscription_id}`
    *   Updates fields for a specific subscription. Only provided fields are updated.
    *   *Request Body:* `{"target_url": "string" (optional), "secret": "string" (optional), "events": ["list"] (optional)}`
    *   *Example:*
        ```bash
        curl -X PATCH http://localhost:8000/subscriptions/<subscription_id> \
        -H "Content-Type: application/json" \
        -d '{"secret": "newS3cr3t"}'
        ```
    *   *Success Response:* `200 OK` with updated subscription details. `404 Not Found` if ID doesn't exist.

*   **Delete Subscription:**
    *   `DELETE /subscriptions/{subscription_id}`
    *   Deletes a specific subscription.
    *   *Example:*
        ```bash
        curl -X DELETE http://localhost:8000/subscriptions/<subscription_id>
        ```
    *   *Success Response:* `204 No Content`. `404 Not Found` if ID doesn't exist.

### Ingestion

*   **Ingest Webhook:**
    *   `POST /ingest/{subscription_id}`
    *   Accepts an incoming webhook payload (JSON) and queues it for delivery to the specified subscription's target URL.
    *   *Request Body:* Any valid JSON payload.
    *   *Optional Headers:* `X-Event-Type: string`, `X-Signature: string`
    *   *Example:*
        ```bash
        curl -X POST http://localhost:8000/ingest/<subscription_id> \
        -H "Content-Type: application/json" \
        -H "X-Event-Type: order.created" \
        -d '{"order_id": 123, "amount": 99.99, "customer": "test@example.com"}'
        ```
    *   *Success Response:* `202 Accepted` with `{"webhook_id": "<new_webhook_uuid>"}`. `404 Not Found` if `subscription_id` doesn't exist. `400 Bad Request` if body is not valid JSON.

### Status & Analytics

*   **Get Webhook Status:**
    *   `GET /status/{webhook_id}`
    *   Retrieves the delivery status summary and recent attempt history for a specific webhook ID (returned by the ingest endpoint).
    *   *Example:*
        ```bash
        curl http://localhost:8000/status/<webhook_id>
        ```
    *   *Success Response:* `200 OK` with status summary and list of recent `DeliveryAttempt` objects. `404 Not Found` if `webhook_id` has no logs.

*   **List Subscription Attempts:**
    *   `GET /subscriptions/{subscription_id}/attempts`
    *   Retrieves a list of recent delivery attempts for a specific subscription.
    *   *Query Parameters:* `limit` (integer, default 20).
    *   *Example:*
        ```bash
        curl "http://localhost:8000/subscriptions/<subscription_id>/attempts?limit=5"
        ```
    *   *Success Response:* `200 OK` with a JSON array of `DeliveryAttempt` objects (most recent first), up to the limit. Returns an empty list if no attempts found.

## Testing

The project includes a test suite using `pytest`. Tests cover API endpoints, worker logic, database interactions, caching, and error handling. Integration tests utilize `testcontainers` to spin up isolated PostgreSQL and Redis instances.

1.  **Install Test Dependencies:** Ensure `pytest` and `pytest-mock` are installed (they should be included if you installed `requirements.txt`).
2.  **Set Python Path:** Before running tests, ensure the project root is in the Python path:
    ```bash
    export PYTHONPATH=$(pwd):$PYTHONPATH
    export REDIS_URL=redis://localhost:6379/0
    export DATABASE_URL=postgresql:/postgres:postgres@localhost:5432/webhook_svc
    ```
3.  **Run Tests:**
    ```bash
    pytest
    ```
    Or with less verbose output:
    ```bash
    pytest -q --disable-warnings
    ```

**Test File Overview:**

*   `test_subscriptions.py`: Tests the full CRUD lifecycle for subscriptions via the API.
*   `test_ingest_and_queue.py`: Verifies that the `/ingest` endpoint successfully enqueues a job in Redis/RQ.
*   `test_delivery_worker.py`: Uses mocking (`pytest-mock`) to test the `process_delivery` worker function's logic for success, different failure types (HTTP error, timeout), retries with backoff, and handling of max attempts. Checks logging and retry scheduling.
*   `test_status_api.py`: Tests the `/status/{webhook_id}` and `/subscriptions/{id}/attempts` endpoints, ensuring they return correct data and structure based on pre-populated log entries.
*   `test_caching.py`: Verifies Redis cache population on miss, cache hits (avoiding DB lookups), and cache invalidation/updates on subscription changes (update/delete).
*   `test_api_errors.py`: Tests API behavior with invalid inputs (bad URLs, bad UUIDs), non-existent resources (404s), and invalid request bodies (e.g., non-JSON for ingest).
*   `test_retention.py`: Tests the `purge_old_logs` function to ensure it correctly deletes logs older than the retention period from the database.
*   `conftest.py`: Contains pytest fixtures for setting up the test environment (Docker containers via `testcontainers`), managing database sessions with transactions, providing Redis/RQ connections, and configuring the FastAPI `TestClient`.

## Deployment (Render)

This application is configured for deployment on [Render](https://render.com/) using a multi-service approach:

1.  **Managed PostgreSQL:** Create a PostgreSQL instance on Render (Free tier available). Copy the **Internal Connection String**.
2.  **Managed Redis:** Create a Redis instance on Render (Free tier available), preferably in the same region as PostgreSQL. Copy the **Internal Connection URL**.
3.  **Backend API (Web Service):**
    *   Create a new "Web Service" on Render.
    *   Connect your GitHub repository.
    *   Set Runtime to **Docker**.
    *   Point to `docker-compose.yml`.
    *   Select **`api`** as the "Service Name" from the compose file.
    *   Choose the "Free" instance type.
    *   Set Environment Variables:
        *   `DATABASE_URL`: (Paste Internal Connection String from Render DB)
        *   `REDIS_URL`: (Paste Internal Connection URL from Render Redis)
        *   `PYTHONUNBUFFERED`: `1`
        *   `PYTHONDONTWRITEBYTECODE`: `1`
    *   Set Health Check Path to `/docs`.
    *   Deploy. Copy the public URL once live (e.g., `https://your-api-name.onrender.com`).
4.  **Backend Worker (Background Worker):**
    *   Create a new "Background Worker" on Render.
    *   Connect the same GitHub repository.
    *   Set Runtime to **Docker**.
    *   Point to `docker-compose.yml`.
    *   Select **`worker`** as the "Service Name" from the compose file.
    *   Choose the "Free" instance type.
    *   Set Environment Variables (same `DATABASE_URL` and `REDIS_URL` as the API).
    *   Deploy.
5.  **Frontend UI (Web Service):**
    *   Create *another* new "Web Service" on Render.
    *   Connect the same GitHub repository.
    *   Set Runtime to **Python 3**.
    *   Build Command: `pip install -r requirements.txt`
    *   Start Command: `streamlit run ui/app.py --server.port $PORT --server.address 0.0.0.0`
    *   Choose the "Free" instance type.
    *   Set Environment Variables:
        *   `API_BASE_URL`: (Paste the public URL of your deployed `webhook-api` service)
        *   `PYTHONUNBUFFERED`: `1`
        *   `PYTHONDONTWRITEBYTECODE`: `1`
    *   Deploy. Copy the public URL once live (e.g., `https://your-ui-name.onrender.com`).

**Live URLs:**

*   **Live UI:** `https://webhook-ui.onrender.com/`
*   **Live API Base:** `https://webhook-api-8tgq.onrender.com`


## Cost Estimation (Render Free Tier)

The deployment strategy aims to utilize Render's free tiers:

*   **PostgreSQL:** Free tier (limits on DB size, shared resources).
*   **Redis:** Free tier (limits on memory, connections).
*   **API (Web Service):** Free tier (shared CPU, limited RAM, sleeps after inactivity).
*   **Worker (Background Worker):** Free tier (shared CPU, limited RAM).
*   **UI (Web Service):** Free tier (shared CPU, limited RAM, sleeps after inactivity).

**Estimated Monthly Cost: $0**

This assumes usage stays within the free tier limits. Key considerations:

*   **Web Service Inactivity:** Free web services spin down after 15 minutes of inactivity and take time (~30s) to spin up on the next request. This might affect UI responsiveness or initial API calls if unused for a while. Background workers do not sleep.
*   **Resource Limits:** High traffic volume (significantly exceeding the ~5000 webhooks/day mentioned in the prompt) or complex processing could exceed CPU/RAM limits, requiring paid tiers.
*   **Data Storage:** Exceeding free tier limits for PostgreSQL or Redis storage would incur costs.

For continuous operation and moderate traffic as specified, the free tiers should be sufficient, resulting in an estimated $0 monthly cost.

## Assumptions

*   Incoming webhook payloads are valid JSON.
*   Target URLs provided in subscriptions are valid and reachable.
*   The chosen retry schedule (exponential backoff up to 5 attempts over ~25 minutes) is acceptable.
*   A 72-hour retention period for delivery logs is sufficient.
*   The minimal Streamlit UI meets the presentation requirement.
*   Network latency between Render services and target URLs is reasonable.
*   Security considerations beyond basic setup (e.g., API rate limiting, advanced auth, input sanitization beyond Pydantic) are out of scope for this assignment version.
